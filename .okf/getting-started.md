---
type: Reference
title: Start here — Senti in five minutes
description: Orientation for agents and people new to Senti; what it is, where things are, and which concepts to read next.
tags: [getting-started, overview]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-27T16:00:00Z' }
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

Two things work together, both set up once by the company:

1. **Hook filter on every employee's Mac.** A thin Senti agent (~100 MB, **no AI model on the Mac**) decides obvious actions
   itself in milliseconds and sends unclear ones to the **company's AI filter** in the company cloud
   ([ADR-012](/decisions/adr-012-company-cloud-ai-filter.md)). Hard rules still protect when the cloud is unreachable.
2. **Server gateway (MCP).** Agents reach the company server's files, database and commands only through Senti; the admin
   describes access per role in plain English and a supervisor model decides what the rules don't cover
   ([Server gateway](/architecture/server-gateway.md), [ADR-011](/decisions/adr-011-server-gateway.md)).[^session][^concept-draft]

Started at an ideathon on 2026-09-26; built on 2026-09-27. **No client UI app** ([ADR-010](/decisions/adr-010-no-client-ui-fastapi-react.md)).

# Status (2026-09-27)

| Item | State |
|---|---|
| Repo | `github.com/vargevorgyan/senti` (private), work on `main` |
| Company side | `./senti-server` installer → backend (FastAPI + SQLite), admin panel (React), company AI (Ollama or any OpenAI-compatible API), MCP gateway — Docker |
| Employee Mac | `senti setup --key …` (from the invite): join, start, protect installed assistants, connect them to the company server, start at login |
| Assistants | Claude Code, Codex CLI, OpenCode tested live; Cursor, Cline, Hermes, OpenClaw built, not live-tested |
| Tests | engine 278, backend 106, admin Playwright 7; e2e judge modes 14/14 |
| Task board | `/TASKS.md` — done / remaining work |

# Read next

1. [Customer onboarding](/guides/customer-onboarding.md) — the whole flow in three steps; then the other [Guides](/guides/).
2. [System overview](/architecture/system-overview.md) — parts and how they connect; [Code guide](/code-guide.md) — where the code is.
3. [Decision engine](/architecture/decision-engine.md) and [LLM judge](/architecture/llm-judge.md).
4. [Organization backend and profiles](/architecture/org-backend-and-profiles.md), [Admin panel](/architecture/admin-panel.md),
   [Access and credentials](/architecture/access-and-credentials.md) and [Server gateway](/architecture/server-gateway.md).
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
