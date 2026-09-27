"""Corporate judge: the org backend's judge gateway, which forwards to the company's model."""
from __future__ import annotations

import time

import httpx

from .base import JudgeResult


def verified_payload(resp: dict, public_key: str, nonce: str, device_id: str) -> dict:
    """The org-signed part of a backend response; raises if the signature, nonce or device doesn't match."""
    from ..profiles import verify_bundle
    signed = resp.get("signed")
    if not isinstance(signed, dict):
        raise ValueError("unsigned response from the organization server")
    body = verify_bundle(signed, public_key)
    if body.get("nonce") != nonce or (device_id and body.get("device_id") not in (None, device_id)):
        raise ValueError("replayed or misdirected response")
    return body


class RemoteJudge:
    def __init__(self, backend_url: str, device_token: str, timeout: float = 20.0, verify=True, public_key: str = "",
                 device_id: str = ""):
        self.verify = verify
        self.public_key = public_key
        self.device_id = device_id
        self.url = backend_url.rstrip("/") + "/api/v1/judge"
        self.token = device_token
        self.timeout = timeout
        self.last_error = ""
        self.last_ok = 0.0

    async def decide(self, profile_id: str, task: str, action: dict, script: str | None, facts: dict | None) -> JudgeResult:
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout, verify=self.verify) as c:
                import secrets
                nonce = secrets.token_urlsafe(16)
                from ..devicekey import DeviceAuth
                r = await c.post(self.url, auth=DeviceAuth(self.token),  # token + device-key signature
                                 json={"profile_id": profile_id, "task": task, "action": action, "content": script,
                                       "facts": facts or {}, "nonce": nonce})
                r.raise_for_status()
                d = verified_payload(r.json(), self.public_key, nonce, self.device_id)
            self.last_ok = time.time()
            return JudgeResult(d["verdict"], d.get("reason", ""), d.get("p") or {}, "corporate", d.get("model", ""),
                               round((time.perf_counter() - t0) * 1000))
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            return JudgeResult("ask", "", source="corporate", error=self.last_error, ms=round((time.perf_counter() - t0) * 1000))
