---
type: Integration
title: Codex CLI integration (ChatGPT agent)
description: Codex CLI (the locally running ChatGPT agent) protected through its PreToolUse/UserPromptSubmit/PostToolUse hooks; verified live.
tags: [integrations, codex, openai, chatgpt]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-27T02:00:00Z' }
sources:
  - id: hol-codex
    resource: https://github.com/hashgraph-online/hol-guard/tree/main/src/codex_plugin_scanner/guard/adapters
    title: HOL Guard Codex adapter (codex.py, codex_daemon_hook_bridge.py)
    last_modified: 2026-09-26
  - id: live
    resource: /.okf/research/real-agent-tests.md
    title: Live agent runs through the full-build engine (2026-09-27)
    author: claude-code/2.1.283
---

# Mechanism (verified with Codex CLI 0.157.1)

- Hooks: `~/.codex/hooks.json` or `<repo>/.codex/hooks.json` (Claude-style JSON; `senti install codex [--project DIR]`), feature `hooks` is stable/on.
- Events used: `PreToolUse`, `UserPromptSubmit`, `PostToolUse`. Shell arrives as `tool_name: "Bash"` with `tool_input.command`; edits as `apply_patch` with the raw patch text in `tool_input.command` (Senti parses Add/Update/Delete/Move into Write/Edit/rm checks; delete+add of one file = overwrite).
- Replies: **allow = empty stdout** (`permissionDecision: allow` without `updatedInput` is rejected); deny = `permissionDecision: "deny"` + reason. **No `ask`** → Senti shows its macOS dialog and answers allow/deny.
- Codex **fails open** on hook errors/timeouts, so `senti-hook codex pre` always prints an explicit deny when Senti is unreachable.
- New hooks must be **trusted** once (`/hooks` in the TUI); `codex exec --dangerously-bypass-hook-trust` for automated tests.

# Status

Tested live (see [Real-agent tests](/research/real-agent-tests.md)): shell, patches, prompt and post-tool hooks all reach Senti;
injection warning delivered; rewritten script allowed instantly via the write-time pre-check.
