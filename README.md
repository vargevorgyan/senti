# Senti

**A local guardrail between you and the AI agents on your Mac.**

People increasingly give AI agents broad — often unintentional — access to their systems: files, shell commands, network calls, credentials. Senti checks every action an agent tries to take *before* it runs:

- **Blocks** clearly dangerous actions (e.g. uploading a file full of passwords to an unknown site, deleting an entire folder)
- **Asks you** about suspicious ones — in plain language, not JSON
- **Allows** the safe ones silently

All analysis runs on a **local LLM** (via Ollama), so none of your monitored activity ever leaves your machine.

## Architecture (MVP)

```
Senti.app (SwiftUI, menu bar)
 ├─ Local server :7777  ◄── Claude Code PreToolUse hook / MCP proxy
 ├─ RuleEngine          instant hard blocks (rm -rf ~, secrets → unknown host, …)
 ├─ LLMJudge  ───────►  Ollama :11434 (local)
 ├─ Approval popup      "Allow / Block" with a plain-language explanation
 └─ Activity log
```

## Stack

- Swift 6 / SwiftUI (macOS 14+)
- [Ollama](https://ollama.com) for the local model
- Claude Code hooks + MCP proxy for interception

## Status

🚧 Built at an ideathon — work in progress.
