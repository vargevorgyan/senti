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
from .config import Settings, ensure_dirs, hook_token, socket_path
from .engine import Engine

from .agents import AGENTS  # noqa: E402


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
    token = hook_token(create=True)
    if not token:
        raise SystemExit("could not create the Senti hook token")

    @app.middleware("http")
    async def require_token(request: Request, call_next):
        import hmac
        if request.url.path == "/v1/secrets/redeem":
            return await call_next(request)  # authorised by a single-use grant bound to the exact command instead
        if not hmac.compare_digest(request.headers.get("x-senti-token", ""), token):
            if request.url.path.startswith("/v1/hook/"):
                return PlainTextResponse("missing or wrong Senti token", status_code=401)  # hook fails closed on non-200
            return JSONResponse({"detail": "missing or wrong Senti token"}, status_code=401)
        return await call_next(request)

    @app.post("/v1/hook/{agent}")
    async def hook(agent: str, request: Request):
        if agent not in AGENTS:
            raise HTTPException(404, "unknown agent")
        try:
            ev = json.loads(await request.body() or b"{}")
            if not isinstance(ev, dict):
                raise ValueError("not an object")
        except Exception:
            ev = {"hook_event_name": "PreToolUse", "tool_name": "", "tool_input": {}}  # unreadable → empty action → ask
        action = adapters.parse(agent, ev)
        from .identity import identify
        action.identity = await asyncio.to_thread(identify, agent, request.scope.get("senti.peer_pid"), action.cwd)
        res = await engine.handle(action)
        return PlainTextResponse(adapters.render(agent, action, res["decision"], res["context"]))

    def refuse_agents(request: Request) -> None:
        """Control endpoints are for the person (CLI), never for anything running under an AI agent."""
        from .identity import agents_in, ancestry
        found = agents_in(ancestry(request.scope.get("senti.peer_pid")))
        if found:
            raise HTTPException(403, f"Senti control actions can't be run from inside an AI agent ({', '.join(sorted(found))})")

    @app.post("/v1/check")
    async def check(request: Request):
        ev = await request.json()
        action = adapters.parse("generic", ev)
        if ev.get("task") and action.session_id and action.session_id not in engine.tasks:
            engine.tasks[action.session_id] = ev["task"][:1000]
        res = await engine.handle(action)
        return PlainTextResponse(adapters.render("generic", action, res["decision"], res["context"]), media_type="application/json")

    @app.post("/v1/secrets/redeem")
    async def redeem(request: Request):
        body = await request.json()
        values = engine.grants.redeem(str(body.get("grant", "")), str(body.get("command", "")))
        if values is None:
            raise HTTPException(403, "invalid, used or expired grant")
        return {"values": values}

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
    async def restore(sid: str, request: Request):
        refuse_agents(request)
        try:
            return {"restored": undo.restore(sid)}
        except FileNotFoundError:
            raise HTTPException(404, "no such snapshot")

    @app.post("/v1/reload")
    async def reload(request: Request):
        refuse_agents(request)
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


def peer_protocol():
    """uvicorn's h11 protocol, extended to put the connecting process id into every request scope."""
    from uvicorn.protocols.http.h11_impl import H11Protocol

    from .identity import peer_pid

    class PeerH11Protocol(H11Protocol):
        def connection_made(self, transport):  # type: ignore[override]
            self.senti_peer_pid = peer_pid(transport.get_extra_info("socket"))
            super().connection_made(transport)

        def handle_events(self) -> None:
            super().handle_events()
            scope = getattr(self, "scope", None)
            if isinstance(scope, dict):
                scope["senti.peer_pid"] = self.senti_peer_pid  # set before the request task first runs

    return PeerH11Protocol


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
    sock_inode = os.stat(path).st_ino
    config = uvicorn.Config(create_app(engine), log_level="warning", access_log=False, http=peer_protocol())
    server = uvicorn.Server(config)
    (engine.audit.path.parent.parent / "senti.pid").write_text(str(os.getpid()))
    print(f"Senti engine listening on {path}", flush=True)

    async def main():
        tasks = [server.serve(sockets=[sock])]
        if engine.settings.gateway_enabled:
            from .gateway import create_gateway
            gsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            gsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                gsock.bind(("127.0.0.1", engine.settings.gateway_port))
                gserver = uvicorn.Server(uvicorn.Config(create_gateway(engine), log_level="warning", access_log=False,
                                                        lifespan="off"))
                tasks.append(gserver.serve(sockets=[gsock]))
                print(f"Senti model gateway on http://127.0.0.1:{engine.settings.gateway_port}/v1 → "
                      f"{engine.settings.gateway_upstream}", flush=True)
            except OSError as e:
                print(f"Senti model gateway disabled: {e}", flush=True)
        await asyncio.gather(*tasks)

    try:
        asyncio.run(main())
    finally:
        # only remove the socket file if it is still ours: a newer engine may already have replaced it
        with contextlib.suppress(OSError):
            if os.stat(path).st_ino == sock_inode:
                os.unlink(path)
