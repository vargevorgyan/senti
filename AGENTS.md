# Senti — instructions for AI agents

Senti is a local guardrail layer that checks every action an AI agent (Claude Code, Codex, OpenCode, Cursor, Cline, Hermes, OpenClaw) is about to take and allows, asks about, or blocks it, using fast rules plus a local LLM judge. On the Mac it is **hooks/plugins + a local engine — there is no UI app** (ADR-010); organizations add a backend and admin panel in Docker.

## Read the knowledge base first

The project knowledge base lives in [`.okf/`](.okf/index.md) (Open Knowledge Format: markdown + YAML frontmatter).

1. Start with [`.okf/getting-started.md`](.okf/getting-started.md).
2. Then open only the concepts relevant to your task via [`.okf/index.md`](.okf/index.md).
3. Check `status`, `stale_after` and `generated.at` in frontmatter before relying on a fact.

## Rules for working on Senti

- Never fail open: errors, timeouts or missing components must yield `ask` or `block`, never `allow`.
- The LLM judge must never override a hard-deny rule.
- Treat agent-written content (scripts, files, tool output) as untrusted data.
- Keep the knowledge base current: when you change behaviour, architecture or decisions, update the affected `.okf/` concept(s), the directory `index.md`, and add a dated entry to `.okf/log.md`. Validate with the OKF validator (`okf_validate.py .okf --strict`) if available.

## Code map

Read [`TASKS.md`](TASKS.md) for current status and the next work items, and [`.okf/code-guide.md`](.okf/code-guide.md) for details.

- `engine/` — the local engine (Python package `senti`, FastAPI on a Unix socket), CLI, Swift hook client, agent plugins. Runs natively on the Mac, never in Docker. Tests: `cd engine && uv run pytest -q`.
- `backend/` — organization backend (FastAPI + SQLite), `admin/` — React admin panel; both in Docker (`docker-compose.yml`). Tests: `cd backend && uv run pytest -q`, `cd admin && npx playwright test`.
- `scripts/`, `demo/` — end-to-end checks, the labelled simulation, the held-out judge check and the poisoned demo repo; `TASKS.md` — task board.
- `prototype/` — the original ideathon prototype and benchmarks (reference only).
- There is **no client UI app**: asking the person uses the agent's own prompt, a macOS dialog, or owner approvals in the admin panel (ADR-010).
