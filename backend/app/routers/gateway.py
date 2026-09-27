"""Server gateway: an MCP endpoint through which AI agents use this server, under role rules compiled from plain English.

Agents connect with a token (the token decides the role). Every tool call is decided by gateway_policy (hard rules → role
rules) and, when the rules don't cover it, by the supervisor LLM — no human in the loop; "ask" counts as a block. Only then
does the gateway perform the action itself. Admin endpoints manage the policy (compile → review examples → approve), agent
tokens and the activity feed.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import corporate, policy_compiler
from ..bus import bus
from ..config import settings
from ..db import SessionLocal, get_db
from ..gateway_client import RunnerOps, RunnerUnavailable
from ..gateway_client import call as runner_call
from ..gateway_policy import CompiledPolicy, GatewayDecision, RolePolicy
from ..models import KV, Admin, ChangeLog, GatewayAgent, GatewayEvent
from ..security import (current_admin, device_for_token, hash_key, limiter, request_target, verify_device_signature)

Auth = Depends(current_admin)
router = APIRouter(prefix="/api/v1/admin/gateway")
TOKEN_PREFIX = "sag_"


# ---------------------------------------------------------------- state
def _kv(db: Session, key: str) -> dict:
    kv = db.get(KV, key)
    return dict(kv.value) if kv else {}


def _set_kv(db: Session, key: str, value: dict) -> None:
    kv = db.get(KV, key)
    if kv:
        kv.value = value
    else:
        db.add(KV(key=key, value=value))
    db.commit()


def active_policy(db: Session) -> tuple[CompiledPolicy | None, str]:
    a = _kv(db, "gateway_active")
    if not a.get("compiled"):
        return None, ""
    return CompiledPolicy.model_validate(a["compiled"]), a.get("text", "")


def policy_model_config(db: Session) -> dict:
    from .device import corp_config
    cfg = dict(corp_config(db))
    if settings.policy_model_url:
        cfg.update(url=settings.policy_model_url, model=settings.policy_model or cfg.get("model", ""),
                   api_key=settings.policy_model_api_key)
    return cfg


class Caller:
    """Who is using the gateway: a bot with its own agent token, or a person's AI assistant on an enrolled Mac."""

    def __init__(self, id: str, name: str, role: str, agent_id: str = ""):
        self.id, self.name, self.role, self.agent_id = id, name, role, agent_id


def agent_for_token(db: Session, raw: str) -> Caller | None:
    raw = (raw or "").removeprefix("Bearer ").strip()
    if raw.startswith(TOKEN_PREFIX):
        a = db.query(GatewayAgent).filter_by(token_hash=hash_key(raw)).first()
        return Caller(a.id, a.name, a.role, agent_id=a.id) if a and not a.revoked else None
    if raw.startswith("sdt_"):
        # an enrolled Mac: the person's server role (set by the admin on the People page) applies to all their assistants.
        # Its requests are signed with the device key; TokenGate checks the signature before any tool runs.
        d = device_for_token(db, raw)
        if d is None or not (d.user.gateway_role or "").strip():
            return None
        return Caller(f"device:{d.id}", f"{d.user.email} · {d.hostname or 'Mac'}", d.user.gateway_role)
    return None


# ---------------------------------------------------------------- deciding one call
async def supervise(db: Session, agent: Caller, policy_text: str, role: RolePolicy, tool: str, arg: str,
                    d: GatewayDecision) -> GatewayDecision:
    """Unclear case: the supervisor LLM decides. No human is watching, so anything but a clear allow is a block."""
    from .device import corp_config
    cfg = corp_config(db)
    if not cfg.get("enabled", True):
        return GatewayDecision("block", "No rule covers this and the supervisor is turned off", "supervisor")
    instructions = (f"SERVER ACCESS POLICY written by the administrator (plain English):\n{policy_text[:3000]}\n\n"
                    f"The agent '{agent.name}' has role '{agent.role}'. {role.notes}\n"
                    "The agent is using a shared server through Senti's gateway, with no human watching. Answer \"allow\" only if "
                    "the policy clearly permits this action for this role; otherwise answer \"block\".")
    action = {"tool": tool, "argument": arg[:1000], "role": agent.role, "why_it_needs_a_decision": d.reason}
    try:
        out = await corporate.judge(cfg, f"work as the '{agent.role}' role on this server", action, None, instructions,
                                    {"role_rules": role.model_dump(exclude={"notes"})}, settings.corp_timeout_s)
    except Exception as e:  # supervisor down → fail closed
        return GatewayDecision("block", f"No rule covers this and the supervisor is unavailable ({type(e).__name__})", "supervisor")
    if out.get("verdict") == "allow":
        return GatewayDecision("allow", out.get("reason") or "The supervisor allowed it", "supervisor")
    return GatewayDecision("block", out.get("reason") or "The supervisor did not allow it", "supervisor")


def log(agent: Caller, tool: str, target: str, d: GatewayDecision, t0: float) -> None:
    with SessionLocal() as db:
        ev = GatewayEvent(agent_id=agent.id, agent_name=agent.name, role=agent.role, tool=tool, target=target[:2000],
                          verdict=d.verdict, layer=d.layer, reason=d.reason[:1000], ms=round((time.perf_counter() - t0) * 1000, 1))
        db.add(ev)
        a = db.get(GatewayAgent, agent.agent_id) if agent.agent_id else None
        if a:
            a.last_used, a.calls = time.time(), (a.calls or 0) + 1
        db.commit()
        bus.publish("admin", {"type": "gateway_event", "event": event_json(ev)})


class Blocked(Exception):
    pass


async def gate(ctx: Context, tool: str, arg: str) -> tuple[Caller, RolePolicy, dict]:
    """Authenticate, rate-limit, decide (rules in the runner → supervisor). Raises Blocked with the reason the agent should
    see. Returns the runner's check answer (query_db results come with it)."""
    t0 = time.perf_counter()
    resp: dict = {}
    with SessionLocal() as db:
        agent = agent_for_token(db, (ctx.headers or {}).get("authorization", ""))
        if agent is None:
            raise Blocked("Senti: unknown or revoked agent token")
        if not limiter.allow(f"gateway:{agent.id}", settings.gateway_rpm):
            raise Blocked("Senti: too many requests from this agent; slow down")
        policy, text = active_policy(db)
        role = policy.roles.get(agent.role) if policy else None
        if role is None:
            d = GatewayDecision("block", f"No approved policy for role '{agent.role}' yet", "hard-rule")
        else:
            try:
                resp = await runner_call({"op": "check", "tool": tool, "arg": arg, "role": role.model_dump()})
                dj = resp["decision"]
                d = GatewayDecision(dj["verdict"], dj["reason"], dj["layer"])
            except (RunnerUnavailable, KeyError) as e:
                d = GatewayDecision("block", str(e) if isinstance(e, RunnerUnavailable) else "bad runner answer", "hard-rule")
            if d.verdict == "supervisor":
                d = await supervise(db, agent, text, role, tool, arg, d)
    log(agent, tool, arg, d, t0)
    if d.verdict != "allow":
        raise Blocked(f"Blocked by Senti: {d.reason}")
    return agent, role, resp


async def run_tool(ctx: Context, tool: str, arg: str, content: str = "") -> str:
    try:
        _, role, resp = await gate(ctx, tool, arg)
    except Blocked as e:
        return str(e)
    if tool == "query_db":
        return json.dumps({"columns": resp.get("columns", []), "rows": resp.get("rows", [])}, default=str)
    try:
        out = await runner_call({"op": "exec", "tool": tool, "arg": arg, "content": content, "role": role.model_dump()})
    except RunnerUnavailable as e:
        return f"Blocked by Senti: {e}"
    if (out.get("decision") or {}).get("verdict") == "block":  # the files changed between check and run
        return f"Blocked by Senti: {out['decision'].get('reason', '')}"
    return str(out.get("output", ""))


# ---------------------------------------------------------------- MCP server and tools
mcp = MCPServer(name="senti-server-gateway", instructions=(
    "This server's files, commands and database are only reachable through these tools. Senti checks every call against "
    "the access policy for your role; a refused call explains why. Paths are relative to the shared folder."))


@mcp.tool(description="List files in a folder of the shared server folder (entries your role can't access are hidden).")
async def list_files(ctx: Context, path: str = ".") -> str:
    return await run_tool(ctx, "list_files", path)


@mcp.tool(description="Read a text file from the shared server folder.")
async def read_file(ctx: Context, path: str) -> str:
    return await run_tool(ctx, "read_file", path)


@mcp.tool(description="Write (create or replace) a text file in the shared server folder.")
async def write_file(ctx: Context, path: str, content: str) -> str:
    return await run_tool(ctx, "write_file", path, content)


@mcp.tool(description="Run one command (no shell, no pipes) in the shared server folder, e.g. 'grep -r invoice tickets'.")
async def run_command(ctx: Context, command: str) -> str:
    return await run_tool(ctx, "run_command", command)


@mcp.tool(description="Run one SQL statement on the server's SQLite database. Returns columns and up to 200 rows.")
async def query_db(ctx: Context, sql: str) -> str:
    return await run_tool(ctx, "query_db", sql)


class TokenGate:
    """Refuse the whole MCP endpoint (even tool listing) to anyone without a valid agent token."""

    def __init__(self, app):
        self.app = app

    MAX_BODY = 4 * 1024 * 1024

    async def _refuse(self, send, status: int, detail: str) -> None:
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"), (b"www-authenticate", b"Bearer")]})
        await send({"type": "http.response.body", "body": json.dumps({"detail": detail}).encode()})

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}
            auth = headers.get("authorization", "")
            with SessionLocal() as db:
                ok = agent_for_token(db, auth) is not None
                dev = device_for_token(db, auth) if ok and "sdt_" in auth else None
            if not ok:
                return await self._refuse(send, 401, "agent token required (Authorization: Bearer sag_...), or a Mac enrolled "
                                                     "by a person who has server access (People page)")
            if dev is not None:
                # a Mac's request must be signed by its device key: read the body once, verify, then replay it
                body, more = b"", True
                while more:
                    msg = await receive()
                    if msg["type"] == "http.disconnect":
                        return
                    body += msg.get("body", b"")
                    more = msg.get("more_body", False)
                    if len(body) > self.MAX_BODY:
                        return await self._refuse(send, 413, "request too large")
                try:
                    verify_device_signature(dev, scope["method"], request_target(scope), headers, body)
                except HTTPException as e:
                    return await self._refuse(send, 401, e.detail)
                sent = False

                async def replay():
                    nonlocal sent
                    if not sent:
                        sent = True
                        return {"type": "http.request", "body": body, "more_body": False}
                    return await receive()
                return await self.app(scope, replay, send)
        await self.app(scope, receive, send)


def mcp_asgi_app():
    # token auth + our own TLS protect the endpoint; the SDK's Host check would reject requests coming through nginx
    app = mcp.streamable_http_app(streamable_http_path="/", stateless_http=True, json_response=True,
                                  transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
    return TokenGate(app)


# ---------------------------------------------------------------- admin API
def event_json(e: GatewayEvent) -> dict:
    return {"id": e.id, "ts": e.ts, "agent": e.agent_name, "agent_id": e.agent_id, "role": e.role, "tool": e.tool,
            "target": e.target, "verdict": e.verdict, "layer": e.layer, "reason": e.reason, "ms": e.ms}


def agent_json(a: GatewayAgent) -> dict:
    return {"id": a.id, "name": a.name, "role": a.role, "created_at": a.created_at, "created_by": a.created_by,
            "last_used": a.last_used, "calls": a.calls, "revoked": a.revoked}


@router.get("/policy")
async def get_policy(admin: Admin = Auth, db: Session = Depends(get_db)):
    try:
        inventory = await RunnerOps().inventory()
    except RunnerUnavailable as e:
        inventory = f"({e})"
    return {"draft": _kv(db, "gateway_draft") or None, "active": _kv(db, "gateway_active") or None, "inventory": inventory}


class PolicyIn(BaseModel):
    text: str


@router.post("/policy/compile")
async def compile_policy(body: PolicyIn, admin: Admin = Auth, db: Session = Depends(get_db)):
    if len(body.text.strip()) < 10:
        raise HTTPException(422, "describe who may do what, in a few sentences")
    cfg = policy_model_config(db)
    if not settings.policy_model_url and not cfg.get("enabled", True):
        raise HTTPException(503, "No AI model is set up to turn the policy into rules. Choose one on the Corporate judge "
                                 "page (any OpenAI-compatible API) or set SENTI_POLICY_MODEL_URL, then generate again.")
    try:
        out = await policy_compiler.compile_policy(cfg, body.text, RunnerOps())
    except httpx.TransportError as e:
        raise HTTPException(503, f"Can't reach the AI model at {cfg.get('url', '?')} ({type(e).__name__}). Check the "
                                 "Corporate judge page or SENTI_POLICY_MODEL_URL, then generate again.")
    except Exception as e:
        raise HTTPException(502, f"could not compile the policy: {type(e).__name__}: {str(e)[:300]}")
    draft = {"text": body.text, **out, "compiled_at": time.time(), "compiled_by": admin.email}
    _set_kv(db, "gateway_draft", draft)
    return draft


@router.post("/policy/approve")
def approve_policy(admin: Admin = Auth, db: Session = Depends(get_db)):
    draft = _kv(db, "gateway_draft")
    if not draft.get("compiled"):
        raise HTTPException(400, "compile a policy first")
    prev = _kv(db, "gateway_active")
    active = {"text": draft["text"], "compiled": draft["compiled"], "version": int(prev.get("version", 0)) + 1,
              "approved_at": time.time(), "approved_by": admin.email}
    _set_kv(db, "gateway_active", active)
    db.add(ChangeLog(actor=admin.email, action="gateway_policy.approve", target=f"v{active['version']}",
                     detail={"roles": sorted(draft["compiled"].get("roles", {}))}))
    db.commit()
    return active


@router.get("/agents")
def list_agents(admin: Admin = Auth, db: Session = Depends(get_db)):
    return [agent_json(a) for a in db.query(GatewayAgent).order_by(GatewayAgent.created_at.desc()).all()]


class AgentIn(BaseModel):
    name: str
    role: str
    base_url: str = ""  # the admin panel passes its own origin; only used to build the connection command


@router.post("/agents", status_code=201)
def create_agent(body: AgentIn, admin: Admin = Auth, db: Session = Depends(get_db)):
    import secrets
    policy, _ = active_policy(db)
    role = body.role.strip().lower()
    if not policy or role not in policy.roles:
        raise HTTPException(422, "approve a policy first and pick one of its roles")
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    a = GatewayAgent(name=body.name.strip()[:200] or role, role=role, token_hash=hash_key(token), created_by=admin.email)
    db.add(a)
    db.add(ChangeLog(actor=admin.email, action="gateway_agent.create", target=a.name, detail={"role": role}))
    db.commit()
    base = body.base_url.rstrip("/") or "<server-url>"
    url = base + "/api/v1/mcp/"
    from .admin import _tls_fingerprint
    fp = _tls_fingerprint()
    bridge = ["mcp", "--backend", base, "--token", token] + (["--fingerprint", fp] if fp else [])
    return {**agent_json(a), "token": token, "url": url,  # the token is shown once; only its hash is stored
            "claude_code": f"claude mcp add --transport http senti-server {url} --header \"Authorization: Bearer {token}\"",
            # through Senti's local bridge: pins this server's (self-signed) certificate, works with any MCP client
            "bridge_command": "senti mcp --backend " + base + " --token " + token + (f" --fingerprint {fp}" if fp else ""),
            "mcp_json": {"mcpServers": {"senti-server": {"command": "senti", "args": bridge}}}}


@router.delete("/agents/{aid}")
def revoke_agent(aid: str, admin: Admin = Auth, db: Session = Depends(get_db)):
    a = db.get(GatewayAgent, aid)
    if not a:
        raise HTTPException(404, "agent not found")
    a.revoked = True
    db.add(ChangeLog(actor=admin.email, action="gateway_agent.revoke", target=a.name))
    db.commit()
    return {"ok": True}


@router.get("/events")
def list_events(limit: int = 100, admin: Admin = Auth, db: Session = Depends(get_db)):
    q = db.query(GatewayEvent).order_by(GatewayEvent.id.desc()).limit(min(max(limit, 1), 500))
    return [event_json(e) for e in q.all()]
