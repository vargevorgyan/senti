"""Admin panel API (admin JWT auth)."""
from __future__ import annotations

import csv
import io
import re
import secrets
import time
from collections import Counter
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import corporate
from ..bundle import bump, profile_doc, resolve
from ..bus import bus, sse
from ..config import settings
from ..db import get_db
from ..models import KV, Admin, Approval, ChangeLog, Device, EnrollmentCode, Event, Profile, Role, User
from ..seed import BASE_FEATURES
from .device import _event_json, approval_json, corp_config

router = APIRouter(prefix="/api/v1/admin")
from ..security import current_admin  # noqa: E402

Auth = Depends(current_admin)
ONLINE_S = 90


# ---------------------------------------------------------------- schemas
Otherwise = Literal["allow", "ask", "block", "judge"]


class FileRules(BaseModel):
    allow: list[str] = []
    deny: list[str] = []
    ask: list[str] = []
    write: Literal["allow", "ask", "block"] | None = None
    outside_allow: Literal["ask", "block", "allow"] | None = None


class NetRules(BaseModel):
    allow: list[str] = []
    deny: list[str] = []
    ask: list[str] = []
    otherwise: Otherwise = "judge"


class ShellRules(BaseModel):
    allow: list[str] = []
    deny: list[str] = []
    ask: list[str] = []
    otherwise: Otherwise = "judge"


class McpRules(BaseModel):
    allow: list[str] = []
    deny: list[str] = []
    otherwise: Otherwise = "judge"


class Rules(BaseModel):
    files: FileRules = FileRules()
    network: NetRules = NetRules()
    shell: ShellRules = ShellRules()
    mcp: McpRules = McpRules()
    packages: Literal["check_supply_chain", "allow", "ask", "block"] = "check_supply_chain"


class JudgeCfg(BaseModel):
    mode: Literal["local", "corporate", "local_then_corporate", "none"] = "local"
    instructions: str = ""
    send_to_corporate: Literal["metadata_only", "with_redacted_content", "full"] = "metadata_only"


class ProfileData(BaseModel):
    applies_to: dict[str, list[str]] = Field(default_factory=lambda: {"roles": [], "agents": []})
    rules: Rules = Rules()
    judge: JudgeCfg = JudgeCfg()
    on_backend_unreachable: Literal["strict_local", "cached"] = "strict_local"
    approvals: dict[str, str] = Field(default_factory=lambda: {"ask_goes_to": "user"})
    features: dict[str, bool] = Field(default_factory=lambda: dict(BASE_FEATURES))
    agent_overrides: dict[str, dict[str, Any]] = {}


class ProfileIn(BaseModel):
    id: str | None = None
    name: str
    description: str = ""
    priority: int = 100
    data: ProfileData = ProfileData()


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", s.lower()).strip("-")[:60] or "profile"


def profile_json(p: Profile, db: Session | None = None) -> dict:
    d = {"id": p.id, "name": p.name, "description": p.description, "priority": p.priority, "version": p.version, "data": p.data,
         "updated_at": p.updated_at, "updated_by": p.updated_by}
    return d


# ---------------------------------------------------------------- overview
@router.get("/overview")
def overview(admin: Admin = Auth, db: Session = Depends(get_db)):
    now = time.time()
    since = now - 86400
    evs = db.query(Event).filter(Event.ts >= since, Event.verdict.isnot(None)).all()
    by_verdict = Counter(e.verdict for e in evs)
    by_agent = Counter(e.agent for e in evs)
    by_layer = Counter((e.layer or "").split("-")[0] for e in evs)
    llm = [e for e in evs if (e.layer or "").startswith("L3")]
    rules = Counter(e.rule for e in evs if e.verdict in {"block", "ask"} and e.rule)
    hours = [0] * 24
    blocks = [0] * 24
    for e in evs:
        i = min(23, int((e.ts - since) // 3600))
        hours[i] += 1
        if e.verdict == "block":
            blocks[i] += 1
    devices = db.query(Device).filter_by(revoked=False).all()
    recent_blocks = db.query(Event).filter(Event.verdict == "block").order_by(Event.ts.desc()).limit(8).all()
    ms = sorted(e.ms for e in evs if e.ms)
    return {
        "org": settings.org_name,
        "devices": {"total": len(devices), "online": sum(1 for d in devices if now - d.last_seen < ONLINE_S)},
        "users": db.query(func.count(User.id)).scalar(),
        "profiles": db.query(func.count(Profile.id)).scalar(),
        "events_24h": len(evs),
        "by_verdict": {v: by_verdict.get(v, 0) for v in ("allow", "ask", "block")},
        "by_agent": dict(by_agent.most_common()),
        "by_layer": dict(by_layer.most_common()),
        "llm_share": round(len(llm) / len(evs), 3) if evs else 0,
        "latency_ms": {"p50": ms[len(ms) // 2] if ms else 0, "p95": ms[int(len(ms) * 0.95)] if ms else 0},
        "top_rules": rules.most_common(6),
        "timeline": {"start": since, "hours": hours, "blocks": blocks},
        "pending_approvals": db.query(func.count(Approval.id)).filter_by(status="pending").scalar(),
        "recent_blocks": [_event_json(e) for e in recent_blocks],
    }


# ---------------------------------------------------------------- profiles
@router.get("/profiles")
def list_profiles(admin: Admin = Auth, db: Session = Depends(get_db)):
    return [profile_json(p) for p in db.query(Profile).order_by(Profile.priority.desc(), Profile.name).all()]


@router.get("/profiles/{pid}")
def get_profile(pid: str, admin: Admin = Auth, db: Session = Depends(get_db)):
    p = db.get(Profile, pid)
    if not p:
        raise HTTPException(404, "profile not found")
    return profile_json(p)


@router.post("/profiles", status_code=201)
def create_profile(body: ProfileIn, admin: Admin = Auth, db: Session = Depends(get_db)):
    pid = _slug(body.id or body.name)
    if db.get(Profile, pid):
        raise HTTPException(409, f"a profile with id '{pid}' already exists")
    p = Profile(id=pid, name=body.name, description=body.description, priority=body.priority,
                data=body.data.model_dump(exclude_none=True), updated_by=admin.email)
    db.add(p)
    db.commit()
    bump(db, admin.email, "profile.create", pid)
    return profile_json(p)


@router.put("/profiles/{pid}")
def update_profile(pid: str, body: ProfileIn, admin: Admin = Auth, db: Session = Depends(get_db)):
    p = db.get(Profile, pid)
    if not p:
        raise HTTPException(404, "profile not found")
    before = profile_doc(p)
    p.name, p.description, p.priority = body.name, body.description, body.priority
    p.data = body.data.model_dump(exclude_none=True)
    p.version += 1
    p.updated_at, p.updated_by = time.time(), admin.email
    db.commit()
    bump(db, admin.email, "profile.update", pid, {"version": p.version, "judge_mode": p.data["judge"]["mode"],
                                                 "before_mode": (before.get("judge") or {}).get("mode")})
    return profile_json(p)


@router.post("/profiles/{pid}/duplicate", status_code=201)
def duplicate_profile(pid: str, admin: Admin = Auth, db: Session = Depends(get_db)):
    p = db.get(Profile, pid)
    if not p:
        raise HTTPException(404, "profile not found")
    nid = f"{pid}-copy"
    i = 2
    while db.get(Profile, nid):
        nid, i = f"{pid}-copy-{i}", i + 1
    import copy
    data = copy.deepcopy(p.data)
    data["applies_to"] = {"roles": [], "agents": []}
    q = Profile(id=nid, name=p.name + " (copy)", description=p.description, priority=p.priority - 1, data=data,
                updated_by=admin.email)
    db.add(q)
    db.commit()
    bump(db, admin.email, "profile.duplicate", nid, {"from": pid})
    return profile_json(q)


@router.delete("/profiles/{pid}")
def delete_profile(pid: str, admin: Admin = Auth, db: Session = Depends(get_db)):
    p = db.get(Profile, pid)
    if not p:
        raise HTTPException(404, "profile not found")
    if db.query(Profile).count() <= 1:
        raise HTTPException(400, "keep at least one profile")
    for u in db.query(User).all():
        if pid in (u.agent_profiles or {}).values():
            u.agent_profiles = {k: v for k, v in u.agent_profiles.items() if v != pid}
    db.delete(p)
    db.commit()
    bump(db, admin.email, "profile.delete", pid)
    return {"ok": True}


# ---------------------------------------------------------------- roles
class RoleIn(BaseModel):
    id: str | None = None
    name: str
    description: str = ""


@router.get("/roles")
def list_roles(admin: Admin = Auth, db: Session = Depends(get_db)):
    counts = dict(db.query(User.role_id, func.count(User.id)).group_by(User.role_id).all())
    return [{"id": r.id, "name": r.name, "description": r.description, "users": counts.get(r.id, 0)} for r in db.query(Role).all()]


@router.post("/roles", status_code=201)
def create_role(body: RoleIn, admin: Admin = Auth, db: Session = Depends(get_db)):
    rid = _slug(body.id or body.name)
    if db.get(Role, rid):
        raise HTTPException(409, "role exists")
    db.add(Role(id=rid, name=body.name, description=body.description))
    db.commit()
    bump(db, admin.email, "role.create", rid)
    return {"id": rid, "name": body.name, "description": body.description, "users": 0}


@router.put("/roles/{rid}")
def update_role(rid: str, body: RoleIn, admin: Admin = Auth, db: Session = Depends(get_db)):
    r = db.get(Role, rid)
    if not r:
        raise HTTPException(404, "role not found")
    r.name, r.description = body.name, body.description
    db.commit()
    bump(db, admin.email, "role.update", rid)
    return {"id": r.id, "name": r.name, "description": r.description}


@router.delete("/roles/{rid}")
def delete_role(rid: str, admin: Admin = Auth, db: Session = Depends(get_db)):
    r = db.get(Role, rid)
    if not r:
        raise HTTPException(404, "role not found")
    if db.query(User).filter_by(role_id=rid).count():
        raise HTTPException(400, "move this role's users to another role first")
    db.delete(r)
    db.commit()
    bump(db, admin.email, "role.delete", rid)
    return {"ok": True}


# ---------------------------------------------------------------- users
class UserIn(BaseModel):
    email: str
    name: str = ""
    role_id: str = "engineering"
    agent_profiles: dict[str, str] = {}


def user_json(u: User, db: Session) -> dict:
    devs = db.query(Device).filter_by(user_id=u.id, revoked=False).all()
    return {"id": u.id, "email": u.email, "name": u.name, "role_id": u.role_id, "agent_profiles": u.agent_profiles or {},
            "devices": len(devs), "online": any(time.time() - d.last_seen < ONLINE_S for d in devs), "created_at": u.created_at}


@router.get("/users")
def list_users(admin: Admin = Auth, db: Session = Depends(get_db)):
    return [user_json(u, db) for u in db.query(User).order_by(User.email).all()]


@router.post("/users", status_code=201)
def create_user(body: UserIn, admin: Admin = Auth, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if db.query(User).filter_by(email=email).first():
        raise HTTPException(409, "user exists")
    if not db.get(Role, body.role_id):
        raise HTTPException(422, "unknown role")
    u = User(email=email, name=body.name or email.split("@")[0], role_id=body.role_id, agent_profiles=body.agent_profiles)
    db.add(u)
    db.commit()
    bump(db, admin.email, "user.create", email)
    return user_json(u, db)


@router.put("/users/{uid}")
def update_user(uid: int, body: UserIn, admin: Admin = Auth, db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "user not found")
    if not db.get(Role, body.role_id):
        raise HTTPException(422, "unknown role")
    for pid in body.agent_profiles.values():
        if pid and not db.get(Profile, pid):
            raise HTTPException(422, f"unknown profile {pid}")
    u.name, u.role_id = body.name, body.role_id
    u.agent_profiles = {k: v for k, v in body.agent_profiles.items() if v}
    db.commit()
    bump(db, admin.email, "user.update", u.email, {"role": u.role_id, "agent_profiles": u.agent_profiles})
    return user_json(u, db)


@router.delete("/users/{uid}")
def delete_user(uid: int, admin: Admin = Auth, db: Session = Depends(get_db)):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "user not found")
    for d in db.query(Device).filter_by(user_id=uid).all():
        d.revoked = True
    db.commit()
    if db.query(Device).filter_by(user_id=uid).count() == 0:
        db.delete(u)
        db.commit()
    bump(db, admin.email, "user.delete", u.email)
    return {"ok": True}


@router.get("/users/{uid}/effective")
def user_effective(uid: int, admin: Admin = Auth, db: Session = Depends(get_db)):
    """Which profile each agent of this user runs under (what their devices receive)."""
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "user not found")
    fake = Device(id="preview", user_id=u.id, token_hash="-")
    fake.user = u
    b = resolve(db, fake)
    return {"default": b["default"], "assignments": b["assignments"], "version": b["version"]}


# ---------------------------------------------------------------- devices
def device_json(d: Device) -> dict:
    st = d.status or {}
    return {"id": d.id, "user": d.user.email if d.user else "", "hostname": d.hostname, "platform": d.platform,
            "enrolled_at": d.enrolled_at, "last_seen": d.last_seen, "online": (time.time() - d.last_seen) < ONLINE_S and not d.revoked,
            "revoked": d.revoked, "engine_version": st.get("version"), "local_judge": (st.get("local_judge") or {}).get("state"),
            "profiles_source": (st.get("profiles") or {}).get("source"), "bundle_version": (st.get("profiles") or {}).get("bundle_version"),
            "stats": st.get("stats") or {}}


@router.get("/devices")
def list_devices(admin: Admin = Auth, db: Session = Depends(get_db)):
    return [device_json(d) for d in db.query(Device).order_by(Device.last_seen.desc()).all()]


@router.post("/devices/{did}/revoke")
def revoke_device(did: str, admin: Admin = Auth, db: Session = Depends(get_db)):
    d = db.get(Device, did)
    if not d:
        raise HTTPException(404, "device not found")
    d.revoked = True
    db.commit()
    bump(db, admin.email, "device.revoke", did)
    return device_json(d)


# ---------------------------------------------------------------- enrollment codes
class CodeIn(BaseModel):
    role_id: str = "engineering"
    uses: int = 10
    days: int = 7
    note: str = ""


@router.get("/enrollment-codes")
def list_codes(admin: Admin = Auth, db: Session = Depends(get_db)):
    return [{"code": c.code, "role_id": c.role_id, "uses_left": c.uses_left, "expires_at": c.expires_at, "note": c.note,
             "created_at": c.created_at} for c in db.query(EnrollmentCode).order_by(EnrollmentCode.created_at.desc()).all()]


@router.post("/enrollment-codes", status_code=201)
def create_code(body: CodeIn, admin: Admin = Auth, db: Session = Depends(get_db)):
    if not db.get(Role, body.role_id):
        raise HTTPException(422, "unknown role")
    code = "SENTI-" + secrets.token_hex(3).upper() + "-" + secrets.token_hex(3).upper()
    c = EnrollmentCode(code=code, role_id=body.role_id, uses_left=max(1, body.uses),
                       expires_at=time.time() + body.days * 86400 if body.days > 0 else 0, note=body.note)
    db.add(c)
    db.commit()
    db.add(ChangeLog(actor=admin.email, action="enrollment_code.create", target=code))
    db.commit()
    return {"code": c.code, "role_id": c.role_id, "uses_left": c.uses_left, "expires_at": c.expires_at, "note": c.note}


@router.delete("/enrollment-codes/{code}")
def delete_code(code: str, admin: Admin = Auth, db: Session = Depends(get_db)):
    c = db.get(EnrollmentCode, code)
    if c:
        db.delete(c)
        db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- events
def _filtered(db: Session, verdict: str, agent: str, user: str, q: str, device: str, severity: str, since: float):
    qry = db.query(Event)
    if verdict:
        qry = qry.filter(Event.verdict == verdict)
    if agent:
        qry = qry.filter(Event.agent == agent)
    if user:
        qry = qry.filter(Event.user_email == user)
    if device:
        qry = qry.filter(Event.device_id == device)
    if severity:
        qry = qry.filter(Event.severity == severity)
    if since:
        qry = qry.filter(Event.ts >= since)
    if q:
        like = f"%{q}%"
        qry = qry.filter((Event.reason.ilike(like)) | (Event.tool.ilike(like)) | (Event.rule.ilike(like)) | (Event.task.ilike(like)))
    return qry


@router.get("/events")
def list_events(verdict: str = "", agent: str = "", user: str = "", q: str = "", device: str = "", severity: str = "",
                since: float = 0, limit: int = 100, offset: int = 0, admin: Admin = Auth, db: Session = Depends(get_db)):
    qry = _filtered(db, verdict, agent, user, q, device, severity, since)
    total = qry.count()
    rows = qry.order_by(Event.ts.desc()).offset(offset).limit(min(limit, 500)).all()
    hosts = {d.id: d.hostname for d in db.query(Device).all()}
    return {"total": total, "items": [{**_event_json(e), "hostname": hosts.get(e.device_id, "")} for e in rows]}


@router.get("/events.csv")
def export_events(verdict: str = "", agent: str = "", user: str = "", q: str = "", admin: Admin = Auth, db: Session = Depends(get_db)):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["time", "user", "agent", "tool", "verdict", "layer", "rule", "severity", "reason", "input", "task"])
    for e in _filtered(db, verdict, agent, user, q, "", "", 0).order_by(Event.ts.desc()).limit(20000):
        w.writerow([time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(e.ts)), e.user_email, e.agent, e.tool, e.verdict, e.layer, e.rule,
                    e.severity, e.reason, str(e.input)[:500], e.task[:200]])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=senti-events.csv"})


@router.get("/stream")
async def admin_stream(admin: Admin = Auth):
    q = bus.subscribe("admin")

    async def gen():
        try:
            async for chunk in sse(q, {"type": "hello"}):
                yield chunk
        finally:
            bus.unsubscribe("admin", q)
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------- approvals
@router.get("/approvals")
def list_approvals(status: str = "", admin: Admin = Auth, db: Session = Depends(get_db)):
    qry = db.query(Approval)
    if status:
        qry = qry.filter_by(status=status)
    hosts = {d.id: d.hostname for d in db.query(Device).all()}
    now = time.time()
    out = []
    for a in qry.order_by(Approval.created_at.desc()).limit(200).all():
        if a.status == "pending" and now - a.created_at > 900:
            a.status, a.decided_by = "expired", "timeout"
        j = approval_json(a)
        j["hostname"] = hosts.get(a.device_id, "")
        out.append(j)
    db.commit()
    return out


class DecisionIn(BaseModel):
    decision: Literal["approve", "deny"]
    note: str = ""


@router.post("/approvals/{aid}/decide")
def decide_approval(aid: str, body: DecisionIn, admin: Admin = Auth, db: Session = Depends(get_db)):
    a = db.get(Approval, aid)
    if not a:
        raise HTTPException(404, "not found")
    if a.status != "pending":
        raise HTTPException(409, f"already {a.status}")
    a.status = "approved" if body.decision == "approve" else "denied"
    a.decided_at, a.decided_by, a.note = time.time(), admin.email, body.note
    db.add(ChangeLog(actor=admin.email, action=f"approval.{a.status}", target=aid, detail={"summary": a.summary[:200]}))
    db.commit()
    bus.publish("admin", {"type": "approval", "approval": approval_json(a)})
    return approval_json(a)


# ---------------------------------------------------------------- settings: corporate model
class CorpIn(BaseModel):
    url: str
    model: str
    api_key: str | None = None
    enabled: bool = True


@router.get("/settings/corporate-model")
def get_corp(admin: Admin = Auth, db: Session = Depends(get_db)):
    c = dict(corp_config(db))
    c["api_key_set"] = bool(c.pop("api_key", ""))
    return c


@router.put("/settings/corporate-model")
def put_corp(body: CorpIn, admin: Admin = Auth, db: Session = Depends(get_db)):
    kv = db.get(KV, "corporate_model")
    cur = dict(kv.value) if kv else {}
    new = {"url": body.url.strip(), "model": body.model.strip(), "enabled": body.enabled,
           "api_key": cur.get("api_key", "") if body.api_key is None else body.api_key}
    if kv:
        kv.value = new
    else:
        db.add(KV(key="corporate_model", value=new))
    db.add(ChangeLog(actor=admin.email, action="settings.corporate_model", target=new["model"], detail={"url": new["url"]}))
    db.commit()
    return {**{k: v for k, v in new.items() if k != "api_key"}, "api_key_set": bool(new["api_key"])}


class PlaygroundIn(BaseModel):
    profile_id: str = ""
    task: str = ""
    tool: str = "Bash"
    input: dict[str, Any] = Field(default_factory=lambda: {"command": "ls"})
    content: str | None = None


@router.post("/judge/playground")
async def playground(body: PlaygroundIn, admin: Admin = Auth, db: Session = Depends(get_db)):
    cfg = corp_config(db)
    prof = db.get(Profile, body.profile_id) if body.profile_id else None
    instructions = ((prof.data.get("judge") or {}).get("instructions", "") if prof else "")
    try:
        return await corporate.judge(cfg, body.task, {"tool": body.tool, **body.input}, body.content, instructions, None,
                                     settings.corp_timeout_s)
    except Exception as e:
        raise HTTPException(502, f"corporate model unavailable: {type(e).__name__}: {str(e)[:200]}")


@router.get("/corporate-model/status")
async def corp_status(admin: Admin = Auth, db: Session = Depends(get_db)):
    import httpx
    cfg = corp_config(db)
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(cfg["url"].rstrip("/") + "/models",
                            headers={"Authorization": f"Bearer {cfg['api_key']}"} if cfg.get("api_key") else {})
            r.raise_for_status()
            models = [m.get("id") for m in r.json().get("data", [])]
        return {"reachable": True, "models": models, "model_present": cfg["model"] in models, "enabled": cfg.get("enabled", True)}
    except Exception as e:
        return {"reachable": False, "error": f"{type(e).__name__}: {str(e)[:200]}", "enabled": cfg.get("enabled", True)}


# ---------------------------------------------------------------- change log
@router.get("/changelog")
def changelog(limit: int = 100, admin: Admin = Auth, db: Session = Depends(get_db)):
    return [{"id": c.id, "ts": c.ts, "actor": c.actor, "action": c.action, "target": c.target, "detail": c.detail}
            for c in db.query(ChangeLog).order_by(ChangeLog.ts.desc()).limit(min(limit, 500)).all()]
