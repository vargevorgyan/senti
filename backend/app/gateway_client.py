"""The backend's side of the gateway runner (see app.gateway_ops). Any failure raises RunnerUnavailable, and callers block."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from .config import settings


class RunnerUnavailable(Exception):
    pass


async def call(req: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
    if settings.gateway_runner:
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(settings.gateway_runner, limit=8 * 1024 * 1024), 5)
            writer.write(json.dumps(req).encode() + b"\n")
            await writer.drain()
            line = await asyncio.wait_for(reader.readline(), timeout)
            writer.close()
            resp = json.loads(line)
        except (OSError, asyncio.TimeoutError, ValueError) as e:
            raise RunnerUnavailable(f"the gateway runner is unavailable ({type(e).__name__})") from e
    elif settings.gateway_in_process:
        from . import gateway_ops  # tests and development only (SENTI_GATEWAY_IN_PROCESS=true)
        resp = json.loads(json.dumps(await asyncio.to_thread(gateway_ops.handle, req), default=str))
    else:
        raise RunnerUnavailable("the gateway runner is not configured (SENTI_GATEWAY_RUNNER)")
    if not isinstance(resp, dict) or "error" in resp:
        raise RunnerUnavailable(f"the gateway runner refused the call ({(resp or {}).get('error', 'bad answer')})")
    return resp


class RunnerOps:
    """What the policy compiler needs from the shared data, answered by the runner."""

    async def inventory(self) -> str:
        return (await call({"op": "inventory"}))["text"]

    async def db_schema(self) -> dict[str, set[str]]:
        return {t: set(c) for t, c in (await call({"op": "db_schema"}))["schema"].items()}

    async def evaluate(self, policy: dict, examples: list[dict]) -> list[dict]:
        return (await call({"op": "evaluate", "policy": policy, "examples": examples}, timeout=120))["results"]
