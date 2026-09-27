---
type: Architecture
title: Organization backend, profiles and judge routing
description: FastAPI backend and React admin panel (Docker) that define profiles per role/user/agent, push signed bundles to each Mac, route grey-zone decisions to a corporate model, collect audit and approvals.
tags: [architecture, backend, enterprise, profiles, admin]
status: draft
generated: { by: claude-code/2.1.283, at: '2026-09-27T02:00:00Z' }
sources:
  - id: team-req
    resource: claude-code session 973dd678-f568-4b80-aeca-b6d8963be82d (2026-09-26)
    title: Team requirement — hook → profile from backend → local or corporate LLM
    author: human:vargevorgyan
  - id: concept-draft
    resource: AI_Agent_Guardrails_Concept_Draft.docx (concept draft v0.1)
    title: Concept draft — policy server, role profiles, gateways
    author: human:vargevorgyan
  - id: build
    resource: /backend/app, /engine/src/senti/sync.py, /docker-compose.yml
    title: Full-build backend and sync source
    author: claude-code/2.1.283
---

# Requirement (from the team)

`Codex / Claude Code / OpenCode → hook → profile for this user/agent from the backend → local or corporate LLM decides`.
The judge must be able to use not only local Qwen3-4B but also a **corporate internal model** reached through the backend.[^team-req]

# Status: built (2026-09-27)

FastAPI + SQLite in Docker (`backend/`), React admin panel (`admin/`, see [Admin panel](/architecture/admin-panel.md)),
Ollama as the corporate model. Verified end to end by `scripts/e2e_modes.py` (14/14) — see [Real-agent tests](/research/real-agent-tests.md).

# Key refinement: hooks never call the backend per action

The local engine keeps a **cached, Ed25519-signed copy** of its profile bundle (`~/.senti/profiles.signed.json`), verified
against the org key pinned at enrollment; tampered caches are ignored. Updates are pushed over SSE; a profile change reaches
the Mac in ~0.2 s and clears the engine's decision cache.

# Flow

1. `senti enroll --backend URL --code CODE --email E` → device token + org public key; the user is created with the code's role.
2. Engine fetches `GET /api/v1/device/profiles` (signed bundle: default profile + per-agent assignments + the profiles) and listens on `/api/v1/device/stream`.
3. Agent action → hook → engine (~3 ms); profile = role profile, or a per-user per-agent override set by the admin, then narrowed by the profile's `agent_overrides` (delegation: never more than the user).
4. Rules settle most actions locally; grey zone → judge named by the profile.
5. `ask` → user (agent prompt/dialog) or, with `approvals.ask_goes_to: owner|admin`, `POST /api/v1/approvals` and wait (timeout → block).
6. Decisions go to the local hash-chained log and are uploaded in batches (`POST /api/v1/events`); heartbeat carries engine status.

# Profile schema (as implemented)

```yaml
id: developer
applies_to: { roles: [engineering], agents: [claude, codex, opencode] }
rules:
  files:   { allow: [], deny: ["~/.ssh/**", "~/.aws/**", "**/.env*", "/data/customers/**"], ask: [], write: allow, outside_allow: ask }
  network: { allow: [github.com, pypi.org, "*.corp.internal"], deny: [webhook.site], ask: ["*.prod.corp.internal"], otherwise: judge }   # hosts also from psql/mysql/redis-cli/mongosh
  shell:   { allow: [], deny: ["sudo *", "rm -rf ~*"], ask: ["git push --force*"], otherwise: judge }
  mcp:     { allow: [], deny: [], otherwise: judge }
  packages: check_supply_chain          # check_supply_chain | allow | ask | block
judge:
  mode: local_then_corporate            # local | corporate | local_then_corporate | none
  instructions: "Production database hosts are *.prod.corp.internal - any access needs approval."
  send_to_corporate: metadata_only      # metadata_only | with_redacted_content | full
on_backend_unreachable: strict_local    # strict_local | cached
approvals: { ask_goes_to: user }        # user | owner | admin
features: { undo: true, honeytokens: true, injection_scan: true, scope_contract: false, sandbox: true }
agent_overrides: { opencode: { rules: { network: { otherwise: block, allow: [] } } } }
```

Seeded profiles: **Developer**, **PM / Product**, **Autonomous agent** (network otherwise block, approvals to owner) from the concept draft.

# Judge modes

| Mode | Grey zone goes to | Trade-off |
|---|---|---|
| `local` | Qwen3-4B on the Mac | private/offline; ~3 GB RAM; weaker model |
| `corporate` | company model via backend | stronger model + company context; needs network (unreachable + strict_local → local) |
| `local_then_corporate` | local first; corporate when local says ask or confidence < 0.8 | best mix |
| `none` | unclear → ask | more prompts |

# Lesson: encode hard policy as rules, not only judge instructions

In the playground the 3B corporate model first **allowed** `psql -h billing.prod.corp.internal` although the Developer
instructions say production hosts need approval. Fixes: `network.ask` lists (DB clients' hosts are extracted too) enforce it
deterministically, and both judge prompts now say policy notes override the model's own judgement (the model then answered ask, p=0.78).

# Transport and sessions (implemented)

- **TLS by default:** the admin container serves HTTPS on 8443 with a self-signed certificate created on first start (or yours in
  `/tls`); HTTP only redirects. The Devices page shows `senti enroll --backend https://HOST:8443 --fingerprint <sha256> …`; the engine
  pins that exact certificate and refuses plain HTTP to non-local backends (`--insecure-http` for labs).
- **Admin sessions:** JWTs carry a token version; changing the password or "Sign out everywhere" revokes all sessions. The SSE stream
  uses a 60-second single-purpose ticket, never the session token.
- **Enrollment:** a second Mac for an existing person needs a personal code (bound to their email); codes decrement atomically;
  deleted people are retired (address freed, devices revoked, audit kept).

# Security

Signed bundles; device tokens stored hashed; revocation (`401` → engine keeps last verified profile, marks backend unreachable);
metadata-only by default and secrets redacted before content is sent; hard rules always local; admin JWT secret random per
install unless set; admin changes recorded in the change log.

# Backend API (implemented, prefix `/api/v1`)

| Endpoint | Purpose |
|---|---|
| `POST /devices/enroll` | Mac joins org with an enrollment code |
| `GET /device/profiles`, `GET /device/stream` (SSE) | signed bundle, live push |
| `POST /device/heartbeat` | engine status for the Devices page |
| `POST /judge` | corporate judge gateway (profile instructions added server-side) |
| `POST /events` | batched, idempotent audit upload |
| `POST /approvals`, `GET /approvals/{id}` | route "ask" to owner/admin and poll |
| `POST /auth/login`, `/admin/*` | admin API: overview, profiles, roles, users, devices, enrollment codes, events (+CSV), approvals, corporate model settings, playground, change log, SSE stream |

[^team-req]: Team requirement — hook → profile from backend → local or corporate LLM
[^concept-draft]: Concept draft — policy server, role profiles, gateways
