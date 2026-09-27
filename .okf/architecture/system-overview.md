---
type: Architecture
title: System overview
description: The parts of Senti — thin agent on each Mac, company cloud (backend, admin panel, company AI filter, MCP server gateway) — and how an agent action flows through them.
tags: [architecture, overview]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-27T02:00:00Z' }
sources:
  - id: session
    resource: claude-code session 973dd678-f568-4b80-aeca-b6d8963be82d (2026-09-26)
    title: Ideathon planning and prototyping session
  - id: prototype
    resource: /prototype/engine/
    title: Prototype engine source in this repo
  - id: build
    resource: /engine/src/senti, /backend/app, /admin/src
    title: Full-build source code
    author: claude-code/2.1.283
---

# Overview

Senti is **not only a hook**. The hook is the doorway; security comes from the parts below working together.
There is **no client UI app** ([ADR-010](/decisions/adr-010-no-client-ui-fastapi-react.md)) and **no AI model on employees'
Macs** ([ADR-012](/decisions/adr-012-company-cloud-ai-filter.md)).

| Part | Where | Job | Concept |
|---|---|---|---|
| **Hooks / plugins** | each Mac, per assistant | Intercept each action *before* it runs and ask Senti | [Hook client](/architecture/hook-client.md), [Agent coverage](/integrations/agent-coverage.md) |
| **Thin Senti agent** (engine) | each Mac (~100 MB) | Rules, detectors, script reading, undo, honeytokens; unclear cases → company AI | [Decision engine](/architecture/decision-engine.md) |
| **Local MCP bridge** | each Mac | Lets assistants reach the server gateway without certificates or tokens in their configs | [Connecting assistants](/guides/connecting-assistants.md) |
| **Sandbox** | each Mac | OS-level hard limits on files and network — what hooks cannot see | [Enforcement sandbox](/architecture/enforcement-sandbox.md) |
| **Backend + admin panel** | company cloud (Docker) | Profiles, people and invites, signed push, audit, approvals | [Org backend](/architecture/org-backend-and-profiles.md), [Admin panel](/architecture/admin-panel.md), [Access and credentials](/architecture/access-and-credentials.md) |
| **Company AI filter** | company cloud | Decides unclear actions for every Mac; supervises the gateway | [LLM judge](/architecture/llm-judge.md) |
| **MCP server gateway** | company cloud | Agents use the server's files, database and commands only through Senti, under plain-English role rules | [Server gateway](/architecture/server-gateway.md) |

# Diagram

```
 ┌──────────────────────── COMPANY CLOUD (installed once with ./senti-server) ────────────────────────┐
 │ admin panel (React/nginx) ── backend (FastAPI + SQLite) ── company AI filter (Ollama / any OpenAI API) │
 │                              └─ MCP server gateway → shared files · SQLite · commands (no shell)   │
 └──────▲ signed profiles (SSE)   ▲ /judge (unclear only)   ▲ /events, /approvals   ▲ /api/v1/mcp/ ─────┘
 ┌──────┴─────────────────────────┴────────────────────────┴───────────────────────┴──────────────────┐
 │ EMPLOYEE MAC (senti setup): thin Senti agent — honeytokens → rules → profile → detectors → cache →  │
 │   company AI · undo snapshots · audit · sandbox profiles        local MCP bridge (senti mcp) ───────┘
 └──────▲──────────────────────────────────────────────────────────────────────────▲────────────────
        │ hook (senti-hook / plugin) before every action                            │ MCP (company-server)
 Claude Code · Codex · OpenCode · Cursor · …  ──────────────────────────────────────┘
```

# Life of one action

1. Agent wants to run `python3 helper.py`; its hook runs `senti-hook <agent> pre`, which POSTs the hook JSON to the engine.
2. Engine picks the profile (user role + agent, per-agent override), checks honeytokens.
3. **Rules** (µs): hard deny → done. **Profile rules** (org deny/allow lists) → often done.
4. **Detectors** (ms): script content + local imports, secrets, supply chain, taint, prompt-injected session.
5. **Cache / write-time prefetch / task scope**, then the **company AI filter** (the judge chosen by the profile: company AI by default; a local model only on personal Macs; or none = ask).
6. Decision returned; `ask` goes to the agent's prompt, a macOS dialog, or the owner in the admin panel; allowed destructive actions get an undo snapshot; everything is logged (hash chain) and uploaded.
7. Agents started through `senti run` stay inside the **sandbox**, so hidden behaviour is contained.

# Design invariants

- Fail closed everywhere (error/timeout/engine down → ask or block; Codex, which fails open on hook errors, gets an explicit deny).
- The LLM can never override a hard rule or a profile deny.
- Agent-written content is untrusted data for the judge.
- Hooks never call the backend directly; profiles are cached locally (signed) and pushed on change.
