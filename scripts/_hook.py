"""Shared helper for the replay scripts: send one event through the real hook binary, fail loudly if the engine is down."""
from __future__ import annotations

import json
import os
import subprocess

HOOK = os.environ.get("SENTI_HOOK", os.path.join(os.environ.get("SENTI_HOME", os.path.expanduser("~/.senti")), "bin", "senti-hook"))
MAP = {"allow": "allow", "ask": "ask", "deny": "block"}
UNAVAILABLE = ("unavailable", "not running", "not reachable", "cannot reach", "no reply")


class EngineUnavailable(RuntimeError):
    pass


def send(payload: dict, event: str) -> tuple[str, str]:
    """Returns (verdict, reason) for a pre event; raises if the hook is missing or answered with its fail-closed fallback."""
    if not os.path.exists(HOOK):
        raise EngineUnavailable(f"hook binary not found: {HOOK} (set SENTI_HOOK or SENTI_HOME)")
    p = subprocess.run([HOOK, "claude", event], input=json.dumps(payload).encode(), capture_output=True, timeout=120)
    out = json.loads(p.stdout or b"{}").get("hookSpecificOutput", {})
    verdict = MAP.get(out.get("permissionDecision"), "?")
    reason = out.get("permissionDecisionReason", "")
    if event == "pre" and (verdict == "?" or any(u in reason.lower() for u in UNAVAILABLE)):
        raise EngineUnavailable(f"engine did not decide (verdict={verdict!r}, reason={reason[:120]!r})")
    return verdict, reason


def preflight(cwd: str) -> None:
    """A routine command must come back as a real 'allow' before any results are trusted."""
    v, r = send({"session_id": "preflight", "hook_event_name": "PreToolUse", "cwd": cwd, "tool_name": "Bash",
                 "tool_input": {"command": "git status"}}, "pre")
    if v != "allow":
        raise EngineUnavailable(f"preflight 'git status' returned {v!r}: {r[:120]}")
