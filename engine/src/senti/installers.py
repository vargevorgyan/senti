"""Install / remove Senti's hooks for Claude Code, Codex CLI and OpenCode (with backups)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from importlib import resources
from pathlib import Path

from .config import senti_home

MARK = "senti-hook"


def _home() -> Path:
    return Path(os.environ.get("HOME") or Path.home())


class _HomeProxy(os.PathLike):
    """`HOME / "x"` evaluated lazily, so tests (and sudo-less installs) can point HOME elsewhere."""
    def __truediv__(self, other):
        return _home() / other

    def __fspath__(self):
        return str(_home())


HOME = _HomeProxy()


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


def key_helper_binary() -> Path:
    return senti_home() / "bin" / "senti-key"


def build_key_helper(source: Path | None = None) -> Path:
    """Compile the Secure Enclave key helper (hook/senti-key.swift). Without the Swift compiler there is no helper and the
    device key falls back to a software key (see devicekey.py)."""
    dst = key_helper_binary()
    src = source or Path(__file__).resolve().parents[2] / "hook" / "senti-key.swift"
    if not (shutil.which("swiftc") and src.exists()):
        raise FileNotFoundError("swiftc or senti-key.swift missing")
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["swiftc", "-O", str(src), "-o", str(dst)], check=True, capture_output=True)
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


def claude_sandbox_block(srt: dict) -> dict:
    """Translate Senti's srt settings into Claude Code's built-in Bash sandbox settings."""
    net, fs = srt["network"], srt["filesystem"]
    return {
        "enabled": True,
        "failIfUnavailable": True,
        # "**/.env*" is left to Senti's rules here: Seatbelt also denies metadata, which breaks tree walkers such as pytest collection
        "filesystem": {"denyRead": [p for p in fs["denyRead"] if not p.startswith("**/.env")], "denyWrite": fs["denyWrite"]},
        "network": {"allowedDomains": [d for d in net["allowedDomains"] if d != "*"],
                    "deniedDomains": net.get("deniedDomains", []),
                    "allowUnixSockets": net["allowUnixSockets"],
                    "strictAllowlist": "*" not in net["allowedDomains"]},
    }


def install_claude(project: str | None = None, sandbox: dict | None = None) -> Path:
    p = claude_settings_path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(p.read_text()) if p.exists() else {}
    _backup(p)
    cfg = _merge_hooks(cfg, "claude", "Read|WebFetch|Bash|Grep|mcp__.*")
    if sandbox is not None:
        cfg["sandbox"] = claude_sandbox_block(sandbox)
    p.write_text(json.dumps(cfg, indent=2))
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


# ---------------------------------------------------------------- agents added 2026-09-27
def _load_json(p: Path) -> dict:
    return json.loads(p.read_text()) if p.exists() and p.read_text().strip() else {}


def _write_json(p: Path, data: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    _backup(p)
    p.write_text(json.dumps(data, indent=2))


def _no_project(agent: str, project: str | None) -> None:
    if project:
        raise ValueError(f"{agent} only reads user-level hook settings; install without --project")


# Cursor: ~/.cursor/hooks.json or <project>/.cursor/hooks.json  (version 1, failClosed so crashes/timeouts deny)
CURSOR_EVENTS = {"beforeShellExecution": "pre", "beforeMCPExecution": "pre", "beforeReadFile": "pre", "preToolUse": "pre",
                 "beforeSubmitPrompt": "prompt", "postToolUse": "post", "afterShellExecution": "post", "afterFileEdit": "post"}


def cursor_hooks_path(project: str | None) -> Path:
    return (Path(project) if project else HOME) / ".cursor" / "hooks.json"


def install_cursor(project: str | None = None) -> Path:
    p = cursor_hooks_path(project)
    cfg = _load_json(p)
    cfg["version"] = cfg.get("version", 1)
    hooks = cfg.setdefault("hooks", {})
    for ev, kind in CURSOR_EVENTS.items():
        entry = {"command": _cmd("cursor", kind), "timeout": 600 if kind == "pre" else 30}
        if kind != "post":
            entry["failClosed"] = True
        hooks[ev] = [entry] + [e for e in hooks.get(ev, []) if MARK not in e.get("command", "")]
    _write_json(p, cfg)
    return p


def uninstall_cursor(project: str | None = None) -> Path:
    p = cursor_hooks_path(project)
    if p.exists():
        cfg = _load_json(p)
        for ev in list((cfg.get("hooks") or {})):
            cfg["hooks"][ev] = [e for e in cfg["hooks"][ev] if MARK not in e.get("command", "")]
            if not cfg["hooks"][ev]:
                del cfg["hooks"][ev]
        _write_json(p, cfg)
    return p


# Cline: one executable per event in ~/Documents/Cline/Hooks/ (or <project>/.clinerules/hooks/)
CLINE_EVENTS = {"PreToolUse": "pre", "UserPromptSubmit": "prompt", "PostToolUse": "post"}


def cline_hooks_dir(project: str | None) -> Path:
    return Path(project) / ".clinerules" / "hooks" if project else HOME / "Documents" / "Cline" / "Hooks"


def install_cline(project: str | None = None) -> Path:
    d = cline_hooks_dir(project)
    d.mkdir(parents=True, exist_ok=True)
    skipped = []
    for ev, kind in CLINE_EVENTS.items():
        f = d / ev
        if f.exists() and MARK not in f.read_text(errors="replace"):
            skipped.append(ev)  # never overwrite a person's own hook
            continue
        f.write_text(f"#!/bin/sh\n# Installed by Senti (senti install cline). Remove with: senti uninstall cline\nexec {hook_binary()} cline {kind}\n")
        f.chmod(0o755)
    if skipped:
        print(f"  cline: kept your existing hooks {', '.join(skipped)} in {d}; Senti is NOT active for those events")
    return d


def uninstall_cline(project: str | None = None) -> Path:
    d = cline_hooks_dir(project)
    for ev in CLINE_EVENTS:
        f = d / ev
        if f.exists() and MARK in f.read_text(errors="replace"):
            f.unlink()
    return d


# Hermes Agent: shell hooks in ~/.hermes/config.yaml (fail_closed), consent pre-seeded in shell-hooks-allowlist.json
def hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or HOME / ".hermes")


def install_hermes(project: str | None = None) -> Path:
    import yaml
    _no_project("Hermes", project)
    p = hermes_home() / "config.yaml"
    cfg = (yaml.safe_load(p.read_text()) if p.exists() else None) or {}
    hooks = cfg.setdefault("hooks", {}) or {}
    cfg["hooks"] = hooks
    for ev, kind in (("pre_tool_call", "pre"), ("post_tool_call", "post")):
        entry = {"id": f"senti-{kind}", "matcher": ".*", "command": _cmd("hermes", kind), "timeout": 300 if kind == "pre" else 30}
        if kind == "pre":
            entry["fail_closed"] = True
        hooks[ev] = [entry] + [e for e in (hooks.get(ev) or []) if MARK not in str(e.get("command", ""))]
    p.parent.mkdir(parents=True, exist_ok=True)
    _backup(p)
    p.write_text(yaml.safe_dump(cfg, sort_keys=False))
    # Hermes asks once per (event, command); running `senti install hermes` is that consent
    allow = hermes_home() / "shell-hooks-allowlist.json"
    data = _load_json(allow) or {"approvals": []}
    for ev, kind in (("pre_tool_call", "pre"), ("post_tool_call", "post")):
        item = {"event": ev, "command": _cmd("hermes", kind)}
        if item not in data["approvals"]:
            data["approvals"].append(item)
    _write_json(allow, data)
    return p


def uninstall_hermes(project: str | None = None) -> Path:
    import yaml
    p = hermes_home() / "config.yaml"
    if p.exists():
        cfg = yaml.safe_load(p.read_text()) or {}
        for ev in list((cfg.get("hooks") or {})):
            cfg["hooks"][ev] = [e for e in cfg["hooks"][ev] or [] if MARK not in str(e.get("command", ""))]
            if not cfg["hooks"][ev]:
                del cfg["hooks"][ev]
        _backup(p)
        p.write_text(yaml.safe_dump(cfg, sort_keys=False))
    allow = hermes_home() / "shell-hooks-allowlist.json"
    if allow.exists():
        data = _load_json(allow)
        data["approvals"] = [a for a in data.get("approvals", []) if MARK not in a.get("command", "")]
        _write_json(allow, data)
    return p


# OpenClaw: a native plugin (before_tool_call) in ~/.openclaw/plugins/senti, linked with OpenClaw's own CLI
def openclaw_plugin_dir() -> Path:
    return Path(os.environ.get("OPENCLAW_STATE_DIR") or HOME / ".openclaw") / "plugins" / "senti"


def install_openclaw(project: str | None = None) -> Path:
    _no_project("OpenClaw", project)
    d = openclaw_plugin_dir()
    d.mkdir(parents=True, exist_ok=True)
    src = resources.files("senti.data").joinpath("openclaw-senti.ts").read_text()
    (d / "index.ts").write_text(src.replace("__SENTI_HOOK__", str(hook_binary())))
    (d / "package.json").write_text(json.dumps({"name": "senti-openclaw", "version": "0.2.0", "type": "module",
                                                "openclaw": {"extensions": ["./index.ts"]}}, indent=2))
    (d / "openclaw.plugin.json").write_text(json.dumps({"id": "senti", "name": "Senti",
                                                        "description": "Checks every tool call with the local Senti engine",
                                                        "activation": {"onStartup": True},
                                                        "configSchema": {"type": "object", "additionalProperties": False}}, indent=2))
    exe = shutil.which("openclaw")
    if exe:
        subprocess.run([exe, "plugins", "install", "--link", str(d), "--force"], check=False)
        subprocess.run([exe, "plugins", "enable", "senti"], check=False)
    else:
        print(f"  openclaw: plugin written to {d}. Activate it with:\n"
              f"    openclaw plugins install --link {d} --force && openclaw plugins enable senti")
    return d


def uninstall_openclaw(project: str | None = None) -> Path:
    d = openclaw_plugin_dir()
    exe = shutil.which("openclaw")
    if exe:
        subprocess.run([exe, "plugins", "disable", "senti"], check=False)
    if d.exists():
        shutil.rmtree(d)
    return d


INSTALL.update({"cursor": install_cursor, "cline": install_cline, "hermes": install_hermes, "openclaw": install_openclaw})
UNINSTALL.update({"cursor": uninstall_cursor, "cline": uninstall_cline, "hermes": uninstall_hermes, "openclaw": uninstall_openclaw})


LAUNCH_AGENT = Path.home() / "Library" / "LaunchAgents" / "am.tumo.senti.plist"


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


# ---------------------------------------------------------------- which assistants are protected
# assistants Senti protects with hooks, detected by their command or their settings folder
DETECT = {"claude": ("claude", ".claude"), "codex": ("codex", ".codex"), "opencode": ("opencode", ".config/opencode"),
          "cursor": ("cursor-agent", ".cursor")}


def detected_agents() -> list[str]:
    home = Path(os.environ.get("HOME") or Path.home())
    return [a for a, (exe, folder) in DETECT.items() if shutil.which(exe) or (home / folder).exists()]


def _protected_file() -> Path:
    return senti_home() / "protected.json"


def protected_agents() -> list[str]:
    try:
        return list(json.loads(_protected_file().read_text()).get("agents", []))
    except (OSError, ValueError):
        return []


def mark_protected(agents: list[str]) -> None:
    p = _protected_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"agents": sorted(set(protected_agents()) | set(agents)), "updated": time.time()}))


def protect_new_assistants() -> list[str]:
    """Hooks for assistants installed after setup. Runs in the engine every minute, only once `senti setup`/`senti join`
    has run on this Mac (so nobody gets hooks they didn't ask for). Returns the assistants it just protected."""
    if not _protected_file().exists():
        return []
    new = [a for a in detected_agents() if a in INSTALL and a not in protected_agents()]
    if not new:
        return []
    if not hook_binary().exists():
        build_hook()
    done = []
    for ag in new:
        try:
            INSTALL[ag](None)
            done.append(ag)
        except OSError:
            continue
    mark_protected(done)
    return done


def uninstall_service() -> None:
    if LAUNCH_AGENT.exists():
        subprocess.run(["launchctl", "unload", str(LAUNCH_AGENT)], capture_output=True)
        LAUNCH_AGENT.unlink()
