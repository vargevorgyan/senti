"""Endpoints used by the local Senti engine on each Mac (device token auth)."""
from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import corporate
from ..bundle import resolve, signed_bundle
from ..bus import bus, sse
from ..config import settings
from ..db import get_db
from ..models import KV, Approval, Device, EnrollmentCode, Event, Invite, Profile, User
from ..security import current_device, hash_key, limiter, new_device_token
from ..signing import public_key_b64, sign

router = APIRouter(prefix="/api/v1")


class EnrollIn(BaseModel):
    invite: str = ""      # personal one-time key from the admin (preferred)
    code: str = ""        # legacy enrollment code (personal codes; shared ones only when explicitly allowed)
    user_email: str = ""
    hostname: str = ""
    platform: str = ""


@router.post("/devices/enroll")
def enroll(body: EnrollIn, db: Session = Depends(get_db)):
    if body.invite.strip():
        return _enroll_with_invite(body, db)
    from sqlalchemy import update
    code = db.get(EnrollmentCode, body.code.strip())
    if code is None or code.uses_left <= 0 or (code.expires_at and code.expires_at < time.time()):
        raise HTTPException(403, "enrollment code is invalid or expired")
    if not code.email and not settings.allow_shared_codes and code.code != settings.demo_enroll_code:
        # a shared code is not tied to a person: if it leaks, anyone can join. Admins invite people instead.
        raise HTTPException(403, "shared enrollment codes are disabled; ask your administrator for a personal invite")
    # atomic decrement: parallel requests can't over-spend a code
    if db.execute(update(EnrollmentCode).where(EnrollmentCode.code == code.code, EnrollmentCode.uses_left > 0)
                  .values(uses_left=EnrollmentCode.uses_left - 1)).rowcount != 1:
        raise HTTPException(403, "enrollment code is used up")
    email = body.user_email.strip().lower()
    if "@" not in email:
        raise HTTPException(422, "a valid email is required")
    user = db.query(User).filter_by(email=email).first()
    if user is not None and user.role_id != code.role_id:
        raise HTTPException(403, "this code is for a different role than the existing account; ask an administrator")
    if user is not None and (code.email or "").lower() != email and \
            db.query(Device).filter_by(user_id=user.id, revoked=False).count() > 0:
        raise HTTPException(403, "this account already has an enrolled Mac; ask an administrator for a personal code for it")
    if code.email and code.email.lower() != email:
        raise HTTPException(403, "this enrollment code belongs to another person")
    if user is None:
        user = User(email=email, name=email.split("@")[0], role_id=code.role_id)
        db.add(user)
        db.flush()
    token, h = new_device_token()
    dev = Device(user_id=user.id, hostname=body.hostname[:200], platform=body.platform[:200], token_hash=h, last_seen=time.time())
    db.add(dev)
    db.commit()
    bus.publish("admin", {"type": "device_enrolled", "device_id": dev.id, "user": email, "hostname": dev.hostname})
    return {"device_id": dev.id, "device_token": token, "public_key": public_key_b64(), "org_name": settings.org_name,
            "user": {"email": user.email, "role": user.role_id}}


def _enroll_with_invite(body: EnrollIn, db: Session) -> dict:
    from sqlalchemy import update
    now = time.time()
    inv = db.query(Invite).filter_by(key_hash=hash_key(body.invite)).first()
    if inv is None or inv.revoked or (inv.expires_at and inv.expires_at < now) or "#deleted-" in inv.user.email:
        raise HTTPException(403, "invite key is invalid, expired or revoked; ask your administrator for a new one")
    # atomic: two Macs racing with the same key can't both win
    if inv.used_at or db.execute(update(Invite).where(Invite.id == inv.id, Invite.used_at == 0, Invite.revoked.is_(False))
                                 .values(used_at=now, used_hostname=body.hostname[:200])).rowcount != 1:
        raise HTTPException(403, "this invite key was already used; if that wasn't you, tell your administrator")
    user = inv.user
    token, h = new_device_token()
    dev = Device(user_id=user.id, hostname=body.hostname[:200], platform=body.platform[:200], token_hash=h, last_seen=now)
    db.add(dev)
    db.flush()
    inv.used_device_id = dev.id
    db.commit()
    bus.publish("admin", {"type": "device_enrolled", "device_id": dev.id, "user": user.email, "hostname": dev.hostname})
    return {"device_id": dev.id, "device_token": token, "public_key": public_key_b64(), "org_name": settings.org_name,
            "user": {"email": user.email, "role": user.role_id}}


@router.get("/device/profiles")
def device_profiles(dev: Device = Depends(current_device), db: Session = Depends(get_db)):
    return signed_bundle(db, dev)


@router.get("/device/stream")
async def device_stream(dev: Device = Depends(current_device)):
    q = bus.subscribe("devices")

    async def gen():
        try:
            async for chunk in sse(q, {"type": "hello", "device_id": dev.id}):
                yield chunk
        finally:
            bus.unsubscribe("devices", q)
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class Heartbeat(BaseModel):
    status: dict[str, Any] = Field(default_factory=dict)


@router.post("/device/heartbeat")
def heartbeat(body: Heartbeat, dev: Device = Depends(current_device), db: Session = Depends(get_db)):
    dev.status = body.status
    dev.last_seen = time.time()
    db.commit()
    return {"ok": True}


class EventsIn(BaseModel):
    events: list[dict[str, Any]]


@router.post("/events")
def ingest(body: EventsIn, dev: Device = Depends(current_device), db: Session = Depends(get_db)):
    n = 0
    for e in body.events[:500]:
        if not isinstance(e, dict):
            continue
        eid = str(e.get("id") or "")[:64]
        if not eid or db.get(Event, eid):
            continue
        try:
            float(e.get("ts") or 0), float(e.get("ms") or 0)
        except (TypeError, ValueError):
            e = {**e, "ts": time.time(), "ms": 0}  # one malformed field must not poison the whole batch
        if not isinstance(e.get("input"), dict):
            e = {**e, "input": {"value": str(e.get("input"))[:500]}}
        verdict = e.get("verdict") if e.get("verdict") in {"allow", "ask", "block"} else None
        ev = Event(id=eid, device_id=dev.id, ts=float(e.get("ts") or time.time()), user_email=dev.user.email,
                   agent=str(e.get("agent", ""))[:64], event=str(e.get("event", "pre_tool"))[:32], tool=str(e.get("tool", ""))[:128],
                   verdict=verdict, layer=str(e.get("layer", ""))[:64], rule=str(e.get("rule", ""))[:128],
                   severity=str(e.get("severity", "info"))[:16], reason=str(e.get("reason", ""))[:2000],
                   profile=str(e.get("profile", ""))[:64], session=str(e.get("session", ""))[:128], task=str(e.get("task", ""))[:1000],
                   cwd=str(e.get("cwd", ""))[:500], input=e.get("input") or {}, ms=float(e.get("ms") or 0),
                   hash=str(e.get("hash", "")), prev=str(e.get("prev", "")))
        db.add(ev)
        n += 1
        bus.publish("admin", {"type": "event", "event": _event_json(ev, dev)})
    db.commit()
    return {"stored": n}


def _event_json(e: Event, dev: Device | None = None) -> dict:
    return {"id": e.id, "ts": e.ts, "device_id": e.device_id, "hostname": dev.hostname if dev else "", "user": e.user_email,
            "agent": e.agent, "event": e.event, "tool": e.tool, "verdict": e.verdict, "layer": e.layer, "rule": e.rule,
            "severity": e.severity, "reason": e.reason, "profile": e.profile, "session": e.session, "task": e.task, "cwd": e.cwd,
            "input": e.input, "ms": e.ms}


class JudgeIn(BaseModel):
    nonce: str = ""
    profile_id: str = ""
    task: str = ""
    action: dict[str, Any]
    content: str | None = None
    facts: dict[str, Any] = Field(default_factory=dict)


def corp_config(db: Session) -> dict:
    kv = db.get(KV, "corporate_model")
    return kv.value if kv else {"url": settings.corp_model_url, "model": settings.corp_model, "api_key": "", "enabled": True}


@router.post("/judge")
async def judge(body: JudgeIn, dev: Device = Depends(current_device), db: Session = Depends(get_db)):
    if not limiter.allow(f"judge:{dev.id}", settings.judge_rpm):
        raise HTTPException(429, "too many judge requests from this device; slow down")
    cfg = corp_config(db)
    if not cfg.get("enabled", True):
        raise HTTPException(503, "the corporate judge is disabled by the administrator")
    if body.profile_id and body.profile_id not in {p["id"] for p in resolve(db, dev)["profiles"]}:
        # only this device's own profiles: another role's policy text must never reach the model on its behalf
        raise HTTPException(403, "this profile is not assigned to this device")
    prof = db.get(Profile, body.profile_id) if body.profile_id else None
    instructions = ((prof.data.get("judge") or {}).get("instructions", "") if prof else "")
    try:
        out = await corporate.judge(cfg, body.task, body.action, body.content, instructions, body.facts, settings.corp_timeout_s)
        return {**out, "signed": sign({**out, "nonce": body.nonce, "device_id": dev.id})}
    except Exception as e:
        raise HTTPException(502, f"corporate model unavailable: {type(e).__name__}: {str(e)[:200]}")


class ApprovalIn(BaseModel):
    agent: str
    tool: str
    summary: str
    input: dict[str, Any] = Field(default_factory=dict)
    cwd: str = ""
    session_id: str = ""
    profile_id: str = ""
    rule: str = ""


@router.post("/approvals")
def create_approval(body: ApprovalIn, dev: Device = Depends(current_device), db: Session = Depends(get_db)):
    if not limiter.allow(f"approvals:{dev.id}", settings.approvals_rpm):
        raise HTTPException(429, "too many approval requests from this device; slow down")
    a = Approval(device_id=dev.id, user_email=dev.user.email, agent=body.agent, tool=body.tool, summary=body.summary[:2000],
                 input=body.input, cwd=body.cwd[:500], profile_id=body.profile_id, rule=body.rule)
    db.add(a)
    db.commit()
    bus.publish("admin", {"type": "approval", "approval": approval_json(a, dev)})
    return {"id": a.id, "status": a.status}


def approval_json(a: Approval, dev: Device | None = None) -> dict:
    return {"id": a.id, "device_id": a.device_id, "hostname": dev.hostname if dev else "", "user": a.user_email, "agent": a.agent,
            "tool": a.tool, "summary": a.summary, "input": a.input, "cwd": a.cwd, "profile_id": a.profile_id, "rule": a.rule,
            "status": a.status, "created_at": a.created_at, "decided_at": a.decided_at, "decided_by": a.decided_by, "note": a.note}


@router.get("/approvals/{aid}")
def get_approval(aid: str, nonce: str = "", dev: Device = Depends(current_device), db: Session = Depends(get_db)):
    a = db.get(Approval, aid)
    if a is None or a.device_id != dev.id:
        raise HTTPException(404, "not found")
    if a.status == "pending" and time.time() - a.created_at > 900:
        a.status, a.decided_by = "expired", "timeout"
        db.commit()
    j = approval_json(a)
    return {**j, "signed": sign({"id": a.id, "status": a.status, "decided_by": a.decided_by, "nonce": nonce, "device_id": dev.id})}


@router.get("/public-key")
def public_key():
    return {"alg": "Ed25519", "public_key": public_key_b64()}


@router.get("/health")
async def health():
    await asyncio.sleep(0)
    return {"ok": True, "org": settings.org_name}
