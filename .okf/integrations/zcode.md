---
type: Integration
title: ZCode integration
description: ZCode (Z.ai) protected through its Claude-Code-compatible hooks in ~/.zcode/cli/config.json; implemented and unit-tested, not yet run against a real ZCode.
tags: [integrations, zcode]
status: draft
generated: { by: claude-code/2.1.283, at: '2026-09-27T11:00:00Z' }
sources:
  - id: primary
    resource: https://zcode.z.ai/en/docs/hooks; zai-org/feedback#32
    title: Primary sources used for the adapter (docs, source code, binaries)
  - id: code
    resource: /engine/src/senti/adapters.py, /engine/src/senti/installers.py, /engine/tests/test_more_agents.py
    title: Adapter, installer and tests
---
# Mechanism

`senti install zcode` writes the nested layout `hooks.events.{PreToolUse, UserPromptSubmit, PostToolUse}` into
`~/.zcode/cli/config.json` (`command` + `args: ["zcode", "<event>"]`). Project-level hook files are ignored by ZCode.

- Payload and reply are Claude Code's (`hookSpecificOutput.permissionDecision allow|ask|deny`), so Senti reuses that adapter.
- **ZCode fails open** on hook errors; the hook binary prints an explicit deny and exits 2.
- Known issue: hooks reportedly don't fire for ZCode's native agent, only for external CLI sub-agents (zai-org/feedback#32).

# Status

Adapter, installer, uninstaller and fail-closed hook replies are implemented and covered by `engine/tests/test_more_agents.py`.
Not yet exercised with the real agent (it isn't installed on the dev Mac, except Antigravity, whose live test would use the
person's Google account). Peer-process verification is recorded but not enforced for this agent until it is tested live.
