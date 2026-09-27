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
Claude Code · Codex · OpenCode · Cursor · Cline · Hermes · OpenClaw
        │ hooks / plugin (fail closed)                         │ MCP "company-server"
        ▼                                                      ▼
Thin Senti agent (per Mac, ~100 MB, no AI model)          local bridge (senti mcp)
  honeytokens → rules → profile → detectors → cache ──┐            │
  undo snapshots · hash-chained audit · sandbox        │ unclear    │
                                                       ▼ actions    ▼
                          ┌── Company cloud (./senti-server, Docker) ─────────────────────────┐
                          │ backend (FastAPI + SQLite) · admin panel (React) :8443             │
                          │ company AI filter (Ollama or any OpenAI-compatible API)            │
                          │ MCP server gateway → shared files · SQLite · commands, plain-English│
                          │   role rules + supervisor                                          │
                          └────────────────────────────────────────────────────────────────────┘
```

There is **no client UI app**: "ask" uses the agent's own prompt (Claude Code) or a macOS dialog (Codex, OpenCode), or goes to
the owner in the admin panel. The org side is in Docker; everything local (hooks, engine, MLX judge) runs natively.

## Quick start

### 1. Organization side

```bash
./senti-server                  # guided install: a few questions, sensible defaults (needs Docker; installs it on Linux)
```

It prints the admin panel address, a one-time admin password and the next steps. Manage it with
`./senti-server status | logs | update | backup | restore | reset-password | uninstall`.

- Admin panel and device API: <https://localhost:8443> (self-signed certificate) — `admin@senti.local` / `senti-admin`; the panel
  warns until you change the password. Ports bind to 127.0.0.1 unless `SENTI_BIND=0.0.0.0`.
- Add each person on the **People and roles** page ("Add person and invite"). The panel shows their enroll command once, with a
  personal invite key (`sti_…`) and the certificate fingerprint: send it to them privately. The key works once, on one Mac, and
  expires after 48 hours; a new invite replaces an unused one. Shared multi-use codes are off (`SENTI_ALLOW_SHARED_CODES`).
  (For demos you can set `SENTI_DEMO_ENROLL_CODE=SENTI-DEMO` in `.env`: 20 uses, 7 days.)

### 2. Each Mac (Apple Silicon)

Requires [uv](https://docs.astral.sh/uv/), Xcode command line tools (for the Swift hook) and Python 3.12 (uv installs it).

```bash
cd engine
uv sync                                # company Macs need no model: unclear actions go to the company's AI filter
                                       # (personal use without a company: uv sync --extra mlx for the local Qwen3-4B judge)
uv run senti start                     # first start downloads Qwen3-4B (~2.3 GB) in the background
uv run senti setup --backend https://localhost:8443 --fingerprint <sha256> --key sti_…   # the command your admin sent you:
                                        # joins, starts Senti, protects your assistants, connects them to the company server
uv run senti stop && uv run senti start
uv run senti install all               # Claude Code, Codex, OpenCode (user-wide); or --project DIR
uv run senti status
```

Personal mode (no organization) works too: skip `enroll`; the built-in profile and the local judge are used.
Run at login: `uv run senti service install` (LaunchAgent).

## Judge modes (per profile, set in the admin panel)

The company runs **one AI filter** in its own cloud (the corporate model); employees' Macs run **no model**. Each Mac runs a
thin Senti agent (~100 MB) that decides obvious actions itself in milliseconds and sends only unclear ones to the company AI
(scripts with secrets redacted).

| Mode | Unclear actions go to |
|---|---|
| **Company AI** (default) | the company's AI filter via the backend |
| On each Mac | a local Qwen3-4B (personal use; company Macs use the company AI instead) |
| Mac first, then company | only if the Mac has a model; otherwise the company AI |
| No AI judge | always ask |

Hard rules and profile denies are enforced on the Mac and can never be overruled by any judge; if the company AI can't be
reached, Senti asks or blocks, never allows.

## CLI

```
senti setup --backend URL --fingerprint FP --key sti_…   one step for employees (join, start, protect, connect, start at login)
senti connect [assistant] [--remove]                      add/remove the company server in Claude Code, Claude Desktop, Cursor, Codex, OpenCode
senti mcp                          local MCP bridge to the company's server gateway (used by the assistants)
senti start|stop|status            run the engine
senti install|uninstall <agent>    claude codex opencode cursor cline hermes openclaw | all  [--project DIR]
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

## Server gateway: agents on your server, rules in plain English

AI agents can use a company server's files, commands and database **only through Senti** (MCP at `/api/v1/mcp/`).
In the admin panel's **Server gateway** page, describe access in plain English ("Support agents can read tickets and customer
names, never card numbers or payments…"), click **Generate rules**, review the rules and example actions, and approve. Then
give people **server access** on the People page: `senti setup` / `senti connect` adds a `company-server` entry to their
Claude Code, Claude Desktop, Cursor, Codex and OpenCode (through a local bridge, so no certificates or tokens to handle).
Bots without a person get an agent token and a ready command on the Server gateway page.
Every call is checked by hard rules and the compiled role rules; anything they don't cover goes to the supervisor model
(no human in the loop, only a clear "allow" passes). Try it with fake data:

```bash
python3 demo/make-server-data.py server-data     # shared as the "server" by docker compose (SENTI_GATEWAY_DIR)
uv run --project backend python scripts/gateway_agent.py https://localhost:8443/api/v1/mcp/ sag_…   # scripted agent
```

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

## Documentation

The knowledge base is in [`.okf/`](.okf/index.md). Guides: [customer onboarding](.okf/guides/customer-onboarding.md),
[server installer](.okf/guides/server-installer.md), [connecting assistants](.okf/guides/connecting-assistants.md),
[writing a server policy](.okf/guides/writing-server-policy.md); architecture: [system overview](.okf/architecture/system-overview.md),
[server gateway](.okf/architecture/server-gateway.md), [access and credentials](.okf/architecture/access-and-credentials.md).

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

Full build merged into `main` (2026-09-27). See [TASKS.md](TASKS.md) for remaining work.
