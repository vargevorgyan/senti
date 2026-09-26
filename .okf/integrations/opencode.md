---
type: Integration
title: OpenCode integration (local models)
description: OpenCode (open-source agent for local models) protected by a Senti plugin using tool.execute.before/after and chat.message; verified live with a local Ollama model.
tags: [integrations, opencode, local-models]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-27T02:00:00Z' }
sources:
  - id: hol-opencode
    resource: https://github.com/hashgraph-online/hol-guard/blob/main/src/codex_plugin_scanner/guard/adapters/opencode_pretool.py
    title: HOL Guard OpenCode pretool plugin template
    last_modified: 2026-09-26
  - id: opencode
    resource: https://github.com/anomalyco/opencode
    title: OpenCode repository (~210k stars)
  - id: live
    resource: /.okf/research/real-agent-tests.md
    title: Live agent runs through the full-build engine (2026-09-27)
    author: claude-code/2.1.283
---

# Why OpenCode

The team wants local-model support via **OpenCode** — a popular open-source agent that can use Ollama, LM Studio or any
OpenAI-compatible server.

# Mechanism (verified with OpenCode 1.18.32)

- Plugin file: `~/.config/opencode/plugins/senti.ts` or `<repo>/.opencode/plugins/senti.ts` (`senti install opencode [--project DIR]`); OpenCode globs `{plugin,plugins}/*.{ts,js}`.
- Hooks: `chat.message` (user's task), `tool.execute.before` (throw = block; the error text is shown to the model), `tool.execute.after` (append Senti's injection warning to the tool output).
- The plugin spawns `senti-hook opencode <event>` with `node:child_process` (**not** `Bun.spawn`, which is unavailable in 1.18) and logs its own errors to `~/.senti-opencode-plugin.log`. Unreachable Senti → block.
- Tool names mapped: bash, read, write, edit, apply_patch (`patchText`), webfetch, websearch, grep, glob, list, task, todowrite; MCP tools `<server>_<tool>`.
- No native ask for plugins (`permission.ask` is never triggered in 1.18) → Senti's macOS dialog.

# Local model

Tested with `ollama/qwen2.5:3b` from the Docker Ollama (project `opencode.json` provider `@ai-sdk/openai-compatible`,
`baseURL http://localhost:11434/v1`). A 3B CPU model is slow (~20–60 s per step with OpenCode's large prompt) but works;
16 GB Macs can run Senti's MLX judge and this model together.

# Status

Tested live with a cloud free model and the local Ollama model: `pytest` allowed, disguised `helper.py` blocked.
