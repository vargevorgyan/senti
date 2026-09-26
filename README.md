# Senti

**A local guardrail between you and the AI agents on your Mac.**

People increasingly give AI agents broad — often unintentional — access to their systems: files, shell commands, network calls, credentials. Senti checks every action an agent tries to take *before* it runs:

- **Blocks** clearly dangerous actions (e.g. uploading a file full of passwords to an unknown site, deleting an entire folder)
- **Asks you** about suspicious ones — in plain language, not JSON
- **Allows** the safe ones silently

All analysis runs on a **local LLM** (via Ollama), so none of your monitored activity ever leaves your machine.

## Architecture (MVP)

```
Claude Code · Codex · OpenCode ──► senti-hook (Swift) ──Unix socket──► Senti engine
                                                                  ├─ cache → rules → detectors
                                                                  ├─ LLM judge: local Qwen3-4B (MLX) or corporate model
                                                                  └─ allow / ask (popup) / block
Commands run inside a per-agent OS sandbox (sandbox-runtime) as the backstop.
```

## Stack

- Swift 6 / SwiftUI (macOS 14+)
- Local judge: Qwen3-4B-Instruct (4-bit) via MLX
- Agent hooks/plugins (Claude Code, Codex CLI, OpenCode) + OS sandbox (anthropics/sandbox-runtime)

## Knowledge base

Full project knowledge (business idea, architecture, decisions, benchmarks, roadmap) is in [`.okf/`](.okf/index.md) — start with [`.okf/getting-started.md`](.okf/getting-started.md).

## Status

🚧 Built at an ideathon — work in progress.
