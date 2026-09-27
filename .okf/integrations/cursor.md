---
type: Integration
title: Cursor integration
description: Cursor (IDE and cursor-agent) protected through hooks.json permission hooks with failClosed; implemented and unit-tested, not yet run against a real Cursor.
tags: [integrations, cursor]
status: draft
generated: { by: claude-code/2.1.283, at: '2026-09-27T11:00:00Z' }
sources:
  - id: primary
    resource: https://cursor.com/docs/hooks
    title: Primary sources used for the adapter (docs, source code, binaries)
  - id: code
    resource: /engine/src/senti/adapters.py, /engine/src/senti/installers.py, /engine/tests/test_more_agents.py
    title: Adapter, installer and tests
---
# Mechanism

`senti install cursor [--project DIR]` merges into `~/.cursor/hooks.json` (or `<project>/.cursor/hooks.json`), `version: 1`:
`beforeShellExecution`, `beforeMCPExecution`, `beforeReadFile`, `preToolUse` (pre, `failClosed: true`), `beforeSubmitPrompt`
(task), `postToolUse` / `afterShellExecution` / `afterFileEdit` (injection warnings via `additional_context`).

- Reply: `{"permission": "allow|deny|ask", "user_message", "agent_message"}`; exit 2 = deny.
- **ask** works natively only for shell and MCP hooks; for `beforeReadFile` and `preToolUse` Senti shows its macOS dialog.
- `preToolUse` skips Shell, Read and MCP (checked by their dedicated hooks) and covers writes, edits, deletes, tasks.
- Crashes/timeouts deny thanks to `failClosed`; the hook binary also prints a deny and exits 2.
- Caveat (community report): `cursor-agent` CLI may only send shell events.

# Status

Adapter, installer, uninstaller and fail-closed hook replies are implemented and covered by `engine/tests/test_more_agents.py`.
Not yet exercised with the real agent (it isn't installed on the dev Mac). Peer-process verification is recorded but not enforced for this agent until it is tested live.
