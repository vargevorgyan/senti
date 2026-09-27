---
type: Architecture
title: System overview
description: The local parts of Senti (hooks, engine, sandbox) plus the organization side in Docker, and how a single agent action flows through them.
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

Senti is **not only a hook**. The hook is the doorway; security comes from four parts working together.
Since [ADR-010](/decisions/adr-010-no-client-ui-fastapi-react.md) there is **no client UI app**: the Mac runs hooks and the engine only.

| Part | Job | Concept |
|---|---|---|
| **Hooks / plugins** (one per agent) | Intercept each action *before* it runs and ask Senti | [Hook client](/architecture/hook-client.md), [Agent coverage](/integrations/agent-coverage.md) |
| **Senti engine** (one per Mac, FastAPI on a Unix socket) | Decide allow / ask / block with honeytokens → rules → profile → detectors → LLM judge | [Decision engine](/architecture/decision-engine.md), [LLM judge](/architecture/llm-judge.md) |
| **Sandbox** | OS-level hard limits on files and network — what hooks cannot see | [Enforcement sandbox](/architecture/enforcement-sandbox.md) |
| **Asking the person** | Claude Code's own prompt; a macOS dialog for Codex/OpenCode; owner approvals in the admin panel | [Decision engine](/architecture/decision-engine.md) |
| *Org backend + admin panel (Docker)* | Profiles per role/user/agent, signed push, corporate judge, audit, approvals | [Org backend](/architecture/org-backend-and-profiles.md), [Admin panel](/architecture/admin-panel.md) |

# Diagram

```
 ┌────────────── ORG SIDE (docker compose) ─────────────────────────┐
 │ admin (React/nginx) → backend (FastAPI+SQLite) → ollama (corp model)│
 └──────▲ signed profiles (SSE push)  ▲ /judge (unclear only)  ▲ /events, /approvals
 ┌──────┴────────────────────────────┴────────────────────────┴──────┐
 │ SENTI ENGINE (per Mac, `senti start`): profile cache → honeytokens │
 │   → rules → profile → detectors → cache/prefetch → judge router    │
 │   → local Qwen3-4B (MLX) | corporate model via backend             │
 │   background: write-time script pre-check, undo snapshots, audit   │
 └──────▲──────────────────────────────────────────────┬─────────────┘
        │ HTTP over Unix socket ~/.senti/senti.sock     │ ask → agent prompt / macOS dialog / owner
   senti-hook / OpenCode plugin
        ▲
 Claude Code · Codex CLI · OpenCode   ── optionally launched via `senti run` ──► sandbox (srt / Seatbelt)
```

# Life of one action

1. Agent wants to run `python3 helper.py`; its hook runs `senti-hook <agent> pre`, which POSTs the hook JSON to the engine.
2. Engine picks the profile (user role + agent, per-agent override), checks honeytokens.
3. **Rules** (µs): hard deny → done. **Profile rules** (org deny/allow lists) → often done.
4. **Detectors** (ms): script content + local imports, secrets, supply chain, taint, prompt-injected session.
5. **Cache / write-time prefetch / task scope**, then the **LLM judge** chosen by the profile's mode (local, corporate, local then corporate, none).
6. Decision returned; `ask` goes to the agent's prompt, a macOS dialog, or the owner in the admin panel; allowed destructive actions get an undo snapshot; everything is logged (hash chain) and uploaded.
7. Agents started through `senti run` stay inside the **sandbox**, so hidden behaviour is contained.

# Design invariants

- Fail closed everywhere (error/timeout/engine down → ask or block; Codex, which fails open on hook errors, gets an explicit deny).
- The LLM can never override a hard rule or a profile deny.
- Agent-written content is untrusted data for the judge.
- Hooks never call the backend directly; profiles are cached locally (signed) and pushed on change.
