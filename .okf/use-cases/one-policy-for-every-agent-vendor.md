---
type: Use Case
title: One policy for every agent vendor
description: Claude Code, Codex (ChatGPT) and OpenCode are governed by the same rules and the same log, regardless of which company made the agent.
tags: [use-case, security]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-27T09:00:00Z' }
sources:
  - id: kb
    resource: /.okf (architecture, research, business sections)
    title: Senti knowledge base — implemented behaviour and test results
    author: claude-code/2.1.283
---

# Who

Company whose people use several AI agents.

# Situation

Each vendor has its own settings and none protects the others; policies drift and nobody sees the whole picture.

# What Senti does

1. Hooks/plugins for each agent send actions to the same local engine and profile.
2. Where an agent has no native "ask" (Codex, OpenCode), Senti shows its own macOS dialog; where hooks fail open on errors (Codex), Senti's hook answers an explicit deny.
3. Admins see all agents in one timeline and can still tighten one vendor's agent specifically.

# Features involved

Adapters for Claude Code, Codex CLI, OpenCode; generic API and model gateway for the rest.

# How well it is verified

**Verified live** with all three agents on the same demo repo.

# Limits

Cursor, Copilot CLI and Gemini CLI have blocking hooks but no Senti adapter yet; agents that run in a vendor's cloud (ChatGPT agent mode) can't be intercepted locally.

# Related

- [agent coverage](/integrations/agent-coverage.md)
- [adr 008 demo agents](/decisions/adr-008-demo-agents.md)
