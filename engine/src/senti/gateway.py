"""Local model gateway for DIY agents (no hooks): an OpenAI-compatible proxy in front of Ollama / LM Studio / any server.

Point your agent's base URL at http://127.0.0.1:11435/v1 instead of the model server. Every tool call the model proposes is
turned into a Senti action and checked before your agent ever sees it; blocked calls are removed and explained in the
message, allowed calls pass (with brokered secrets rewritten). Optional headers: X-Senti-Agent, X-Senti-Cwd, X-Senti-Session.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .models import Action

SHELL_WORDS = ("bash", "shell", "exec", "run_command", "terminal", "execute", "cmd", "command", "run_shell", "sh")


def map_tool(name: str, args: dict) -> tuple[str, dict]:
    """Best-effort mapping of an arbitrary function call to Senti's tool vocabulary."""
    n = name.lower()
    cmd = args.get("command") or args.get("cmd") or args.get("script") or args.get("code") if isinstance(args, dict) else None
    path = next((args.get(k) for k in ("file_path", "path", "filename", "file", "filepath") if isinstance(args, dict) and args.get(k)), None)
    url = args.get("url") or args.get("uri") if isinstance(args, dict) else None
    if isinstance(cmd, list):
        cmd = " ".join(map(str, cmd))
    if cmd and any(w in n for w in SHELL_WORDS):
        return "Bash", {"command": str(cmd)}
    if url and any(w in n for w in ("fetch", "http", "url", "browse", "web", "request", "download", "get")):
        return "WebFetch", {"url": str(url)}
    if path and any(w in n for w in ("delete", "remove", "unlink", "rm")):
        return "Bash", {"command": f"rm -rf {json.dumps(str(path))}"}
    if path and any(w in n for w in ("write", "create", "save", "append", "put")):
        return "Write", {"file_path": str(path), "content": str(args.get("content") or args.get("text") or args.get("data") or "")}
    if path and any(w in n for w in ("edit", "replace", "patch", "modify", "update")):
        return "Edit", {"file_path": str(path), "old_string": str(args.get("old") or args.get("old_string") or args.get("search") or ""),
                        "new_string": str(args.get("new") or args.get("new_string") or args.get("replace") or "")}
    if path and any(w in n for w in ("read", "open", "cat", "view", "load", "list", "ls")):
        return "Read", {"file_path": str(path)}
    if "search" in n and (args.get("query") if isinstance(args, dict) else None):
        return "WebSearch", {"query": str(args["query"])}
    if cmd:
        return "Bash", {"command": str(cmd)}
    return f"mcp__gateway__{name}", args if isinstance(args, dict) else {"args": args}


def _task(messages: list) -> str:
    for m in reversed(messages or []):
        if m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, list):
                c = " ".join(p.get("text", "") for p in c if isinstance(p, dict))
            return str(c or "")[:1000]
    return ""


async def check_choices(engine, req: dict, resp: dict, agent: str, cwd: str, session: str) -> dict:
    task = _task(req.get("messages", []))
    if task:
        engine.tasks[session] = task
    for ch in resp.get("choices", []):
        msg = ch.get("message") or {}
        calls = msg.get("tool_calls") or []
        kept, notes = [], []
        for call in calls:
            fn = call.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except ValueError:
                args = {"raw": fn.get("arguments")}
            tool, inp = map_tool(fn.get("name", ""), args)
            res = await engine.handle(Action(agent, tool, inp, cwd, session, raw_tool=fn.get("name", "")))
            d = res["decision"]
            if d.verdict == "allow":
                upd = d.meta.get("updated_input")
                if upd and tool == "Bash":
                    for k in ("command", "cmd", "script", "code"):
                        if k in args:
                            args[k] = upd["command"]
                            break
                    fn["arguments"] = json.dumps(args)
                kept.append(call)
            else:
                notes.append(f"Senti blocked the tool call `{fn.get('name')}`: {d.reason}")
        if calls:
            msg["tool_calls"] = kept or None
            if not kept:
                msg.pop("tool_calls", None)
                ch["finish_reason"] = "stop"
            if notes:
                msg["content"] = ((msg.get("content") or "") + "\n\n" + "\n".join(notes)).strip()
    return resp


def _as_stream(resp: dict):
    """Re-emit a checked completion as an SSE stream (tool calls are only checked on complete responses)."""
    base = {"id": resp.get("id", f"chatcmpl-{uuid.uuid4().hex[:12]}"), "object": "chat.completion.chunk",
            "created": resp.get("created", int(time.time())), "model": resp.get("model", "")}
    for ch in resp.get("choices", []):
        msg = ch.get("message") or {}
        delta = {"role": "assistant", "content": msg.get("content") or ""}
        if msg.get("tool_calls"):
            delta["tool_calls"] = [{**tc, "index": i} for i, tc in enumerate(msg["tool_calls"])]
        yield f"data: {json.dumps({**base, 'choices': [{'index': ch.get('index', 0), 'delta': delta, 'finish_reason': None}]})}\n\n"
        yield f"data: {json.dumps({**base, 'choices': [{'index': ch.get('index', 0), 'delta': {}, 'finish_reason': ch.get('finish_reason')}]})}\n\n"
    yield "data: [DONE]\n\n"


def create_gateway(engine) -> FastAPI:
    app = FastAPI(title="Senti model gateway")
    upstream = engine.settings.gateway_upstream.rstrip("/")

    @app.post("/v1/chat/completions")
    async def chat(request: Request):
        req = await request.json()
        agent = request.headers.get("x-senti-agent", "gateway")
        cwd = request.headers.get("x-senti-cwd") or engine.settings.gateway_cwd or os.path.expanduser("~")
        session = request.headers.get("x-senti-session") or hashlib.sha256(
            json.dumps((req.get("messages") or [{}])[:2], default=str).encode()).hexdigest()[:16]
        want_stream = bool(req.get("stream"))
        fwd = {**req, "stream": False}
        fwd.pop("stream_options", None)
        headers = {k: v for k, v in request.headers.items() if k.lower() in {"authorization"}}
        try:
            async with httpx.AsyncClient(timeout=600) as c:
                r = await c.post(upstream + "/chat/completions", json=fwd, headers=headers)
        except httpx.HTTPError as e:
            return JSONResponse({"error": {"message": f"Senti gateway: model server unreachable ({e})"}}, status_code=502)
        if r.status_code != 200:
            return Response(r.content, status_code=r.status_code, media_type=r.headers.get("content-type"))
        resp = await check_choices(engine, req, r.json(), agent, cwd, session)
        if want_stream:
            return StreamingResponse(_as_stream(resp), media_type="text/event-stream")
        return JSONResponse(resp)

    @app.api_route("/v1/{path:path}", methods=["GET", "POST"])
    async def passthrough(path: str, request: Request):
        """Models, embeddings, etc. are forwarded unchanged (no tool calls to check)."""
        async with httpx.AsyncClient(timeout=600) as c:
            r = await c.request(request.method, f"{upstream}/{path}", content=await request.body(),
                                headers={k: v for k, v in request.headers.items() if k.lower() in {"authorization", "content-type"}})
        return Response(r.content, status_code=r.status_code, media_type=r.headers.get("content-type"))

    return app
