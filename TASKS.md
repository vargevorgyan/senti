# Senti — build task board

Living task summary for the full build (merged into `main` on 2026-09-27). Any agent picking this up:
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

Legend: [x] done · [~] partial · [ ] todo

### Engine (local, host) — `engine/`
- [x] Package skeleton, config (`~/.senti`), models, CLI (`senti …`)
- [x] Rules L1 + detectors L2 ported and extended (sudo, substitutions, hex/base64, history wipe, stop-Senti, Keychain, …)
- [x] Script inspection: inline `-c/-e`, `package.json` scripts (+install hooks), Makefile targets, local imports (py/js/sh), personal-folder deletion, reviewer-injection text, obfuscation
- [x] Profiles: schema, evaluation (files/network/shell/mcp/packages), per-agent overrides (narrowing only), per-user assignments
- [x] Signed profile cache (Ed25519), SSE push (~0.2 s), `strict_local` when backend unreachable, revocation handling
- [x] Judges: LocalJudge (MLX, lazy load, idle unload), RemoteJudge (corporate via backend), router `local | corporate | local_then_corporate | none`
- [x] Decision cache (keyed by profile version), task tracking, write-time script pre-check, reasons for ask/block
- [x] Audit log (hash-chained JSONL) + batched idempotent upload + heartbeat
- [x] Adapters: Claude Code, Codex CLI (incl. `apply_patch`, delete+add = overwrite), OpenCode, generic `/v1/check`
- [x] FastAPI server over Unix socket (0600), refuses to steal a live socket
- [x] Swift hook client (HTTP/UDS, fail closed per agent; Codex explicit deny) + Python fallback client
- [x] Installers (Claude Code settings, Codex hooks.json, OpenCode plugin) with backups; LaunchAgent (`senti service install`)
- [x] Sandbox: per-agent srt settings from the profile, `senti sandbox`, `senti run`, `senti shell-init` wrappers, `senti install claude --sandbox` (Claude Code built-in sandbox) — verified live
- [x] Undo / time machine (APFS clones), Honeytokens, Supply-chain check, Post-read injection scanning (+ tainted sessions), Task scope contract (opt-in)
- [x] Self-protection (Senti home, agent hook configs, launchctl/pkill Senti)
- [x] "Ask" handling: Claude native prompt; macOS dialog for Codex/OpenCode (Always allow → allowlist); owner/admin approvals via backend

### More agents (2026-09-27)
- [x] Agent registry (`agents.py`); adapters + installers + fail-closed hook replies for Cursor, Cline, Hermes Agent, OpenClaw (ZCode and Antigravity dropped by the owner) (`tests/test_more_agents.py`)
- [ ] Live tests with the real agents (none of the four is installed on the dev Mac)
- [ ] Enforce peer verification for these agents once their process names are confirmed live

### Evidence: real incidents (2026-09-27)
- [x] 19 sourced incidents → `research/incidents/incidents.json`; `scripts/incident_replay.py`; `engine/tests/test_incidents.py` (38/38 by rules)
- [x] ~15 rules added from the misses; KB: `.okf/research/agent-incidents.md` (presentation-ready)
- [ ] Refresh the incident list quarterly; add live re-enactments (safe copies) for the four headline stories

### Org backend (Docker) — `backend/`
- [x] FastAPI + SQLite models: admins, roles, users, profiles, devices, enrollment codes, events, approvals, KV, change log
- [x] Admin auth (JWT, random secret per install), seed admin + Developer / PM / Autonomous agent profiles + demo code
- [x] Device API: enroll, signed profiles, SSE stream, heartbeat, events, judge gateway, approvals
- [x] Corporate judge gateway (OpenAI-compatible, JSON mode, logprobs → p(verdict), safety bias)
- [x] Admin API: overview, profiles CRUD/duplicate, roles, users (+effective profiles), devices/revoke, codes, events (+CSV), approvals, corporate model settings/status/playground, change log, SSE
- [x] Tests (13)

### Admin panel (React, Docker) — `admin/`
- [x] Design tokens/type/components from the designer's system (`docs/design/`), light/dark, responsive
- [x] Login, Overview, Activity (live), Approvals, Profiles + editor (judge modes, rules, overrides, protections), People and roles, Devices + enrollment, Corporate judge + playground, Change log
- [x] Playwright e2e (7 tests incl. mobile overflow)
- [ ] Real logo SVGs (designer's artifact blobs are not downloadable; placeholder icon used)

### Security review (2026-09-27)
- [x] 20 findings from an adversarial review; all high and most medium fixed with regression tests — see `.okf/research/security-review-2026-09-27.md`
- [x] JWT revocation + SSE tickets, TLS by default with certificate pinning, peer-process verification (done 2026-09-27)
- [x] Second review (/code-review max): 15 main + ~20 minor findings fixed — `engine/tests/test_review2.py`
- [x] Review leftovers: git exec keys/globals, Grep content over secrets, demo code off by default, signed judge/approval answers, allowlist cwd
- [ ] Open: `github.com` WebFetch trust; hook.token readable by uninspected same-user code; judge over-blocking some asks; `cat .env` decided by the judge (by design)

### Infra / QA / docs
- [x] docker-compose (backend, admin, ollama + model pull, healthchecks), `.env.example`
- [x] `scripts/e2e_modes.py` — 14/14 live checks (all judge modes, push, overrides, approvals, audit upload)
- [x] `scripts/simulate.py` — 73 labelled actions: 22/22 dangerous stopped, 97% exact
- [x] Real agents: Claude Code, Codex CLI, OpenCode (cloud model and local Ollama) — see `.okf/research/real-agent-tests.md`
- [x] Demo: `demo/make-demo-repo.sh` (poisoned repo, fake secrets)
- [x] README quickstart, `.okf` updates (ADR-010, code guide, admin panel, real-agent tests, rewritten concepts, log)

## Remaining / next steps (pick up here)

1. ~~Enforce `features.sandbox`~~ — done (ask before commands when not sandboxed).
2. ~~Secret brokering, local model gateway~~ — done (`senti secret`, gateway on 127.0.0.1:11435).
3. ~~Peer verification~~ — done (socket token + LOCAL_PEERPID parent chain).
4. **Over-cautious judge cases** (`seed_db.py`, `check_links.py`): still open. Tried 2026-09-27: broad "allow" guidance + few-shot examples regressed the simulation (typosquat package silently allowed) and `sends_data`/`hosts` facts had no effect — both reverted, see `.okf/research/detector-hardening-2026-09-27.md`.
5. **Codex hook trust** for managed rollouts (`requirements.toml` managed hooks).
6. ~~Push the full build~~ — done: pushed directly to `main` on 2026-09-27.
7. Postgres option for the backend and multi-admin roles (only one admin role today).
8. Designer's real logo SVGs into `admin/public/`.
9. **Quadratic `curl … | sh` hard-deny regexes** on adversarial one-line input (~120 ms at the 20 KB cap) — rewrite with a bounded pattern.

## How to verify quickly

```bash
docker compose up -d --build
cd engine && uv sync --extra mlx && uv run pytest -q && cd ../backend && uv run pytest -q
cd ../engine && SENTI_HOME=/tmp/senti-test SENTI_SOCKET=/tmp/senti-test.sock uv run senti start
# fingerprint: Devices page, or: docker compose logs admin | grep Fingerprint
SENTI_HOME=/tmp/senti-test SENTI_SOCKET=/tmp/senti-test.sock uv run senti enroll --backend https://localhost:8443 --fingerprint <sha256> --code SENTI-DEMO --email dev@acme.test
# restart the engine, then:
cd .. && SENTI_SOCKET=/tmp/senti-test.sock uv run --project engine python scripts/e2e_modes.py
cd admin && npx playwright test
```

## Log
- 2026-09-27: Board created. Branch `feat/full-build`. Design system copied to `docs/design/`.
- 2026-09-27: Engine, backend, admin panel, Docker stack built; all judge modes verified end to end (14/14); real Claude Code, Codex, OpenCode sessions pass through Senti; simulation 22/22 dangerous stopped; docs and `.okf` updated.
- 2026-09-27: Security review fixes (runner/awk/git/symlink/glob/curl bypasses, socket token, override narrowing, bundle binding, backend spoofing, default-password warning). Claude Code built-in sandbox via `install --sandbox`; `network.ask` rules.
- 2026-09-27: Remaining items done — JWT revocation/SSE tickets, TLS + pinning, peer-process verification, required sandbox, secret brokering, model gateway; second review (15+ findings) fixed. Engine 161 tests, backend 22, Playwright 7, e2e 14/14.
- 2026-09-27: Review leftovers fixed (see security review, third pass). Engine 175 tests, backend 24, Playwright 7, e2e 14/14.
- 2026-09-27: Six more agents (Cursor, Cline, Antigravity, ZCode, Hermes, OpenClaw): adapters, installers, docs; unit-tested, not live-tested. Engine 196 tests.
- 2026-09-27: ZCode and Antigravity support removed at the owner's request.
- 2026-09-27: Incident research: 19 real agent incidents replayed, 38/38 harmful actions caught by rules; new rules added; simulation unchanged (22/22, 2/39 safe asked).
- 2026-09-27: Script detector hardening (env-exfil, backdoor key, download-and-run, personal-folder upload, persistence) after code + security review; held-out attacks hard-blocked 3/8 → 8/8, routine scripts 12/12, simulation unchanged; `senti stop` race + stale-pid fixes; replay scripts fail loudly when the engine is down. Engine 218 tests.
- 2026-09-27: Personal invite keys (People page → one-time `sti_` key, hashed, 48 h, `senti enroll --key`); shared codes off by default; `/judge` restricted to the device's own profiles; per-device rate limits on `/judge` and `/approvals`; clean `senti enroll` errors. Backend 38 tests, engine 261.
- 2026-09-27: Server gateway (MCP) in the backend: plain-English policy → role rules (reviewed examples + warnings) → approve; agent tokens; hard rules + SQLite authorizer + supervisor LLM; admin page; demo data + scripted MCP agent; tested with a real MCP client and a real Claude Code session. Backend 101 tests (incl. security review fixes: absolute paths in commands, runaway SQL, off-loop execution).
- 2026-09-27: `./senti-server` installer/manager (tested install/update/backup/reset on Docker Desktop); `senti setup` one step for employees; `senti connect` + `senti mcp` bridge (assistants reject the self-signed certificate — tested); per-person server role on People page. Engine 271 tests, backend 106. Next: serve a packaged Mac installer from the company's Senti server so the invite is one link.
- 2026-09-27: Company AI filter (ADR-012): company Macs load no model, all unclear actions go to the company's cloud AI; company profiles default to it; scripts sent with secrets redacted; pre-checks via the company AI. Live: Mac 97 MB, 22/22 dangerous stopped, 88% decided on the Mac. Typosquat check fixed (0/226 false alarms). Open: measure the reworded Developer note (re-run timed out on the stand-in model). Engine 278 tests, backend 106.
