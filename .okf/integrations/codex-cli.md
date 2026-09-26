---
type: Integration
title: Codex CLI integration (ChatGPT agent)
description: Plan for hooking OpenAI's Codex CLI, the locally running ChatGPT coding agent, using its PreToolUse hooks.
tags: [integrations, codex, openai, chatgpt]
status: draft
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
sources:
  - id: hol-codex
    resource: https://github.com/hashgraph-online/hol-guard/tree/main/src/codex_plugin_scanner/guard/adapters
    title: HOL Guard Codex adapter (codex.py, codex_daemon_hook_bridge.py)
    last_modified: 2026-09-26
---

# Mechanism (from HOL Guard's Codex adapter; not yet verified by us)[^hol-codex]

- Hooks live in `~/.codex/config.toml` (or project `.codex/config.toml`) under a hooks table; enabled unless `features.hooks = false`.
- Events: `PreToolUse`, `PermissionRequest`, `PostToolUse`, prompt hook. Matcher example: `Bash|Read|Write|Edit|MultiEdit|^apply_patch$|mcp__.*`.
- Response format mirrors Claude Code: `hookSpecificOutput.permissionDecision: deny` + `permissionDecisionReason`.
- Codex edits files with **`apply_patch`** → adapter must map it to Senti's Edit/Write checks (parse the patch for paths and new content).

# Status

Codex CLI is **not installed** on the dev Mac (`npm i -g @openai/codex`, latest seen 0.157.1). `~/.codex/` exists
with a login, so it should use the user's ChatGPT account. Installing and running a test session needs the user's
permission (uses their ChatGPT plan).
