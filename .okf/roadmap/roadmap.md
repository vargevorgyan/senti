---
type: Roadmap
title: Product roadmap and feature ideas
description: Near-term engineering work, differentiating feature ideas ranked by value, and the longer-term enterprise path.
tags: [roadmap, features, ideas]
status: draft
stale_after: 2026-12-31
generated: { by: claude-code/2.1.283, at: '2026-09-27T02:00:00Z' }
sources:
  - id: session
    resource: claude-code session 973dd678-f568-4b80-aeca-b6d8963be82d (2026-09-26)
    title: Ideas and alternatives discussion
  - id: concept-draft
    resource: AI_Agent_Guardrails_Concept_Draft.docx (concept draft v0.1)
    title: Concept draft — MVP scope and later items
    author: human:vargevorgyan
---

# Implementation status (2026-09-27, full build)

| Feature | Status |
|---|---|
| Undo / time machine | **done** — APFS-clone snapshots, `senti undo list/restore` |
| Honeytokens | **done** — `senti honeytoken plant DIR`, alarm on read or send |
| Task scope contract | **done (opt-in)** — profile feature `scope_contract`, local judge derives domains |
| Post-read injection scanning | **done** — PostToolUse / tool.execute.after warnings; tainted sessions need a yes for network |
| Cross-agent timeline | **done** — admin Activity/Overview across agents and Macs |
| Package supply-chain check | **done** — offline known-malicious + typosquat lists |
| Secret brokering | **done** — [Secret brokering](/architecture/secret-brokering.md) |
| Local model gateway for DIY agents | **done** — [Model gateway](/architecture/model-gateway.md) |
| Per-agent identity / peer verification | **done** — socket token + `LOCAL_PEERPID` parent-chain check ([Hook client](/architecture/hook-client.md)) |
| Required sandbox per profile | **done** — ask before commands when the agent isn't sandboxed |
| TLS + certificate pinning, JWT revocation | **done** — [Org backend](/architecture/org-backend-and-profiles.md) |
| Engine port to Swift | dropped for now (ADR-010 keeps Python) |

# Differentiating features (ranked)

1. **Undo / time machine** — snapshot affected files (APFS clones) before destructive actions; one click reverts what the agent did. Turns misses into recoverable events.
2. **Honeytokens** — plant fake AWS keys / `.env` entries; any read or send is a near-certain alarm, no LLM needed.
3. **Secret brokering** — agents see placeholders; real values injected only at execution. Exfiltration yields nothing.
4. **Task scope contract** — at prompt submit, the LLM derives expected scope (files, domains); later checks are fast rules. Moves the LLM off the hot path.
5. **Post-read injection scanning** — scan READMEs/web pages/tool output for prompt injection and warn before the agent acts.
6. **Cross-agent timeline** — one log for all agents; seed of the enterprise dashboard.
7. **Package supply-chain check** — offline known-malicious / typosquat list.

# Engineering next steps

- Resolve `package.json` scripts, `Makefile`, test runners; follow local imports; inline `-c`/`-e` code to judge ([Script inspection](/architecture/script-inspection.md)).
- Detector for personal-folder deletion inside scripts; alert at write time on malicious files.
- LLM priority/preemption so background work never delays a verdict.
- Per-agent identity tokens + peer verification on the socket.
- Port engine to Swift (MLX Swift), unload model when idle.
- Try few-shot examples in the cached system prompt (free per request thanks to the prefix cache) to see if the smaller Qwen3-1.7B becomes safe enough.
- Local model gateway for DIY agents (OpenAI-compatible proxy inspecting tool calls).

# Enterprise path (concept draft)[^concept-draft]

Policy server with role profiles from the identity provider; corporate filter model; endpoint client rolled out via MDM (Jamf, Intune);
**LLM gateway** redacting secrets before cloud models; autonomous-agent identities with owners, budgets and expiry; observe-first rollout.
MVP in the draft: 3 profiles (developer, PM, autonomous agent), hooks for Claude Code and Cursor.

Removed from the roadmap by the team (2026-09-26): MCP gateway, judge fine-tuning.

[^concept-draft]: Concept draft — MVP scope and later items
