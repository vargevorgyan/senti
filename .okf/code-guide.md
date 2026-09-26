---
type: Reference
title: Code guide (full build)
description: Map of the production code — engine (host-native), backend and admin panel (Docker), hooks/plugins, tests, e2e and demo scripts — and how to run each part.
tags: [code, engine, backend, admin, setup]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-27T01:45:00Z' }
stale_after: 2026-12-31
sources:
  - id: repo
    resource: /engine, /backend, /admin, /scripts, /demo, /docker-compose.yml
    title: Senti source tree on branch feat/full-build
---

# Layout

| Path | What | Runs |
|---|---|---|
| `engine/src/senti/` | Python package `senti` — the local engine and CLI | natively on the Mac (never Docker) |
| `engine/hook/senti-hook.swift` | Compiled hook client: HTTP/1.1 over the Unix socket, fail closed per agent | spawned by agents |
| `engine/src/senti/data/opencode-senti.ts` | OpenCode plugin template (installed by `senti install opencode`) | inside OpenCode |
| `backend/app/` | Org backend: FastAPI + SQLite (admin API, device API, judge gateway, SSE) | Docker (`backend`) |
| `admin/src/` | React (Vite, TypeScript) admin panel, design tokens from `docs/design/` | Docker (`admin`, nginx) |
| `docker-compose.yml` | backend + admin + Ollama "corporate model" | Docker |
| `scripts/e2e_modes.py` | End-to-end check of all judge modes, push, overrides, approvals, audit upload | host |
| `demo/make-demo-repo.sh` | Poisoned demo repo (fake secrets, `*.invalid` targets) | host |
| `prototype/` | Original ideathon prototype and benchmarks (reference only) | — |

# Engine modules (`engine/src/senti/`)

| Module | Responsibility |
|---|---|
| `server.py` | FastAPI app on a `0600` Unix socket: `/v1/hook/{agent}`, `/v1/check`, `/v1/status`, `/v1/decisions`, `/v1/snapshots`, `/v1/reload`, `/v1/audit/verify` |
| `adapters.py` | Normalise Claude Code / Codex / OpenCode / generic payloads into `Action`; render each agent's reply; brand-voice reasons |
| `engine.py` | The cascade (honeytokens → rules → profile → detectors → allowlist/cache/prefetch → scope → judge router), ask resolution (native / dialog / owner approval), undo snapshots, injection taint, audit |
| `rules.py` | L1 rules + L2 detectors (shell parsing, npm/Makefile resolution, inline code, import following, script scan, secrets, redaction) |
| `profiles.py` | Profile schema, Ed25519 bundle verification, cache, evaluation, agent overrides (narrowing only) |
| `judge/` | `base.py` prompt + safety bias; `local.py` MLX Qwen3-4B (prefix cache, logit verdict, lazy load/unload); `remote.py` corporate via backend |
| `sync.py` | Enrollment, signed profile fetch + SSE push, audit upload, heartbeat, owner approvals |
| `audit.py` | Hash-chained append-only JSONL log with upload offsets |
| `honeytokens.py`, `undo.py`, `supply_chain.py`, `injection.py`, `notify.py`, `sandbox.py`, `patch.py` | Decoys, APFS-clone snapshots, package check, post-read injection scan, macOS notification/dialog, srt settings, apply_patch parser |
| `installers.py`, `cli.py` | Hook installers (with backups) and the `senti` command |

# Run

```bash
# organization side
docker compose up -d --build          # admin http://localhost:8080, device API http://localhost:8000

# a Mac
cd engine && uv sync --extra mlx       # Apple Silicon; drop --extra mlx for rules + corporate judge only
uv run senti start                     # or: uv run senti service install
uv run senti enroll --backend http://localhost:8000 --code SENTI-DEMO --email you@acme.test
uv run senti stop && uv run senti start
uv run senti install all               # or --project DIR for one repo
```

# Tests

```bash
cd engine && uv run pytest -q          # 112 tests: rules, review regressions, profiles, judge modes, adapters, undo, audit
cd backend && uv run pytest -q         # 17 API tests
cd admin && npx playwright test        # 7 browser tests against the running stack
SENTI_SOCKET=... uv run --project engine python scripts/e2e_modes.py   # 14 live checks
```

Isolated test instance: `SENTI_HOME=/tmp/senti-test SENTI_SOCKET=/tmp/senti-test.sock SENTI_NO_GUI=1` (no dialogs; ask → block for dialog agents).
