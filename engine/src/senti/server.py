"""The local engine server: FastAPI over a Unix domain socket (mode 0600, only this user's processes can connect).

Endpoints (all local):
  POST /v1/hook/{agent}   raw hook JSON from senti-hook / the OpenCode plugin → agent-formatted reply
  POST /v1/check          generic "may I do this?" API for custom agents
  GET  /v1/status         engine, judges, backend, profiles
  GET  /v1/decisions      recent decisions
  GET  /v1/snapshots      undo snapshots; POST /v1/snapshots/{id}/restore
  POST /v1/reload         reload honeytokens / settings-derived state
  GET  /v1/audit/verify   verify the hash chain of the local audit log
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import socket

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from . import adapters, undo
from .config import Settings, ensure_dirs, socket_path
from .engine import Engine

AGENTS = {"claude", "codex", "opencode", "generic"}


def create_app(engine: Engine) -> FastAPI:
    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        tasks = []
        if engine.local.state != "unavailable":
            engine.local.start_loading()
        if engine.settings.enrolled:
            from .sync import heartbeat_loop, profile_loop, upload_loop
            tasks += [asyncio.create_task(profile_loop(engine)), asyncio.create_task(upload_loop(engine)),
                      asyncio.create_task(heartbeat_loop(engine))]

        async def idle():
            while True:
                await asyncio.sleep(60)
                engine.local.maybe_unload()
        tasks.append(asyncio.create_task(idle()))
        yield
        for t in tasks:
            t.cancel()

    app = FastAPI(title="Senti engine", lifespan=lifespan)
    app.state.engine = engine

    @app.post("/v1/hook/{agent}")
    async def hook(agent: str, request: Request):
        if agent not in AGENTS:
            raise HTTPException(404, "unknown agent")
        try:
            ev = json.loads(await request.body() or b"{}")
        except Exception:
            ev = {}
        action = adapters.parse(agent, ev)
        res = await engine.handle(action)
        return PlainTextResponse(adapters.render(agent, action, res["decision"], res["context"]))

    @app.post("/v1/check")
    async def check(request: Request):
        ev = await request.json()
        action = adapters.parse("generic", ev)
        if ev.get("task") and action.session_id and action.session_id not in engine.tasks:
            engine.tasks[action.session_id] = ev["task"][:1000]
        res = await engine.handle(action)
        return PlainTextResponse(adapters.render("generic", action, res["decision"], res["context"]), media_type="application/json")

    @app.get("/v1/status")
    async def status():
        return engine.status()

    @app.get("/v1/decisions")
    async def decisions(limit: int = 50):
        return JSONResponse(engine.audit.recent[-limit:][::-1])

    @app.get("/v1/snapshots")
    async def snapshots():
        return undo.list_snapshots()

    @app.post("/v1/snapshots/{sid}/restore")
    async def restore(sid: str):
        try:
            return {"restored": undo.restore(sid)}
        except FileNotFoundError:
            raise HTTPException(404, "no such snapshot")

    @app.post("/v1/reload")
    async def reload():
        engine.honey.reload()
        engine.allowlist = engine._load_allowlist()
        engine.cache.clear()
        if engine.settings.enrolled:
            from .sync import fetch_profiles
            with contextlib.suppress(Exception):
                await fetch_profiles(engine)
        return {"ok": True, "profiles": engine.profiles.source}

    @app.get("/v1/audit/verify")
    async def verify():
        ok, n, err = engine.audit.verify()
        return {"ok": ok, "records": n, "error": err}

    return app


def bind_socket(path: str) -> socket.socket:
    if os.path.exists(path):
        # refuse to steal a live socket
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            s.connect(path)
            s.close()
            raise SystemExit(f"Senti is already running on {path}")
        except (ConnectionRefusedError, FileNotFoundError, OSError) as e:
            if isinstance(e, SystemExit):
                raise
            os.unlink(path)
    old = os.umask(0o177)
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(path)
    finally:
        os.umask(old)
    os.chmod(path, 0o600)
    return sock


def run(use_llm: bool = True, sock_path: str | None = None) -> None:
    import uvicorn
    ensure_dirs()
    engine = Engine(Settings.load(), use_llm=use_llm)
    path = sock_path or socket_path()
    sock = bind_socket(path)
    config = uvicorn.Config(create_app(engine), log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    (engine.audit.path.parent.parent / "senti.pid").write_text(str(os.getpid()))
    print(f"Senti engine listening on {path}", flush=True)
    try:
        server.run(sockets=[sock])
    finally:
        with contextlib.suppress(OSError):
            os.unlink(path)
