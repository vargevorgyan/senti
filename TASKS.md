# Senti — build task board

Living task summary for the full build (branch `feat/full-build`). Any agent picking this up:
read `AGENTS.md`, then this file, then `.okf/getting-started.md`. Update this file as you go
(move items, add notes, date entries in the log at the bottom). All docs are in English.

## Scope decisions (2026-09-27, from the repo owner)

- **No client UI app on the Mac.** Client side = hooks/plugins + a local engine (host-native, never in Docker).
  The SwiftUI app from ADR-001 is dropped (superseded by ADR-010).
- `ask` verdicts use each agent's native permission prompt (Claude Code, Codex); OpenCode gets a macOS dialog via `osascript`.
- **Org side in Docker:** FastAPI backend + React admin panel + a small "corporate model" (Ollama, CPU) — must fit a 16 GB laptop.
- Backend = Python FastAPI. Frontend = React (Vite). Local judge = MLX Qwen3-4B on the host.
- Admin UI follows the designer's design system (copied to `docs/design/`, source: claude.ai artifact CZ821iLED5QtDoAh7JWzQg).

## Layout (target)

| Path | What |
|---|---|
| `engine/` | Host-native Python package `senti`: FastAPI over a Unix socket, cascade, judges, profiles, audit, CLI, installers |
| `engine/hook/senti-hook.swift` | Compiled hook client (HTTP over Unix socket, fail closed) |
| `engine/plugins/opencode/` | OpenCode TypeScript plugin |
| `backend/` | Org backend (FastAPI + SQLite), Docker |
| `admin/` | React admin panel, Docker (nginx) |
| `docker-compose.yml` | backend + admin + ollama (corporate model) |
| `prototype/` | Original ideathon prototype (kept for reference/benchmarks) |

## Status

Legend: [x] done · [~] in progress · [ ] todo

### Engine (local, host)
- [ ] Package skeleton, config (`~/.senti`), models
- [ ] Rules L1 + detectors L2 ported from prototype
- [ ] Script inspection: inline `-c/-e`, `package.json` scripts, Makefile targets, local imports, personal-folder deletion in scripts
- [ ] Profiles: schema, evaluation (files/network/shell/packages), per-agent overrides, delegation intersection
- [ ] Signed profile cache (Ed25519), SSE push sync, `strict_local` when backend unreachable
- [ ] Judge interface: LocalJudge (MLX), RemoteJudge (corporate via backend), NoJudge; router modes `local | corporate | local_then_corporate | none`
- [ ] Decision cache, task tracking (UserPromptSubmit), write-time script pre-check, async reasons
- [ ] Audit log (hash-chained JSONL, append-only) + batched upload
- [ ] Adapters: Claude Code, Codex CLI (incl. `apply_patch`), OpenCode, generic `/v1/check`
- [ ] FastAPI server over Unix socket (0600)
- [ ] Swift hook client (HTTP/UDS, fail closed)
- [ ] CLI: start/stop/status/install/uninstall/enroll/log/undo/run
- [ ] Installers: Claude Code settings, Codex config.toml, OpenCode plugin
- [ ] Sandbox: per-agent srt settings generated from profile; `senti run <cmd>`
- [ ] Undo / time machine (APFS clone snapshots before destructive actions)
- [ ] Honeytokens
- [ ] Supply-chain check (offline malicious/typosquat list)
- [ ] Post-read prompt-injection scanning
- [ ] Task scope contract
- [ ] Self-protection (Senti/agent hook configs)

### Org backend (Docker)
- [ ] FastAPI + SQLite models: org, users, roles, agents, devices, profiles, events, approvals, admins
- [ ] Admin auth (JWT), seed admin + default profiles (Developer, PM, Autonomous agent)
- [ ] `POST /devices/enroll`, `GET /profiles` (signed) + SSE push
- [ ] `POST /judge` gateway → corporate model (Ollama OpenAI-compatible)
- [ ] `POST /events` (batched audit), stats
- [ ] `GET/POST /approvals` (ask routed to owner/admin)
- [ ] Tests

### Admin panel (React, Docker)
- [ ] Design tokens from design system, fonts, light/dark
- [ ] Login, overview dashboard (live feed), profiles editor (judge mode, rules, instructions), devices, users, agents, audit log, approvals
- [ ] Playwright e2e

### Infra / QA / docs
- [ ] docker-compose (backend, admin, ollama + model pull)
- [ ] End-to-end simulation re-run against new engine
- [ ] Real-agent tests: Claude Code, Codex CLI, OpenCode
- [ ] Demo: poisoned repo + script
- [ ] README quickstart, `.okf` updates (ADR-010, concepts, log)

## Log
- 2026-09-27: Board created. Branch `feat/full-build`. Design system copied to `docs/design/`.
