"""Enforcement backstop: generate per-agent sandbox-runtime (srt) settings from the active profile.

Hooks only see what an agent *reports*. The sandbox limits what the whole process tree can actually read,
write and reach, so downloaded or obfuscated code is contained even if every check misses it.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from .config import senti_home, socket_path

BASE_DENY_READ = ["~/.ssh", "~/.aws", "~/.gnupg", "~/.config/gcloud", "~/.kube", "~/.docker/config.json", "~/.netrc",
                  "~/.npmrc", "~/.pypirc", "~/Library/Keychains", "~/Library/Cookies", "~/Library/Messages",
                  "~/Library/Application Support/Google/Chrome", "~/Library/Safari", "~/.password-store",
                  "**/.env", "**/.env.*", str(senti_home())]
BASE_DOMAINS = ["github.com", "*.github.com", "api.github.com", "raw.githubusercontent.com", "codeload.github.com",
                "objects.githubusercontent.com", "pypi.org", "files.pythonhosted.org", "registry.npmjs.org", "*.npmjs.org",
                "crates.io", "static.crates.io", "proxy.golang.org"]
AGENT_DOMAINS = {"claude": ["api.anthropic.com", "statsig.anthropic.com", "*.anthropic.com", "claude.ai"],
                 "codex": ["api.openai.com", "chatgpt.com", "*.openai.com", "*.chatgpt.com", "auth.openai.com"],
                 "opencode": ["opencode.ai", "*.opencode.ai", "models.dev", "localhost"]}


def srt_settings(profile: dict, agent: str, project: str) -> dict:
    rules = profile.get("rules") or {}
    files, net = rules.get("files") or {}, rules.get("network") or {}
    deny_read = list(dict.fromkeys(BASE_DENY_READ + [p for p in files.get("deny", []) if not p.startswith("re:")]))
    domains = list(dict.fromkeys(BASE_DOMAINS + AGENT_DOMAINS.get(agent, []) + list(net.get("allow") or [])))
    if net.get("otherwise") == "allow":
        domains.append("*")
    home = str(Path.home())
    agent_state = {"claude": [f"{home}/.claude", f"{home}/.claude.json"], "codex": [f"{home}/.codex"],
                   "opencode": [f"{home}/.local/share/opencode", f"{home}/.cache/opencode", f"{home}/.config/opencode"]}
    return {
        "network": {"allowedDomains": domains, "deniedDomains": list(net.get("deny") or []),
                    "allowUnixSockets": [socket_path()], "allowLocalBinding": True},
        "filesystem": {"denyRead": deny_read, "allowRead": [],
                       "allowWrite": [project, "/tmp", "/private/tmp", f"{home}/.cache", *agent_state.get(agent, [])],
                       "denyWrite": [str(senti_home()), "**/.env", f"{home}/.claude/settings.json", f"{home}/.codex/config.toml",
                                     f"{home}/.codex/hooks.json", f"{home}/.config/opencode/plugins",
                                     f"{project}/.claude/settings.json", f"{project}/.claude/settings.local.json",
                                     f"{project}/.codex/hooks.json", f"{project}/.codex/config.toml", f"{project}/.opencode/plugins",
                                     f"{project}/.opencode/plugin", f"{project}/.git/hooks", f"{project}/.git/config"]},
        "enableWeakerNestedSandbox": False,
    }


def write_settings(profile: dict, agent: str, project: str) -> Path:
    d = senti_home() / "sandbox"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{agent}.srt.json"
    p.write_text(json.dumps(srt_settings(profile, agent, project), indent=2))
    os.chmod(p, 0o600)
    return p


def command(settings_path: Path, argv: list[str]) -> list[str]:
    srt = shutil.which("srt")
    base = [srt] if srt else ["npx", "-y", "@anthropic-ai/sandbox-runtime"]
    return [*base, "--settings", str(settings_path), *argv]
