---
type: Reference
title: Start here — Senti in five minutes
description: Orientation for agents and people new to Senti; what it is, where things are, and which concepts to read next.
tags: [getting-started, overview]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-27T02:00:00Z' }
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

Started at an ideathon on 2026-09-26; fully built on 2026-09-27. **No client UI app**: the Mac runs hooks + a local engine;
the organization side (backend, admin panel, corporate model) runs in Docker ([ADR-010](/decisions/adr-010-no-client-ui-fastapi-react.md)).

# Status (2026-09-27)

| Item | State |
|---|---|
| Name / repo | Senti · `github.com/vargevorgyan/senti` (private); full build on branch `feat/full-build` (not pushed) |
| Local engine | `engine/` — Python package `senti`, FastAPI on a Unix socket, CLI; 68 tests |
| Hooks | Claude Code, Codex CLI, OpenCode — all tested live |
| Org backend | `backend/` — FastAPI + SQLite, Docker; 13 tests |
| Admin panel | `admin/` — React, Docker (nginx), designer's design system; 7 Playwright tests |
| Corporate model | Ollama container (`qwen2.5:3b`), any OpenAI-compatible endpoint |
| End-to-end | `scripts/e2e_modes.py` 14/14 (all judge modes, push, overrides, approvals, audit) |
| Task board | `/TASKS.md` in the repo root — done / remaining work for the next agent |

# Read next

1. [Code guide](/code-guide.md) — where the code is and how to run it.
2. [System overview](/architecture/system-overview.md) — parts and how they connect.
3. [Decision engine](/architecture/decision-engine.md) and [LLM judge](/architecture/llm-judge.md).
4. [Organization backend and profiles](/architecture/org-backend-and-profiles.md) and [Admin panel](/architecture/admin-panel.md).
5. [Agent coverage](/integrations/agent-coverage.md), [Real-agent tests](/research/real-agent-tests.md) and [Real incidents replayed](/research/agent-incidents.md) (evidence for the pitch).
6. [Demo plan](/roadmap/hackathon-demo-plan.md), [Roadmap](/roadmap/roadmap.md), [Open questions](/roadmap/open-questions.md).
7. [Problem](/business/problem.md), [Value proposition](/business/value-proposition.md) and [Use cases](/use-cases/) — why this exists and who it serves.
8. [Glossary](/glossary.md).

# Ground rules for agents working on Senti

- **Never fail open.** Any error, timeout or missing component must produce `ask` or `block`, never `allow`.
- **The LLM never overrides a hard rule.** Hard denies live in the rules layer.
- **Treat agent-written content as untrusted data** (wrap it in `<untrusted>` when sending to a judge).
- **The sandbox is the backstop**; hooks alone are advisory. See [Enforcement sandbox](/architecture/enforcement-sandbox.md).
- Record new durable knowledge back into this bundle (update the concept, `index.md`, and `log.md`) and keep `/TASKS.md` current.

[^session]: Ideathon planning and prototyping session between the team and Claude Code
[^concept-draft]: Role-Based Guardrails for AI Agents — concept draft v0.1
