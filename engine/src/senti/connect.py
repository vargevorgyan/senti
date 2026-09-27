"""`senti connect`: add (or remove) the company server to the AI assistants on this Mac.

Each assistant gets one MCP server entry, "company-server", that runs the local bridge (`senti mcp`). The entry holds no
secret: the bridge uses this Mac's enrollment. Configs are backed up before changes; running it twice changes nothing.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .installers import HOME, _backup, _load_json, _write_json

NAME = "company-server"
ASSISTANTS = ["claude", "claude-desktop", "cursor", "codex", "opencode"]


def bridge_command() -> tuple[str, list[str], dict[str, str]]:
    env = {k: os.environ[k] for k in ("SENTI_HOME",) if os.environ.get(k)}
    return sys.executable, ["-m", "senti.cli", "mcp"], env


def _json_server() -> dict:
    cmd, args, env = bridge_command()
    return {"command": cmd, "args": args, **({"env": env} if env else {})}


# ---------------------------------------------------------------- JSON configs (Claude Desktop, Cursor, OpenCode)
def _set_json(path: Path, key: str, value: dict | None) -> str:
    cfg = _load_json(path) if path.exists() else {}
    servers = cfg.setdefault(key, {})
    if value is None:
        if NAME not in servers:
            return "not connected"
        servers.pop(NAME)
    elif servers.get(NAME) == value:
        return "already connected"
    else:
        servers[NAME] = value
    _write_json(path, cfg)  # backs the file up first
    return str(path)


def claude_desktop(remove: bool = False) -> str:
    d = HOME / "Library/Application Support/Claude"
    if not d.exists():
        return "not installed"
    return _set_json(d / "claude_desktop_config.json", "mcpServers", None if remove else _json_server())


def cursor(remove: bool = False) -> str:
    d = HOME / ".cursor"
    if not d.exists():
        return "not installed"
    return _set_json(d / "mcp.json", "mcpServers", None if remove else _json_server())


def opencode(remove: bool = False) -> str:
    d = HOME / ".config/opencode"
    if not d.exists() and not shutil.which("opencode"):
        return "not installed"
    cmd, args, env = bridge_command()
    entry = {"type": "local", "command": [cmd, *args], "enabled": True, **({"environment": env} if env else {})}
    return _set_json(d / "opencode.json", "mcp", None if remove else entry)


# ---------------------------------------------------------------- Codex (TOML)
BEGIN, END = "# >>> senti company-server >>>", "# <<< senti company-server <<<"


def codex(remove: bool = False) -> str:
    d = HOME / ".codex"
    if not d.exists() and not shutil.which("codex"):
        return "not installed"
    path = d / "config.toml"
    text = path.read_text() if path.exists() else ""
    stripped = re.sub(rf"\n?{re.escape(BEGIN)}.*?{re.escape(END)}\n?", "\n", text, flags=re.S).rstrip("\n")
    if remove:
        if stripped == text.rstrip("\n"):
            return "not connected"
        new = stripped + "\n" if stripped else ""
    else:
        cmd, args, env = bridge_command()
        block = [BEGIN, f"[mcp_servers.{NAME}]", f"command = {json.dumps(cmd)}", f"args = {json.dumps(args)}"]
        if env:
            block.append("env = { " + ", ".join(f"{k} = {json.dumps(v)}" for k, v in env.items()) + " }")
        block.append(END)
        new = (stripped + "\n\n" if stripped else "") + "\n".join(block) + "\n"
        if new == text:
            return "already connected"
    d.mkdir(parents=True, exist_ok=True)
    _backup(path)
    path.write_text(new)
    return str(path)


# ---------------------------------------------------------------- Claude Code (through its own CLI)
def claude(remove: bool = False) -> str:
    exe = shutil.which("claude")
    if not exe:
        return "not installed"
    cmd, args, env = bridge_command()
    subprocess.run([exe, "mcp", "remove", "--scope", "user", NAME], capture_output=True)
    if remove:
        return "removed (user scope)"
    # add-json: `mcp add -e` takes several values and would swallow the server name
    spec = {"type": "stdio", "command": cmd, "args": args, **({"env": env} if env else {})}
    r = subprocess.run([exe, "mcp", "add-json", "--scope", "user", NAME, json.dumps(spec)], capture_output=True, text=True)
    if r.returncode != 0:
        return f"failed: {(r.stderr or r.stdout).strip()[:200]}"
    return "connected (user scope)"


CONNECT = {"claude": claude, "claude-desktop": claude_desktop, "cursor": cursor, "codex": codex, "opencode": opencode}
