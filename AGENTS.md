# Senti — instructions for AI agents

Senti is a local guardrail layer that checks every action an AI agent (Claude Code, Codex, OpenCode, ...) is about to take and allows, asks about, or blocks it, using fast rules plus a local LLM judge.

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

- `prototype/engine/` — working Python engine + Swift hook (see [`.okf/prototype.md`](.okf/prototype.md)).
- `prototype/bench/`, `prototype/results/` — benchmarks and raw results.
- The SwiftUI app and org backend are not started yet.
