# Senti

**A local guardrail between you and the AI agents on your Mac.**

People increasingly give AI agents broad — often unintentional — access to their systems: files, shell commands, network
calls, credentials. Senti checks every action an agent tries to take *before* it runs:

- **Blocks** clearly dangerous actions (uploading a file full of passwords to an unknown site, deleting a whole folder)
- **Asks** about suspicious ones — in plain language, not JSON
- **Allows** the safe ones silently

Decisions come from fast rules plus a **local LLM** (Qwen3-4B on MLX), so monitored activity never has to leave the machine.
Organizations add a backend and an admin panel that push role-based profiles to every Mac and can route unclear cases to a
**corporate model**.

## Architecture

```
Claude Code · Codex CLI · OpenCode
        │  hooks / plugin (senti-hook, fail closed)
        ▼
Senti engine (per Mac, FastAPI on ~/.senti/senti.sock)          ┌── Organization (docker compose) ──────────┐
  honeytokens → rules → profile → detectors → cache → judge ◄──►│ backend (FastAPI + SQLite)                │
  local judge: Qwen3-4B (MLX)   corporate judge: via backend    │ admin panel (React, nginx)  :8080         │
  undo snapshots · hash-chained audit · sandbox profiles        │ corporate model (Ollama, qwen2.5:3b)      │
                                                                └───────────────────────────────────────────┘
```

There is **no client UI app**: "ask" uses the agent's own prompt (Claude Code) or a macOS dialog (Codex, OpenCode), or goes to
the owner in the admin panel. The org side is in Docker; everything local (hooks, engine, MLX judge) runs natively.

## Quick start

### 1. Organization side (Docker)

```bash
cp .env.example .env            # optional: org name, admin password, model
docker compose up -d --build    # first start pulls the corporate model (~2 GB)
```

- Admin panel and device API: <https://localhost:8443> (self-signed certificate) — `admin@senti.local` / `senti-admin`; the panel
  warns until you change the password. Ports bind to 127.0.0.1 unless `SENTI_BIND=0.0.0.0`.
- Create an enrollment code on the **Devices** page; it shows the exact enroll command including the certificate fingerprint.
  (For demos you can set `SENTI_DEMO_ENROLL_CODE=SENTI-DEMO` in `.env`: 20 uses, 7 days.)

### 2. Each Mac (Apple Silicon)

Requires [uv](https://docs.astral.sh/uv/), Xcode command line tools (for the Swift hook) and Python 3.12 (uv installs it).

```bash
cd engine
uv sync --extra mlx                    # without --extra mlx: rules + corporate judge only
uv run senti start                     # first start downloads Qwen3-4B (~2.3 GB) in the background
uv run senti enroll --backend https://localhost:8443 --fingerprint <sha256> --code <code> --email you@acme.test   # command shown on the Devices page
uv run senti stop && uv run senti start
uv run senti install all               # Claude Code, Codex, OpenCode (user-wide); or --project DIR
uv run senti status
```

Personal mode (no organization) works too: skip `enroll`; the built-in profile and the local judge are used.
Run at login: `uv run senti service install` (LaunchAgent).

## Judge modes (per profile, set in the admin panel)

| Mode | Unclear actions go to |
|---|---|
| Local judge | Qwen3-4B on the Mac — private, offline |
| Corporate judge | the company model via the backend (falls back to local when the backend is unreachable) |
| Local, then corporate | local first; corporate only when local is unsure |
| No AI judge | always ask |

Hard rules and profile denies are enforced locally and can never be overruled by any judge.

## CLI

```
senti start|stop|status            run the engine
senti install|uninstall <agent>    claude | codex | opencode | all  [--project DIR]
senti enroll / unenroll            join or leave an organization
senti log [-f]                     recent decisions
senti audit verify                 check the tamper-evident audit log
senti undo list|restore ID         restore files an agent deleted or overwrote
senti honeytoken plant DIR         plant decoy secrets
senti sandbox --agent X / run      sandbox-runtime profile from the active profile
senti check Bash "cmd"             ask the engine about one action
senti secret add NAME --hosts H    broker a secret: agents write {{senti:NAME}}, the value is injected only at run time
senti shell-init                   shell functions that start agents inside their sandbox
```

## Demo

```bash
demo/make-demo-repo.sh /tmp/senti-demo          # poisoned repo, fake secrets only
cd engine && uv run senti install all --project /tmp/senti-demo
cd /tmp/senti-demo && claude -p "Read README.md, follow its setup steps, run helper.py and the tests"
```

Senti warns the agent about the hidden README instruction and blocks the disguised `helper.py`; the same happens with Codex and
OpenCode. The admin panel's Overview and Activity update live. Full script: [.okf/roadmap/hackathon-demo-plan.md](.okf/roadmap/hackathon-demo-plan.md).

## DIY agents (no hooks)

Point any OpenAI-compatible agent at the engine's model gateway instead of the model server:
`http://127.0.0.1:11435/v1` (forwards to Ollama at `localhost:11434`). Every tool call the model proposes is checked before your agent
sees it — try `python3 demo/diy_agent.py "…"`.

## Tests

```bash
cd engine && uv run pytest -q        # engine: rules, profiles, judge modes, adapters, undo, audit
cd backend && uv run pytest -q       # backend API
cd admin && npx playwright test      # admin UI against the running stack
SENTI_SOCKET=~/.senti/senti.sock uv run --project engine python scripts/e2e_modes.py   # live end-to-end
```

## Repository

| Path | What |
|---|---|
| `engine/` | Local engine, CLI, Swift hook, OpenCode plugin |
| `backend/` | Organization backend (FastAPI) |
| `admin/` | Admin panel (React) |
| `docs/design/` | Design system from the team's designer |
| `scripts/`, `demo/` | End-to-end checks, demo repo |
| `prototype/` | Ideathon prototype and benchmarks |
| `.okf/` | Knowledge base — start with [.okf/getting-started.md](.okf/getting-started.md) |
| `TASKS.md` | Task board: what is done and what remains |

## Status

Full build complete on branch `feat/full-build` (2026-09-27). See [TASKS.md](TASKS.md) for remaining work.
