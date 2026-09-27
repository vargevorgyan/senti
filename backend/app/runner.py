"""The isolated gateway runner: `python -m app.runner` in its own container.

It listens on a Unix socket in a volume shared only with the backend, and performs gateway calls (app.gateway_ops) on the
shared folder. The container has no network, no secrets, no admin database and runs as an unprivileged user with a
read-only filesystem, so even a command that escapes the gateway rules finds nothing worth taking.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

from .gateway_ops import handle

SOCKET = os.environ.get("SENTI_GATEWAY_RUNNER", "/run/senti-runner/runner.sock")
MAX_LINE = 8 * 1024 * 1024
PARALLEL = asyncio.Semaphore(4)


async def serve_one(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        line = await reader.readline()
        try:
            req = json.loads(line)
            if not isinstance(req, dict):
                raise ValueError("not an object")
        except ValueError:
            resp = {"error": "bad request"}
        else:
            async with PARALLEL:
                try:
                    resp = await asyncio.to_thread(handle, req)
                except Exception as e:  # never leak a traceback; the backend blocks the call
                    resp = {"error": f"{type(e).__name__}"}
        writer.write(json.dumps(resp, default=str).encode() + b"\n")
        await writer.drain()
    except (ConnectionError, asyncio.LimitOverrunError, ValueError):
        pass
    finally:
        writer.close()


async def main() -> None:
    if os.path.exists(SOCKET):
        os.unlink(SOCKET)
    os.makedirs(os.path.dirname(SOCKET), exist_ok=True)
    old = os.umask(0o077)  # only this user (the backend runs as the same unprivileged user) may connect
    server = await asyncio.start_unix_server(serve_one, path=SOCKET, limit=MAX_LINE)
    os.umask(old)
    print(f"senti gateway runner listening on {SOCKET}", file=sys.stderr, flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
