---
type: Integration Matrix
title: Agent coverage
description: Which AI agents Senti supports and how each is intercepted (hooks, plugin, MCP proxy, sandbox), including the demo trio Claude Code, Codex and OpenCode with local models.
tags: [integrations, agents, coverage]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
stale_after: 2026-12-31
sources:
  - id: hol-matrix
    resource: https://github.com/hashgraph-online/hol-guard/blob/main/docs/guard/harness-support.md
    title: HOL Guard harness support matrix (read, not independently verified)
    last_modified: 2026-09-26
  - id: team-req
    resource: claude-code session 973dd678-f568-4b80-aeca-b6d8963be82d (2026-09-26)
    title: Team decision — demo must support Claude, ChatGPT (Codex) and local models via OpenCode
    author: human:vargevorgyan
---

# Principle

Senti is **vendor-neutral**. Its own judge is a local open model; it depends on neither Anthropic nor OpenAI.
Agents do not talk to each other through Senti — each agent independently asks "may I do this?".
Each agent has a small **adapter** that normalizes its hook JSON into one internal event format
(tool, command/path/URL, agent, session). The model *behind* an agent does not matter.

**Sub-agents** (e.g. Claude Code spawning helper agents) are covered automatically: their tool calls go through the same hooks with their session/agent identity, so per-agent rules still apply.
For local-model specifics see [Local models](/integrations/local-models.md).

# Demo trio (team decision)[^team-req]

| Agent | Model | Mechanism | Status | Concept |
|---|---|---|---|---|
| **Claude Code** | Claude | `PreToolUse` + `UserPromptSubmit` hooks | done, tested live | [Claude Code](/integrations/claude-code.md) |
| **Codex CLI** | ChatGPT / OpenAI | `PreToolUse` hooks in `~/.codex/config.toml` (Claude-like format) | adapter needed | [Codex CLI](/integrations/codex-cli.md) |
| **OpenCode** | **local models** (Ollama, LM Studio, OpenAI-compatible) | TypeScript plugin with `tool.execute.before` (throw = block) | plugin needed | [OpenCode](/integrations/opencode.md) |

# Other agents with blocking hooks (per HOL Guard's matrix)[^hol-matrix]

Cursor (`beforeShellExecution`, `beforeReadFile`, `beforeMCPExecution`, `preToolUse` in `.cursor/hooks.json`),
GitHub Copilot CLI (`preToolUse` in `.github/hooks/*.json`), Cline (`PreToolUse`), Gemini CLI (hooks/extensions), Kimi, and others.
HOL Guard's adapters are Apache-2.0 and can be reused with attribution.

# Agents without hooks

| Mechanism | Covers |
|---|---|
| **MCP proxy** | Tool calls of any MCP-speaking agent |
| **Local model gateway** (idea) | DIY agents calling Ollama/LM Studio/MLX via an OpenAI-compatible API: Senti inspects the model's proposed tool calls and replaces blocked ones |
| **Sandbox wrapper** (`srt`) | Anything launched through it — no per-action popups, but hard limits |
| **Direct API** | Custom/multi-agent systems call Senti's "check this action" endpoint |

# Not coverable locally

The **ChatGPT desktop app's agent mode** runs on OpenAI's servers; nothing local can intercept it. Use **Codex CLI** as the "ChatGPT" agent in demos.

# Capacity (estimate, not measured)

Rules handle hundreds of checks/s. The single local LLM does ~1 verdict per 0.7–1.4 s. With ~25% of actions
reaching the LLM and agents acting every 3–10 s, one Mac should serve roughly 10–20 concurrently busy agents
before queueing. Scale via caching, batching, or a corporate GPU judge.
