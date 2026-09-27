"""Who is on the other end of the socket? Peer-process verification and sandbox detection.

The engine reads the connecting process id from the Unix socket (macOS LOCAL_PEERPID), walks its parent chain and:
- verifies the caller really descends from the agent it claims to be (a same-user script can't pose as Claude Code);
- tells whether the agent runs inside a sandbox (for profiles that require one);
- refuses Senti control endpoints to anything running under an agent.
"""
from __future__ import annotations

import json
import os
import socket
import struct
import sys
from pathlib import Path

AGENT_MARKERS = {"claude": ("claude",), "codex": ("codex",), "opencode": ("opencode",)}
SOL_LOCAL, LOCAL_PEERPID = 0, 0x002


def peer_pid(sock: socket.socket | None) -> int | None:
    if sock is None or sys.platform != "darwin":
        if sock is not None and hasattr(socket, "SO_PEERCRED"):  # Linux
            try:
                pid, _, _ = struct.unpack("3i", sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
                return pid
            except OSError:
                return None
        return None
    try:
        return struct.unpack("i", sock.getsockopt(SOL_LOCAL, LOCAL_PEERPID, 4))[0]
    except OSError:
        return None


def ancestry(pid: int | None, depth: int = 16) -> list[dict]:
    if not pid:
        return []
    import psutil
    chain, seen = [], set()
    try:
        p = psutil.Process(pid)
    except psutil.Error:
        return []
    while p is not None and len(chain) < depth and p.pid not in seen:
        seen.add(p.pid)
        info = {"pid": p.pid, "name": "", "exe": "", "cmdline": []}
        try:
            with p.oneshot():
                info["name"] = p.name()
                try:
                    info["exe"] = p.exe()
                except psutil.Error:
                    pass
                try:
                    info["cmdline"] = p.cmdline()[:8]
                except psutil.Error:
                    pass
                parent = p.parent()
        except psutil.Error:
            parent = None
        chain.append(info)
        if p.pid <= 1:
            break
        p = parent
    return chain


def _words(proc: dict) -> list[str]:
    out = [proc.get("name", "").lower(), os.path.basename(proc.get("exe", "")).lower()]
    out += [os.path.basename(a).lower() for a in proc.get("cmdline", [])[:3]]
    return out


def agents_in(chain: list[dict]) -> set[str]:
    found = set()
    for proc in chain:
        words = _words(proc)
        for agent, marks in AGENT_MARKERS.items():
            if any(m == w or w.startswith(m + "-") or w.startswith(m + ".") for m in marks for w in words):
                found.add(agent)
    return found


def sandboxed_chain(chain: list[dict]) -> bool:
    for proc in chain:
        words = _words(proc)
        cmd = " ".join(proc.get("cmdline", []))
        if "sandbox-exec" in words or "sandbox-runtime" in cmd or "@anthropic-ai/sandbox-runtime" in cmd or "srt" in words:
            return True
    return False


def _claude_sandbox_enabled(cwd: str) -> bool:
    from .rules import project_root
    root = Path(project_root(cwd))
    files = [Path.home() / ".claude" / "settings.json", root / ".claude" / "settings.json", root / ".claude" / "settings.local.json",
             Path("/Library/Application Support/ClaudeCode/managed-settings.json")]
    enabled = False
    for f in files:
        try:
            sb = json.loads(f.read_text()).get("sandbox")
            if isinstance(sb, dict) and "enabled" in sb:
                enabled = bool(sb["enabled"])
        except (OSError, ValueError):
            continue
    return enabled


def sandbox_status(agent: str, chain: list[dict], cwd: str) -> bool | None:
    """True = the agent's commands run sandboxed, False = not, None = unknown."""
    if sandboxed_chain(chain):
        return True
    if agent == "claude":
        return _claude_sandbox_enabled(cwd)  # Claude Code sandboxes its Bash commands itself
    if agent == "codex":
        cmd = " ".join(" ".join(p.get("cmdline", [])) for p in chain)
        if not chain:
            return None
        return not ("--dangerously-bypass-approvals-and-sandbox" in cmd or "danger-full-access" in cmd or "--yolo" in cmd)
    return False if chain else None


def identify(agent: str, pid: int | None, cwd: str) -> dict:
    chain = ancestry(pid)
    found = agents_in(chain)
    verified = None if not chain else (agent in found if agent in AGENT_MARKERS else True)
    return {"pid": pid, "verified": verified, "agents_in_chain": sorted(found),
            "chain": [p.get("name") for p in chain[:8]],
            "sandboxed": sandbox_status(agent, chain, cwd) if agent in AGENT_MARKERS else None}
