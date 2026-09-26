"""Install / remove Senti's hooks for Claude Code, Codex CLI and OpenCode (with backups)."""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from importlib import resources
from pathlib import Path

from .config import senti_home

HOME = Path.home()
MARK = "senti-hook"


def hook_binary() -> Path:
    return senti_home() / "bin" / "senti-hook"


def build_hook(source: Path | None = None) -> Path:
    """Compile the Swift hook client into ~/.senti/bin (falls back to the Python client if swiftc is missing)."""
    dst = hook_binary()
    dst.parent.mkdir(parents=True, exist_ok=True)
    src = source or Path(__file__).resolve().parents[2] / "hook" / "senti-hook.swift"
    if shutil.which("swiftc") and src.exists():
        subprocess.run(["swiftc", "-O", str(src), "-o", str(dst)], check=True)
    else:
        py = Path(__file__).with_name("hook_client.py")
        dst.write_text(f"#!/bin/sh\nexec python3 {py} \"$@\"\n")
        dst.chmod(0o755)
    return dst


def _backup(p: Path) -> None:
    if p.exists():
        shutil.copy2(p, p.with_name(p.name + f".senti-backup-{time.strftime('%Y%m%d%H%M%S')}"))


def _cmd(agent: str, event: str) -> str:
    return f"{hook_binary()} {agent} {event}"


def _merge_hooks(cfg: dict, agent: str, post_matcher: str) -> dict:
    hooks = cfg.setdefault("hooks", {})
    spec = {
        "PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": _cmd(agent, "pre"), "timeout": 600}]}],
        "UserPromptSubmit": [{"hooks": [{"type": "command", "command": _cmd(agent, "prompt"), "timeout": 30}]}],
        "PostToolUse": [{"matcher": post_matcher, "hooks": [{"type": "command", "command": _cmd(agent, "post"), "timeout": 30}]}],
    }
    for ev, entries in spec.items():
        cur = [e for e in hooks.get(ev, []) if not any(MARK in h.get("command", "") for h in e.get("hooks", []))]
        hooks[ev] = entries + cur  # Senti first
    return cfg


def _strip_hooks(cfg: dict) -> dict:
    for ev in list((cfg.get("hooks") or {}).keys()):
        cfg["hooks"][ev] = [e for e in cfg["hooks"][ev] if not any(MARK in h.get("command", "") for h in e.get("hooks", []))]
        if not cfg["hooks"][ev]:
            del cfg["hooks"][ev]
    return cfg


def claude_settings_path(project: str | None) -> Path:
    return Path(project) / ".claude" / "settings.local.json" if project else HOME / ".claude" / "settings.json"


def install_claude(project: str | None = None) -> Path:
    p = claude_settings_path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(p.read_text()) if p.exists() else {}
    _backup(p)
    p.write_text(json.dumps(_merge_hooks(cfg, "claude", "Read|WebFetch|Bash|Grep|mcp__.*"), indent=2))
    return p


def uninstall_claude(project: str | None = None) -> Path:
    p = claude_settings_path(project)
    if p.exists():
        _backup(p)
        p.write_text(json.dumps(_strip_hooks(json.loads(p.read_text())), indent=2))
    return p


def codex_hooks_path(project: str | None) -> Path:
    return (Path(project) / ".codex" if project else HOME / ".codex") / "hooks.json"


def install_codex(project: str | None = None) -> Path:
    p = codex_hooks_path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(p.read_text()) if p.exists() else {}
    _backup(p)
    p.write_text(json.dumps(_merge_hooks(cfg, "codex", "*"), indent=2))
    return p


def uninstall_codex(project: str | None = None) -> Path:
    p = codex_hooks_path(project)
    if p.exists():
        _backup(p)
        p.write_text(json.dumps(_strip_hooks(json.loads(p.read_text())), indent=2))
    return p


def opencode_plugin_path(project: str | None) -> Path:
    return (Path(project) / ".opencode" if project else HOME / ".config" / "opencode") / "plugins" / "senti.ts"


def install_opencode(project: str | None = None) -> Path:
    p = opencode_plugin_path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    src = resources.files("senti.data").joinpath("opencode-senti.ts").read_text()
    _backup(p)
    p.write_text(src.replace("__SENTI_HOOK__", str(hook_binary())))
    return p


def uninstall_opencode(project: str | None = None) -> Path:
    p = opencode_plugin_path(project)
    if p.exists():
        _backup(p)
        p.unlink()
    return p


INSTALL = {"claude": install_claude, "codex": install_codex, "opencode": install_opencode}
UNINSTALL = {"claude": uninstall_claude, "codex": uninstall_codex, "opencode": uninstall_opencode}


LAUNCH_AGENT = HOME / "Library" / "LaunchAgents" / "am.tumo.senti.plist"


def install_service(senti_exe: str) -> Path:
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>am.tumo.senti</string>
  <key>ProgramArguments</key><array><string>{senti_exe}</string><string>start</string><string>--foreground</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>{senti_home()}/engine.log</string>
  <key>StandardErrorPath</key><string>{senti_home()}/engine.log</string>
</dict></plist>
"""
    LAUNCH_AGENT.parent.mkdir(parents=True, exist_ok=True)
    LAUNCH_AGENT.write_text(plist)
    subprocess.run(["launchctl", "unload", str(LAUNCH_AGENT)], capture_output=True)
    subprocess.run(["launchctl", "load", str(LAUNCH_AGENT)], check=False)
    return LAUNCH_AGENT


def uninstall_service() -> None:
    if LAUNCH_AGENT.exists():
        subprocess.run(["launchctl", "unload", str(LAUNCH_AGENT)], capture_output=True)
        LAUNCH_AGENT.unlink()
