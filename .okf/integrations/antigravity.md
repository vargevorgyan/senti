---
type: Integration
title: Google Antigravity integration
description: Antigravity (IDE and agy CLI) protected by its hooks.json PreToolUse hook; implemented and unit-tested, not yet run against a real session.
tags: [integrations, antigravity]
status: draft
generated: { by: claude-code/2.1.283, at: '2026-09-27T11:00:00Z' }
sources:
  - id: primary
    resource: antigravity.google/docs/hooks; hooks guide embedded in the local agy 1.2.2 binary
    title: Primary sources used for the adapter (docs, source code, binaries)
  - id: code
    resource: /engine/src/senti/adapters.py, /engine/src/senti/installers.py, /engine/tests/test_more_agents.py
    title: Adapter, installer and tests
---
# Mechanism

Antigravity is not Gemini CLI; it has its own hooks (`~/.gemini/config/hooks.json`, shared by the IDE and `agy`, or
`<project>/.agents/hooks.json` after the folder is trusted). `senti install antigravity [--project DIR]` adds one named hook
`senti` with `PreToolUse` and `PostToolUse` (`matcher: "*"`).

- Payload: `toolCall {name, args}` with CamelCase args — `run_command {CommandLine, Cwd}`, `write_to_file {TargetFile, CodeContent}`,
  `replace_file_content`, `view_file {AbsolutePath}`, `read_url_content {Url}`, `grep_search`, `list_dir`, browser and MCP steps.
- Reply: `{"decision": "allow|deny|ask", "reason"}` (native ask).
- There is no prompt-submit event (PreInvocation carries no text), so Senti has no task context for Antigravity yet.
- Failure behaviour is undocumented; the hook binary always prints an explicit deny when Senti is unreachable.

# Status

Adapter, installer, uninstaller and fail-closed hook replies are implemented and covered by `engine/tests/test_more_agents.py`.
Not yet exercised with the real agent (it isn't installed on the dev Mac, except Antigravity, whose live test would use the
person's Google account). Peer-process verification is recorded but not enforced for this agent until it is tested live.
