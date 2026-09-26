"""Talking to the org backend: enrollment, signed profile sync (SSE push), audit upload, approvals.

Hooks never call the backend: only this background module does. If the backend is unreachable the
engine keeps the last verified profile and (per profile) runs in strict local mode.
"""
from __future__ import annotations

import asyncio
import json
import platform
import socket
import time

import httpx

from .config import Settings
from .models import Action, Decision
from .profiles import bundle_to_set, save_cache, verify_bundle


def _headers(s: Settings) -> dict:
    return {"Authorization": f"Bearer {s.device_token}"}


def enroll(backend_url: str, code: str, user_email: str) -> Settings:
    s = Settings.load()
    r = httpx.post(backend_url.rstrip("/") + "/api/v1/devices/enroll", timeout=15,
                   json={"code": code, "user_email": user_email, "hostname": socket.gethostname(),
                         "platform": f"{platform.system()} {platform.release()} {platform.machine()}"})
    if r.status_code >= 400:
        raise RuntimeError(f"enrollment failed: {r.status_code} {r.text[:300]}")
    d = r.json()
    s.backend_url = backend_url.rstrip("/")
    s.device_id, s.device_token = d["device_id"], d["device_token"]
    s.backend_public_key, s.org_name, s.user_email = d["public_key"], d.get("org_name", ""), user_email
    s.save()
    return s


async def fetch_profiles(engine) -> bool:
    s = engine.settings
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(s.backend_url + "/api/v1/device/profiles", headers=_headers(s))
        if r.status_code == 401:
            engine.backend_error = "device token rejected (device revoked?)"
            raise RuntimeError(engine.backend_error)
        r.raise_for_status()
        signed = r.json()
    payload = verify_bundle(signed, s.backend_public_key)  # raises on tampering
    ps = bundle_to_set(payload)
    changed = ps.bundle_version != engine.profiles.bundle_version or engine.profiles.source != "backend"
    engine.profiles = ps
    engine.cache.clear()  # policy changed: earlier LLM verdicts may no longer apply
    save_cache(signed)
    engine.backend_state, engine.backend_error = "online", ""
    return changed


async def profile_loop(engine) -> None:
    """Initial fetch, then listen to the SSE stream; reconnect with backoff; poll as a fallback."""
    s = engine.settings
    backoff = 1.0
    while True:
        try:
            await fetch_profiles(engine)
            backoff = 1.0
            async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=45)) as c:
                async with c.stream("GET", s.backend_url + "/api/v1/device/stream", headers=_headers(s)) as r:
                    r.raise_for_status()
                    async for line in r.aiter_lines():
                        if line.startswith("data:"):
                            try:
                                ev = json.loads(line[5:].strip())
                            except Exception:
                                continue
                            if ev.get("type") in {"profiles_changed", "assignments_changed"}:
                                await fetch_profiles(engine)
                            elif ev.get("type") == "honeytokens_changed":
                                engine.honey.reload()
                        engine.backend_state = "online"
        except asyncio.CancelledError:
            raise
        except Exception as e:
            engine.backend_state = "unreachable"
            engine.backend_error = engine.backend_error or f"{type(e).__name__}: {e}"[:200]
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
            engine.backend_error = ""


async def upload_loop(engine, interval: float = 3.0) -> None:
    s = engine.settings
    while True:
        await asyncio.sleep(interval)
        try:
            batch, offset = engine.audit.pending(200)
            if not batch:
                continue
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.post(s.backend_url + "/api/v1/events", headers=_headers(s), json={"events": batch})
                r.raise_for_status()
            engine.audit.mark_uploaded(offset)
        except asyncio.CancelledError:
            raise
        except Exception:
            continue  # stays queued locally; retried next round


async def heartbeat_loop(engine, interval: float = 30.0) -> None:
    s = engine.settings
    while True:
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                await c.post(s.backend_url + "/api/v1/device/heartbeat", headers=_headers(s), json={"status": engine.status()})
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(interval)


async def request_approval(s: Settings, a: Action, d: Decision, profile: dict, timeout: int) -> tuple[str, str]:
    """Route an 'ask' to the owner/admin via the backend and wait. Timeout or error → block (fail closed)."""
    body = {"agent": a.agent, "tool": a.tool, "summary": d.reason, "input": {k: str(v)[:1500] for k, v in a.input.items()},
            "cwd": a.cwd, "session_id": a.session_id, "profile_id": profile.get("id"), "rule": d.rule}
    deadline = time.time() + timeout
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(s.backend_url + "/api/v1/approvals", headers=_headers(s), json=body)
            r.raise_for_status()
            aid = r.json()["id"]
            while time.time() < deadline:
                await asyncio.sleep(1.5)
                r = await c.get(f"{s.backend_url}/api/v1/approvals/{aid}", headers=_headers(s))
                if r.status_code == 200:
                    st = r.json()
                    if st["status"] in {"approved", "denied"}:
                        return ("allow" if st["status"] == "approved" else "block"), st.get("decided_by") or "admin"
        return "block", "no decision in time"
    except Exception as e:
        return "block", f"approval service unreachable: {type(e).__name__}"
