---
type: Reference
title: Start here — Senti in five minutes
description: Orientation for agents and people new to Senti; what it is, where things are, and which concepts to read next.
tags: [getting-started, overview]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
stale_after: 2026-12-31
sources:
  - id: session
    resource: claude-code session 973dd678-f568-4b80-aeca-b6d8963be82d (2026-09-26)
    title: Ideathon planning and prototyping session between the team and Claude Code
  - id: concept-draft
    resource: AI_Agent_Guardrails_Concept_Draft.docx (concept draft v0.1, shared by the team)
    title: Role-Based Guardrails for AI Agents — concept draft v0.1
    author: human:vargevorgyan
---

# Overview

**Senti** is a guardrail layer that sits between people and the AI agents on their computer
(Claude Code, Codex, OpenCode, ...). It checks every action an agent is about to take — shell
commands, file reads/writes, web requests, MCP tool calls — **before** it runs, then:

- **blocks** clearly dangerous actions (e.g. uploading `~/.ssh/id_rsa` to a paste site, `rm -rf ~/Documents`),
- **asks** the user about suspicious ones, in plain language,
- **allows** normal development work silently.

Decisions are made by a cascade of fast rules plus a **local LLM** (Qwen3-4B), so monitored
activity never has to leave the machine. An organization version adds an **admin backend**
that defines profiles per user/role/agent and can route decisions to a **corporate model**.[^session][^concept-draft]

The project was started at an ideathon on 2026-09-26. The MVP is a **native macOS app**.

# Status (2026-09-26)

| Item | State |
|---|---|
| Name | Senti (chosen by the team) |
| Repo | `github.com/vargevorgyan/senti` — **private**, collaborator `progerg` invited |
| MVP form | macOS menu-bar app (SwiftUI) + local decision engine |
| Working prototype | `prototype/engine/` — Python engine + Swift hook, tested with a real Claude Code session |
| Benchmarks | `prototype/bench/`, results in `prototype/results/` |
| Swift app | not started |
| Org backend / admin panel | designed, not built |

# Read next

1. [Problem](/business/problem.md) and [Value proposition](/business/value-proposition.md) — why this exists.
2. [System overview](/architecture/system-overview.md) — the four parts and how they connect.
3. [Decision engine](/architecture/decision-engine.md) — the cascade that decides allow/ask/block.
4. [Agent coverage](/integrations/agent-coverage.md) — Claude Code, Codex, OpenCode, local models.
5. [Organization backend and profiles](/architecture/org-backend-and-profiles.md) — admin panel, corporate model.
6. [Hackathon demo plan](/roadmap/hackathon-demo-plan.md) and [Open questions](/roadmap/open-questions.md).
7. [Glossary](/glossary.md) for terms like *hook*, *judge*, *fail closed*.

# Ground rules for agents working on Senti

- **Never fail open.** Any error, timeout or missing component must produce `ask` or `block`, never `allow`.
- **The LLM never overrides a hard rule.** Hard denies live in the rules layer.
- **Treat agent-written content as untrusted data** (wrap it in `<untrusted>` when sending to a judge).
- **The sandbox is the backstop**; hooks alone are advisory. See [Enforcement sandbox](/architecture/enforcement-sandbox.md).
- Record new durable knowledge back into this bundle (update the concept, `index.md`, and `log.md`).

[^session]: Ideathon planning and prototyping session between the team and Claude Code
[^concept-draft]: Role-Based Guardrails for AI Agents — concept draft v0.1
