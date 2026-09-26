---
type: Architecture
title: Organization backend, profiles and judge routing
description: Admin panel and backend that define profiles per user/role/agent, push them to each Mac, and optionally route grey-zone decisions to a corporate model.
tags: [architecture, backend, enterprise, profiles, admin]
status: draft
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
sources:
  - id: team-req
    resource: claude-code session 973dd678-f568-4b80-aeca-b6d8963be82d (2026-09-26)
    title: Team requirement — hook → profile from backend → local or corporate LLM
    author: human:vargevorgyan
  - id: concept-draft
    resource: AI_Agent_Guardrails_Concept_Draft.docx (concept draft v0.1)
    title: Concept draft — policy server, role profiles, gateways
    author: human:vargevorgyan
---

# Requirement (from the team)

`Codex / Claude Code / OpenCode → hook → profile for this user/agent from the backend → local or corporate LLM decides`.
The judge must be able to use not only local Qwen3-4B but also a **corporate internal model** reached through the backend.[^team-req]

# Key refinement: hooks never call the backend per action

A local **Senti agent** keeps a **cached, signed copy** of the user's profiles, pushed on change (SSE/WebSocket).
Per-action backend calls would add latency and stall agents during outages.

# Flow

1. Profile sync (at login and when an admin changes something).
2. Agent action → hook → local Senti agent (~3 ms).
3. Pick profile (user + agent; per-agent overrides narrow the role profile; an agent never gets more than its user — delegation rule).[^concept-draft]
4. Profile rules settle most actions locally; grey zone → judge named by the profile:
   - **local** Qwen on the Mac, or
   - **corporate** model via the backend's judge gateway.
5. Decision → hook (allow / ask popup / block).
6. Decision logged locally, uploaded in batches for the admin audit view.

# Profile schema (example)

```yaml
profile: developer
applies_to: { roles: [engineering], agents: [claude-code, codex, opencode] }
rules:
  files:   { allow: ["~/code/**"], deny: ["~/.ssh/**", "~/.aws/**", "**/.env*"] }
  network: { allow: [github.com, pypi.org, registry.npmjs.org, "*.corp.internal"], otherwise: ask }
  shell:   { deny: ["sudo *", "rm -rf ~*"], otherwise: judge }
  packages: check_supply_chain
judge:
  mode: local_then_corporate   # local | corporate | local_then_corporate | none
  instructions: |
    Production database hosts are *.prod.corp.internal - any access needs approval.
    Customer data lives in /data/customers - never allowed to leave the machine.
  send_to_corporate: metadata_only   # metadata_only | with_redacted_content | full
on_backend_unreachable: strict_local
approvals: { ask_goes_to: user }     # or owner (autonomous agents), slack channel
```

# Judge modes

| Mode | Grey zone goes to | Trade-off |
|---|---|---|
| `local` | Qwen3-4B on the Mac | private/offline; ~3 GB RAM; weaker model |
| `corporate` | company model via backend | stronger model + company context; needs network |
| `local_then_corporate` | local first; escalate only when local is unsure | best mix |
| `none` | unclear → ask | more prompts |

Latency estimate (not measured): corporate GPU ≈50–300 ms + network, often faster than local 0.5–1.5 s.
Use `max_tokens: 1` + `logprobs` for a single-token verdict.

# Security

Signed profiles (tampered → rejected); metadata-only by default, secrets redacted before any content is sent;
hard rules always enforced locally; backend unreachable → cached profile + local rules/judge, never fail open;
device enrollment with per-device key.

# Backend API (draft)

| Endpoint | Purpose |
|---|---|
| `POST /devices/enroll` | Mac joins org, gets device key |
| `GET /profiles?user&device` + SSE/WebSocket push | signed profiles, live updates |
| `POST /judge` | `{profile_id, task, action_metadata}` → `{verdict, reason, probabilities}` |
| `POST /events` (batched) | audit upload |
| `GET/POST /approvals` | route "ask" to owners/admins |

# Hackathon scope (proposed)

FastAPI + SQLite backend with the endpoints above; one-page admin panel (profiles Developer/PM/Autonomous agent,
judge-mode dropdown, rules, instructions, live decision feed). Demo: switch a profile's judge mode or add
"no network for OpenCode" and see the next action on the Mac obey it without restart.
Open choices: backend location (same Mac vs small VM), admin stack (React via FastAPI vs Next.js), what plays the
"corporate model" — see [Open questions](/roadmap/open-questions.md).

[^team-req]: Team requirement — hook → profile from backend → local or corporate LLM
[^concept-draft]: Concept draft — policy server, role profiles, gateways
