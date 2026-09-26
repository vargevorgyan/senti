---
type: Architecture
title: System overview
description: The four local parts of Senti (hooks, engine, sandbox, app) plus the optional organization backend, and how a single agent action flows through them.
tags: [architecture, overview]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
sources:
  - id: session
    resource: claude-code session 973dd678-f568-4b80-aeca-b6d8963be82d (2026-09-26)
    title: Ideathon planning and prototyping session
  - id: prototype
    resource: /prototype/engine/
    title: Prototype engine source in this repo
---

# Overview

Senti is **not only a hook**. The hook is the doorway; security comes from four parts working together.

| Part | Job | Concept |
|---|---|---|
| **Hooks / plugins** (one per agent) | Intercept each action *before* it runs and ask Senti | [Hook client](/architecture/hook-client.md), [Agent coverage](/integrations/agent-coverage.md) |
| **Senti agent / engine** (one per Mac) | Decide allow / ask / block with rules → detectors → LLM judge | [Decision engine](/architecture/decision-engine.md), [LLM judge](/architecture/llm-judge.md) |
| **Sandbox** | OS-level hard limits on files and network — what hooks cannot see | [Enforcement sandbox](/architecture/enforcement-sandbox.md) |
| **Mac app** | Menu bar, plain-English popup, activity log, per-agent settings | [macOS app](/architecture/macos-app.md) |
| *Org backend (optional)* | Admin panel, profiles per user/role/agent, corporate judge, audit | [Org backend and profiles](/architecture/org-backend-and-profiles.md) |

# Diagram

```
 ┌──────────── ORG BACKEND (optional, company servers) ────────────┐
 │ Admin panel · Policy service (signed profiles) · Judge gateway  │
 │ → corporate model · Audit service                                │
 └──────▲ profile sync (push)     ▲ corporate judge     ▲ audit ────┘
        │                          │ (unclear only)      │ (batched)
 ┌──────┴──────────────────────────┴─────────────────────┴──────────┐
 │ SENTI AGENT (per Mac): profile cache → cache → rules → detectors │
 │   → judge router → local Qwen3-4B | corporate model              │
 │   background: script pre-check on write, reasons, model unload   │
 └──────▲───────────────────────────────────────────────┬───────────┘
        │ Unix socket (~3 ms)                            │ ask/block
   senti-hook / plugin                              Senti.app popup
        ▲                                                
 Claude Code · Codex CLI · OpenCode   ── commands run inside ──► sandbox (srt / Seatbelt)
```

# Life of one action

1. Agent wants to run `python3 helper.py`; its hook runs `senti-hook`, which sends the hook JSON over a Unix socket.
2. Engine picks the profile (user + agent), checks the **decision cache**.
3. **Rules** (µs): hard deny or clearly safe → done (~70% of actions in tests).
4. **Detectors** (ms): secrets, base64 decoding, script static scan, taint → often done.
5. **LLM judge** (0.5–1.5 s local) for the unclear ~25%: verdict first, plain-English reason streamed later.
6. Decision returned; `ask` opens the popup and waits for the user; everything is logged.
7. Whatever was allowed still runs inside the **sandbox**, so hidden behaviour (downloaded code, obfuscation) is contained.

# Design invariants

- Fail closed everywhere (error/timeout/engine down → ask or block).
- The LLM can never override a hard rule.
- Agent-written content is untrusted data for the judge.
- Hooks never call the backend directly; profiles are cached locally and pushed on change.
