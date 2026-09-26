"""Senti prototype decision server: Unix socket, cascade L0 cache -> L1 rules -> L2 detectors -> L3 LLM.

Speaks Claude Code's hook protocol: receives the hook JSON, answers with hookSpecificOutput.
Run: python server.py SOCKET_PATH PROJECT_DIR [--no-llm] [--no-reason]
"""
from __future__ import annotations

import asyncio, hashlib, json, os, sys, time
from rules import Decision, check_action, expand

SOCK, PROJECT = sys.argv[1], os.path.realpath(sys.argv[2])
USE_LLM = "--no-llm" not in sys.argv
WANT_REASON = "--no-reason" not in sys.argv
ASYNC_REASON = "--async-reason" in sys.argv
PREFETCH = "--prefetch" in sys.argv
CODE_EXT = (".py", ".sh", ".js", ".mjs", ".ts", ".rb", ".pl", ".zsh", ".bash")
LOG = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "decisions.jsonl"), "a")

judge = None
if USE_LLM:
    from judge import Judge
    judge = Judge()
    judge.decide("warmup", {"tool": "Bash", "command": "ls"})

tasks: dict[str, str] = {}      # session_id -> latest user prompt (the TASK)
cache: dict[str, Decision] = {}  # L0 decision cache
llm_lock = asyncio.Lock()
script_verdicts: dict[str, "asyncio.Task"] = {}  # sha(task+script) -> pending/finished LLM verdict
background: set = set()


def script_key(task, text):
    return hashlib.sha256((task + "\0" + text).encode()).hexdigest()


async def llm(task, action, script_text, want_reason):
    async with llm_lock:
        return await asyncio.to_thread(judge.decide, task, action, script_text, want_reason)


def spawn(coro):
    t = asyncio.ensure_future(coro)
    background.add(t)
    t.add_done_callback(background.discard)
    return t


def read_script(path: str) -> str | None:
    try:
        with open(path, "r", errors="replace") as f:
            return f.read(20000)
    except OSError:
        return None


async def decide(ev: dict) -> tuple[Decision, dict]:
    t = {"t0": time.perf_counter()}
    session, tool, inp = ev.get("session_id", ""), ev.get("tool_name", ""), ev.get("tool_input", {})
    cwd = ev.get("cwd") or PROJECT
    task = tasks.get(session, "")

    d, facts = check_action(tool, inp, cwd, PROJECT)
    t["rules"] = time.perf_counter()
    scripts = {p: read_script(p) for p in facts.get("scripts", [])}
    script_text = "\n\n".join(f"# file: {os.path.basename(p)}\n{s}" for p, s in scripts.items() if s) or None

    # L2: static scan of script content with the same rules (a script is just more commands)
    if d is None and script_text:
        from rules import HARD_DENY_CMD, find_secrets
        import re
        sens = re.search(r"\.ssh|\.aws/credentials|id_rsa|\.env\b|Keychains|Cookies", script_text)
        net = re.search(r"requests\.(post|put)|urlopen\(.*data=|fetch\(.*method:\s*['\"]POST|curl\s|http\.client|socket\.connect", script_text)
        if sens and net:
            d = Decision("block", "The script reads secret files and sends data to the internet", "L2-detectors", "script_taint")
        for pat, why in HARD_DENY_CMD:
            if d is None and re.search(pat, script_text):
                d = Decision("block", "The script " + why[0].lower() + why[1:], "L2-detectors", "script_rule")
    t["detectors"] = time.perf_counter()

    key = None
    if d is None:
        key = hashlib.sha256(json.dumps([task, tool, inp, script_text], sort_keys=True).encode()).hexdigest()
        if key in cache:
            d = Decision(cache[key].verdict, cache[key].reason, "L0-cache", cache[key].rule)
    if d is None and script_text and PREFETCH and script_key(task, script_text) in script_verdicts:
        r = await script_verdicts[script_key(task, script_text)]   # judged in the background when the agent wrote it
        d = Decision(r["verdict"], r["reason"] or "Script was checked when it was written", "L0-prefetch", str(r["p"]))
    if d is None:
        if judge is None:
            d = Decision("ask", "Senti could not classify this action automatically", "fallback", "no_llm")
        else:
            action = {"tool": tool, **inp, "cwd": cwd.replace(os.path.expanduser("~"), "~")}
            r = await llm(task, action, script_text, WANT_REASON and not ASYNC_REASON)
            d = Decision(r["verdict"], r["reason"] or "Looks like normal development work", "L3-llm", str(r["p"]))
            t["llm_verdict_ms"] = r["ms_verdict"]
            cache[key] = d
            if ASYNC_REASON and d.verdict != "allow":
                # the popup opens right away; the plain-English reason is streamed into it a moment later
                spawn(llm(task, action, script_text, True))
    if PREFETCH and judge is not None and d.verdict == "allow" and tool in {"Write", "Edit"}:
        path = expand(inp.get("file_path", ""), cwd)
        if path.endswith(CODE_EXT):
            if tool == "Write":
                content = inp.get("content", "")
            else:
                content = (read_script(path) or "").replace(inp.get("old_string", ""), inp.get("new_string", ""), 1)
            text = f"# file: {os.path.basename(path)}\n{content}"
            k = script_key(task, text)
            if k not in script_verdicts:
                act = {"tool": "Bash", "command": f"(agent is about to run) {os.path.basename(path)}", "cwd": cwd}
                script_verdicts[k] = spawn(llm(task, act, text, False))
    t["end"] = time.perf_counter()
    timing = {"rules_ms": round((t["rules"] - t["t0"]) * 1000, 3),
              "detectors_ms": round((t["detectors"] - t["rules"]) * 1000, 3),
              "total_ms": round((t["end"] - t["t0"]) * 1000, 2)}
    if "llm_verdict_ms" in t:
        timing["llm_verdict_ms"] = t["llm_verdict_ms"]
    return d, timing


async def handle(reader, writer):
    try:
        raw = await asyncio.wait_for(reader.read(-1), timeout=5)
        ev = json.loads(raw)
        name = ev.get("hook_event_name")
        if name == "UserPromptSubmit":
            tasks[ev.get("session_id", "")] = ev.get("prompt", "")[:500]
            out, d, timing = {}, None, {}
        else:
            d, timing = await decide(ev)
            perm = {"allow": "allow", "ask": "ask", "block": "deny"}[d.verdict]
            out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": perm,
                                          "permissionDecisionReason": f"Senti: {d.reason}"}}
        writer.write(json.dumps(out).encode())
        await writer.drain()
        LOG.write(json.dumps({"event": name, "tool": ev.get("tool_name"), "id": ev.get("_case_id"),
                              "verdict": d.verdict if d else None, "layer": d.layer if d else None,
                              "reason": d.reason if d else None, **timing}) + "\n")
        LOG.flush()
    except Exception as e:  # fail closed
        writer.write(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                                                        "permissionDecisionReason": f"Senti error, asking to be safe: {e}"}}).encode())
    finally:
        writer.close()


async def main():
    if os.path.exists(SOCK):
        os.unlink(SOCK)
    srv = await asyncio.start_unix_server(handle, path=SOCK)
    os.chmod(SOCK, 0o600)
    print("ready", flush=True)
    async with srv:
        await srv.serve_forever()


asyncio.run(main())
