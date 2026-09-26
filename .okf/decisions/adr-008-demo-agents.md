---
type: Decision
title: "ADR-008: Demo agents are Claude Code, Codex CLI and OpenCode"
description: "The demo must show Claude (Claude Code), ChatGPT (Codex CLI) and local models (OpenCode) protected by the same engine."
tags: [decision, agents, demo]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
sources:
  - id: session
    resource: claude-code session 973dd678-f568-4b80-aeca-b6d8963be82d (2026-09-26)
    title: Ideathon planning session
    author: human:vargevorgyan
---

# Decision
Claude Code (hooks, done), Codex CLI as the "ChatGPT" agent (the ChatGPT app's agent mode runs in OpenAI's cloud and cannot be hooked),
OpenCode for local models (plugin). Chosen by the team over a custom local-model gateway agent.
See [Agent coverage](/integrations/agent-coverage.md).
