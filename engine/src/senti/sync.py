"""Talking to the org backend: enrollment, signed profile sync (SSE push), audit upload, approvals.

Hooks never call the backend: only this background module does. If the backend is unreachable the
engine keeps the last verified profile and (per profile) runs in strict local mode.
"""
from __future__ import annotations

import asyncio
import json
import platform
import socket
import hashlib
import time

import httpx

import os

from .config import Settings, senti_home, tls_verify
from .devicekey import DeviceAuth
from .models import Action, Decision
from .profiles import bundle_to_set, save_cache, verify_bundle


def _auth(s: Settings) -> DeviceAuth:
    """Device token + a fresh signature by this Mac's device key on every request (devicekey.py)."""
    return DeviceAuth(s.device_token)


def _fingerprint(fp: str) -> str:
    return fp.lower().replace(":", "").replace("sha256", "").strip("= ")


def fetch_ca(backend_url: str) -> str | None:
    """The organization's own CA certificate, or None if the server has none (publicly trusted or older server).
    Fetched without verification on purpose: the caller accepts it only if its fingerprint matches the invite."""
    r = httpx.get(backend_url.rstrip("/") + "/api/v1/tls/ca", verify=False, timeout=10)  # noqa: S501 - checked by fingerprint
    if r.status_code == 404:
        return None
    r.raise_for_status()
    if r.text.count("BEGIN CERTIFICATE") != 1:
        raise RuntimeError("the server sent an unexpected certificate authority")
    return r.text


def trusted_ca_pem(backend_url: str, fingerprint: str) -> str | None:
    """The CA PEM if the server has one matching the fingerprint; None if the server has no CA. Raises on a mismatch."""
    import ssl
    pem = fetch_ca(backend_url)
    if pem is None:
        return None
    got = hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()
    if got != _fingerprint(fingerprint):
        raise RuntimeError(f"certificate fingerprint mismatch: server has {got}, invite says {_fingerprint(fingerprint)}. "
                           "Not joining: this may not be your company's server.")
    return pem


def pin_certificate(backend_url: str, fingerprint: str) -> tuple[str, str]:
    """Trust anchor for a self-signed server: its CA (preferred) or, for older servers, its certificate. The fingerprint
    from the invite must match. Returns (path, "ca" | "leaf")."""
    import ssl
    from urllib.parse import urlparse
    path_ca = senti_home() / "backend-ca.pem"
    pem = trusted_ca_pem(backend_url, fingerprint)
    kind = "ca"
    if pem is None:
        u = urlparse(backend_url)
        pem = ssl.get_server_certificate((u.hostname, u.port or 443), timeout=10)
        got = hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()
        if got != _fingerprint(fingerprint):
            raise RuntimeError(f"certificate fingerprint mismatch: server has {got}, expected {_fingerprint(fingerprint)}. Not enrolling.")
        kind = "leaf"
    path = path_ca if kind == "ca" else senti_home() / "backend-cert.pem"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(pem)
    return str(path), kind


def server_trust(backend_url: str, fingerprint: str, insecure_http: bool = False) -> Settings:
    """Settings (not saved) that trust the server the way the invite says: its CA, or normal public verification."""
    s = Settings.load()
    check_transport(backend_url, insecure_http)
    s.backend_cert, s.backend_cert_kind = ("", "")
    if fingerprint and backend_url.startswith("https"):
        s.backend_cert, s.backend_cert_kind = pin_certificate(backend_url, fingerprint)
    return s


def invite_info(backend_url: str, invite: str, s: Settings) -> dict:
    """What the server says the invite is for (company, person, role). Shown before joining; doesn't use up the key."""
    r = httpx.post(backend_url.rstrip("/") + "/api/v1/devices/invite-info", timeout=15, verify=tls_verify(s),
                   json={"invite": invite})
    if r.status_code >= 400:
        raise RuntimeError(f"the server refused the invite: {r.status_code} {r.text[:300]}")
    return r.json()


def check_transport(backend_url: str, insecure_http: bool = False) -> None:
    from urllib.parse import urlparse
    u = urlparse(backend_url)
    if u.scheme == "http" and u.hostname not in {"localhost", "127.0.0.1", "::1"} and not insecure_http:
        raise RuntimeError("refusing plain HTTP to a remote backend: use https:// (with --fingerprint for a self-signed "
                           "certificate) or pass --insecure-http for a lab setup")


def enroll(backend_url: str, code: str = "", user_email: str = "", fingerprint: str = "", insecure_http: bool = False,
           invite: str = "") -> Settings:
    """Join an organization with a personal invite key (preferred) or a legacy enrollment code + email."""
    from . import devicekey
    s = server_trust(backend_url, fingerprint, insecure_http)
    pub, key_type = devicekey.create()  # a new device key for this organization; the private half never leaves the Mac
    body = {"hostname": socket.gethostname(), "platform": f"{platform.system()} {platform.release()} {platform.machine()}",
            "device_key": pub, "key_type": key_type}
    body.update({"invite": invite} if invite else {"code": code, "user_email": user_email})
    r = httpx.post(backend_url.rstrip("/") + "/api/v1/devices/enroll", timeout=15, verify=tls_verify(s), json=body)
    if r.status_code >= 400:
        raise RuntimeError(f"enrollment failed: {r.status_code} {r.text[:300]}")
    d = r.json()
    s.backend_url = backend_url.rstrip("/")
    s.device_id, s.device_token = d["device_id"], d["device_token"]
    s.backend_public_key, s.org_name = d["public_key"], d.get("org_name", "")
    s.user_email = (d.get("user") or {}).get("email") or user_email
    s.device_key_type = key_type
    s.save()
    return s


async def fetch_profiles(engine) -> bool:
    s = engine.settings
    async with httpx.AsyncClient(timeout=10, verify=tls_verify(s)) as c:
        r = await c.get(s.backend_url + "/api/v1/device/profiles", auth=_auth(s))
        if r.status_code == 401:
            engine.backend_error = "device token rejected (device revoked?)"
            raise RuntimeError(engine.backend_error)
        r.raise_for_status()
        signed = r.json()
    payload = verify_bundle(signed, s.backend_public_key)  # raises on tampering
    if payload.get("device_id") not in (None, s.device_id):
        raise ValueError("profile bundle was signed for another device")
    if engine.profiles.source in {"backend", "cache"} and payload.get("version", 0) < engine.profiles.bundle_version:
        raise ValueError("profile bundle is older than the one already applied (rollback refused)")
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
            async with httpx.AsyncClient(timeout=httpx.Timeout(10, read=45), verify=tls_verify(s)) as c:
                async with c.stream("GET", s.backend_url + "/api/v1/device/stream", auth=_auth(s)) as r:
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
            async with httpx.AsyncClient(timeout=10, verify=tls_verify(s)) as c:
                r = await c.post(s.backend_url + "/api/v1/events", auth=_auth(s), json={"events": batch})
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
            async with httpx.AsyncClient(timeout=10, verify=tls_verify(s)) as c:
                await c.post(s.backend_url + "/api/v1/device/heartbeat", auth=_auth(s), json={"status": engine.status()})
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
        async with httpx.AsyncClient(timeout=10, verify=tls_verify(s)) as c:
            r = await c.post(s.backend_url + "/api/v1/approvals", auth=_auth(s), json=body)
            r.raise_for_status()
            aid = r.json()["id"]
            import secrets as _sec
            from .judge.remote import verified_payload
            while time.time() < deadline:
                await asyncio.sleep(1.5)
                nonce = _sec.token_urlsafe(12)
                r = await c.get(f"{s.backend_url}/api/v1/approvals/{aid}", auth=_auth(s), params={"nonce": nonce})
                if r.status_code == 200:
                    st = verified_payload(r.json(), s.backend_public_key, nonce, s.device_id)  # unsigned/forged → exception → block
                    if st.get("id") != aid:
                        return "block", "approval response for another request"
                    if st["status"] in {"approved", "denied"}:
                        return ("allow" if st["status"] == "approved" else "block"), st.get("decided_by") or "admin"
                    if st["status"] == "expired":
                        return "block", "request expired"
        return "block", "no decision in time"
    except Exception as e:
        return "block", f"approval service unreachable: {type(e).__name__}"
