---
type: Use Case
title: The agent wanders off its task
description: Asked to fix CSS, the agent opens billing configuration or credentials; the task-aware judge notices it doesn't fit and asks.
tags: [use-case, individual]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-27T09:00:00Z' }
sources:
  - id: kb
    resource: /.okf (architecture, research, business sections)
    title: Senti knowledge base — implemented behaviour and test results
    author: claude-code/2.1.283
---

# Who

Developer or non-technical user giving an agent a narrow task.

# Situation

Task: *"Fix the hero button on the landing page."* The agent then reads `services/billing/config.yaml` and `~/.aws/credentials`.

# What Senti does

1. Senti records the person's prompt as the session **task** (`UserPromptSubmit` / `chat.message`).
2. Reading credentials is a hard block; reading a config file inside the project goes to the **judge together with the task**, which sees it doesn't fit and returns **ask** with a plain-English reason.
3. The person answers in the agent's own prompt (Claude Code) or a macOS dialog (Codex, OpenCode).

# Features involved

Task tracking, LLM judge (local Qwen3-4B or corporate), plain-language reasons.

# How well it is verified

**Tested** in the end-to-end simulation (session "off-task").

# Limits

Judges can be over-cautious on harmless off-task actions (1–2 of 39 safe actions asked in simulation).

# Related

- [llm judge](/architecture/llm-judge.md)
- [end to end simulation](/research/end-to-end-simulation.md)
