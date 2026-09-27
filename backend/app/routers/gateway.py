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

from fastapi import APIRouter, Depends, HTTPException
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import corporate, policy_compiler
from ..bus import bus
from ..config import settings
from ..db import SessionLocal, get_db
from ..gateway_policy import (CompiledPolicy, GatewayDecision, RolePolicy, check_command, check_path, resolve_path, run_sql,
                              visible)
from ..gateway_policy import run_command as execute_command
from ..models import KV, Admin, ChangeLog, GatewayAgent, GatewayEvent
from ..security import current_admin, hash_key, limiter

Auth = Depends(current_admin)
router = APIRouter(prefix="/api/v1/admin/gateway")
TOKEN_PREFIX = "sag_"


# ---------------------------------------------------------------- state
def root() -> Path:
    p = Path(settings.gateway_root_path)
    p.mkdir(parents=True, exist_ok=True)
    return p.resolve()


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


def agent_for_token(db: Session, raw: str) -> GatewayAgent | None:
    raw = (raw or "").removeprefix("Bearer ").strip()
    if not raw.startswith(TOKEN_PREFIX):
        return None
    a = db.query(GatewayAgent).filter_by(token_hash=hash_key(raw)).first()
    return a if a and not a.revoked else None


# ---------------------------------------------------------------- deciding one call
async def supervise(db: Session, agent: GatewayAgent, policy_text: str, role: RolePolicy, tool: str, arg: str,
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


def log(agent: GatewayAgent, tool: str, target: str, d: GatewayDecision, t0: float) -> None:
    with SessionLocal() as db:
        ev = GatewayEvent(agent_id=agent.id, agent_name=agent.name, role=agent.role, tool=tool, target=target[:2000],
                          verdict=d.verdict, layer=d.layer, reason=d.reason[:1000], ms=round((time.perf_counter() - t0) * 1000, 1))
        db.add(ev)
        a = db.get(GatewayAgent, agent.id)
        if a:
            a.last_used, a.calls = time.time(), (a.calls or 0) + 1
        db.commit()
        bus.publish("admin", {"type": "gateway_event", "event": event_json(ev)})


class Blocked(Exception):
    pass


async def gate(ctx: Context, tool: str, arg: str, decide) -> tuple[GatewayAgent, RolePolicy, float]:
    """Authenticate, rate-limit, decide (rules → supervisor). Raises Blocked with the reason the agent should see."""
    t0 = time.perf_counter()
    with SessionLocal() as db:
        agent = agent_for_token(db, (ctx.headers or {}).get("authorization", ""))
        if agent is None:
            raise Blocked("Senti: unknown or revoked agent token")
        db.expunge(agent)
        if not limiter.allow(f"gateway:{agent.id}", settings.gateway_rpm):
            raise Blocked("Senti: too many requests from this agent; slow down")
        policy, text = active_policy(db)
        role = policy.roles.get(agent.role) if policy else None
        if role is None:
            d = GatewayDecision("block", f"No approved policy for role '{agent.role}' yet", "hard-rule")
        else:
            d = await asyncio.to_thread(decide, role)  # SQL and path checks must never block the event loop
            if d.verdict == "supervisor":
                d = await supervise(db, agent, text, role, tool, arg, d)
    log(agent, tool, arg, d, t0)
    if d.verdict != "allow":
        raise Blocked(f"Blocked by Senti: {d.reason}")
    return agent, role, t0


# ---------------------------------------------------------------- MCP server and tools
mcp = MCPServer(name="senti-server-gateway", instructions=(
    "This server's files, commands and database are only reachable through these tools. Senti checks every call against "
    "the access policy for your role; a refused call explains why. Paths are relative to the shared folder."))


def _err(e: Exception) -> str:
    return str(e)


@mcp.tool(description="List files in a folder of the shared server folder (entries your role can't access are hidden).")
async def list_files(ctx: Context, path: str = ".") -> str:
    try:
        agent, role, _ = await gate(ctx, "list_files", path, lambda r: check_path(r, root(), path, "list"))
    except Blocked as e:
        return _err(e)
    real, _ = resolve_path(root(), path)
    if real is None or not real.is_dir():
        return f"'{path}' is not a folder"
    out = []
    for p in sorted(real.iterdir()):
        r = p.relative_to(root()).as_posix()
        if p.is_symlink() or not visible(role, r):
            continue
        out.append(f"{r}{'/' if p.is_dir() else ''}\t{p.stat().st_size if p.is_file() else ''}")
    return "\n".join(out) or "(empty)"


@mcp.tool(description="Read a text file from the shared server folder.")
async def read_file(ctx: Context, path: str) -> str:
    try:
        await gate(ctx, "read_file", path, lambda r: check_path(r, root(), path, "read"))
    except Blocked as e:
        return _err(e)
    real, _ = resolve_path(root(), path)
    if real is None or not real.is_file():
        return f"'{path}' is not a file"
    data = real.read_bytes()[:200_000]
    return data.decode("utf-8", errors="replace")


@mcp.tool(description="Write (create or replace) a text file in the shared server folder.")
async def write_file(ctx: Context, path: str, content: str) -> str:
    try:
        await gate(ctx, "write_file", path, lambda r: check_path(r, root(), path, "write"))
    except Blocked as e:
        return _err(e)
    real, rel = resolve_path(root(), path)
    if real is None or real.is_dir():
        return f"'{path}' can't be written"
    real.parent.mkdir(parents=True, exist_ok=True)
    real.write_text(content[:1_000_000])
    return f"Wrote {len(content)} characters to {rel}"


@mcp.tool(description="Run one command (no shell, no pipes) in the shared server folder, e.g. 'grep -r invoice tickets'.")
async def run_command(ctx: Context, command: str) -> str:
    holder: dict[str, Any] = {}

    def decide(r: RolePolicy):
        d, argv = check_command(r, root(), command)
        holder["argv"] = argv
        return d
    try:
        await gate(ctx, "run_command", command, decide)
    except Blocked as e:
        return _err(e)
    return await asyncio.to_thread(execute_command, root(), holder["argv"], settings.gateway_cmd_timeout_s)


@mcp.tool(description="Run one SQL statement on the server's SQLite database. Returns columns and up to 200 rows.")
async def query_db(ctx: Context, sql: str) -> str:
    holder: dict[str, Any] = {}

    def decide(r: RolePolicy):
        d, cols, rows = run_sql(r, settings.gateway_db_path, sql)  # SQLite's authorizer decides while it runs
        holder.update(cols=cols, rows=rows)
        return d if d.verdict != "allow" else GatewayDecision("allow", d.reason, "role-rule")
    try:
        await gate(ctx, "query_db", sql, decide)
    except Blocked as e:
        return _err(e)
    return json.dumps({"columns": holder["cols"], "rows": holder["rows"]}, default=str)


class TokenGate:
    """Refuse the whole MCP endpoint (even tool listing) to anyone without a valid agent token."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            auth = dict(scope.get("headers") or []).get(b"authorization", b"").decode("latin-1")
            with SessionLocal() as db:
                ok = agent_for_token(db, auth) is not None
            if not ok:
                body = b'{"detail":"agent token required (Authorization: Bearer sag_...)"}'
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"application/json"), (b"www-authenticate", b"Bearer")]})
                await send({"type": "http.response.body", "body": body})
                return
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
def get_policy(admin: Admin = Auth, db: Session = Depends(get_db)):
    return {"draft": _kv(db, "gateway_draft") or None, "active": _kv(db, "gateway_active") or None,
            "inventory": policy_compiler.inventory(root(), settings.gateway_db_path)}


class PolicyIn(BaseModel):
    text: str


@router.post("/policy/compile")
async def compile_policy(body: PolicyIn, admin: Admin = Auth, db: Session = Depends(get_db)):
    if len(body.text.strip()) < 10:
        raise HTTPException(422, "describe who may do what, in a few sentences")
    try:
        out = await policy_compiler.compile_policy(policy_model_config(db), body.text, root(), settings.gateway_db_path)
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
    url = (body.base_url.rstrip("/") or "<server-url>") + "/api/v1/mcp/"
    return {**agent_json(a), "token": token, "url": url,  # the token is shown once; only its hash is stored
            "claude_code": f"claude mcp add --transport http senti-server {url} --header \"Authorization: Bearer {token}\"",
            "mcp_json": {"mcpServers": {"senti-server": {"type": "http", "url": url,
                                                           "headers": {"Authorization": f"Bearer {token}"}}}}}


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
