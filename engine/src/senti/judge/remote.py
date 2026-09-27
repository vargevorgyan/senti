"""Corporate judge: the org backend's judge gateway, which forwards to the company's model."""
from __future__ import annotations

import time

import httpx

from .base import JudgeResult


class RemoteJudge:
    def __init__(self, backend_url: str, device_token: str, timeout: float = 20.0, verify=True):
        self.verify = verify
        self.url = backend_url.rstrip("/") + "/api/v1/judge"
        self.token = device_token
        self.timeout = timeout
        self.last_error = ""
        self.last_ok = 0.0

    async def decide(self, profile_id: str, task: str, action: dict, script: str | None, facts: dict | None) -> JudgeResult:
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout, verify=self.verify) as c:
                r = await c.post(self.url, headers={"Authorization": f"Bearer {self.token}"},
                                 json={"profile_id": profile_id, "task": task, "action": action, "content": script,
                                       "facts": facts or {}})
                r.raise_for_status()
                d = r.json()
            self.last_ok = time.time()
            return JudgeResult(d["verdict"], d.get("reason", ""), d.get("p") or {}, "corporate", d.get("model", ""),
                               round((time.perf_counter() - t0) * 1000))
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            return JudgeResult("ask", "", source="corporate", error=self.last_error, ms=round((time.perf_counter() - t0) * 1000))
