---
type: Integration
title: Cline integration
description: Cline (VS Code extension and CLI) protected by executable hook files PreToolUse / UserPromptSubmit / PostToolUse; implemented and unit-tested, not yet run against a real Cline.
tags: [integrations, cline]
status: draft
generated: { by: claude-code/2.1.283, at: '2026-09-27T11:00:00Z' }
sources:
  - id: primary
    resource: https://github.com/cline/cline (apps/vscode/src/core/hooks, sdk/examples/hooks)
    title: Primary sources used for the adapter (docs, source code, binaries)
  - id: code
    resource: /engine/src/senti/adapters.py, /engine/src/senti/installers.py, /engine/tests/test_more_agents.py
    title: Adapter, installer and tests
---
# Mechanism

`senti install cline [--project DIR]` writes executable scripts `PreToolUse`, `UserPromptSubmit`, `PostToolUse` into
`~/Documents/Cline/Hooks/` (or `<project>/.clinerules/hooks/`), each `exec senti-hook cline <event>`. Existing hooks of the
person are never overwritten (Senti says which events stay unprotected).

- Both payload shapes are accepted: VS Code (`preToolUse.toolName`, JSON-stringified `parameters`) and CLI/SDK (`tool_call.name/input`).
- Tools: `run_commands`/`execute_command` (each command checked, strictest wins), `read_files`, `editor`, `write_to_file`,
  `replace_in_file`, `apply_patch`, `fetch_web_content`, `browser_action`, `use_mcp_tool`, `<server>__<tool>`.
- Reply: allow `{"cancel": false}`, deny `{"cancel": true, "errorMessage"}` (in VS Code this stops the task). No native ask → macOS dialog.
- **Cline fails open** on hook errors, so the hook binary always prints an explicit `cancel: true` when Senti is unreachable.

# Status

Adapter, installer, uninstaller and fail-closed hook replies are implemented and covered by `engine/tests/test_more_agents.py`.
Not yet exercised with the real agent (it isn't installed on the dev Mac). Peer-process verification is recorded but not enforced for this agent until it is tested live.
