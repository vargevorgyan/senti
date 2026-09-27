"""Registry of supported agents: display name, whether the agent can ask the person itself, how to recognise its
process (peer verification), which API hosts it needs inside a sandbox. Adapters (payload ↔ Action) live in adapters.py."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentSpec:
    id: str
    name: str
    native_ask: bool                      # the agent shows its own permission prompt for "ask"
    markers: tuple[str, ...] = ()         # process names that identify it (identity.py)
    verify_identity: bool = False         # enforce the peer check (only for agents verified live)
    domains: tuple[str, ...] = ()         # API hosts it needs when sandboxed
    hook_based: bool = True               # installed via hooks/plugins (vs. API-only)
    live_tested: bool = False


AGENTS: dict[str, AgentSpec] = {a.id: a for a in [
    AgentSpec("claude", "Claude Code", True, ("claude",), True,
              ("api.anthropic.com", "statsig.anthropic.com", "*.anthropic.com", "claude.ai"), live_tested=True),
    AgentSpec("codex", "Codex", False, ("codex",), True,
              ("api.openai.com", "chatgpt.com", "*.openai.com", "*.chatgpt.com", "auth.openai.com"), live_tested=True),
    AgentSpec("opencode", "OpenCode", False, ("opencode",), True, ("opencode.ai", "*.opencode.ai", "models.dev", "localhost"),
              live_tested=True),
    # Added 2026-09-27 from primary-source research (docs, source, binaries); not yet exercised with the real agents.
    AgentSpec("cursor", "Cursor", True, ("cursor", "cursor-agent"), False, ("*.cursor.sh", "*.cursor.com", "cursor.com")),
    AgentSpec("cline", "Cline", False, ("cline", "code", "cursor", "windsurf", "antigravity", "codium", "vscodium"), False,
              ("api.cline.bot", "*.cline.bot")),
    AgentSpec("hermes", "Hermes Agent", True, ("hermes",), False, ("openrouter.ai", "*.nousresearch.com", "inference-api.nousresearch.com")),
    AgentSpec("openclaw", "OpenClaw", True, ("openclaw",), False, ("*.openclaw.ai",)),
    AgentSpec("generic", "Other agents", True, (), False, (), hook_based=False),
    AgentSpec("gateway", "DIY agents (gateway)", False, (), False, (), hook_based=False),
]}


def hook_agents() -> list[str]:
    return [a.id for a in AGENTS.values() if a.hook_based]


def name(agent: str) -> str:
    return AGENTS[agent].name if agent in AGENTS else agent
