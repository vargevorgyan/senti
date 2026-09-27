---
type: Integration
title: OpenClaw integration
description: OpenClaw protected by a native TypeScript plugin on before_tool_call; ask uses OpenClaw's requireApproval. Implemented and unit-tested, not yet run against a real OpenClaw.
tags: [integrations, openclaw]
status: draft
generated: { by: claude-code/2.1.283, at: '2026-09-27T11:00:00Z' }
sources:
  - id: primary
    resource: openclaw/openclaw docs/plugins/hooks.md, docs/plugins/hooks/tool-policy.md, src/plugin-sdk/plugin-entry.ts
    title: Primary sources used for the adapter (docs, source code, binaries)
  - id: code
    resource: /engine/src/senti/adapters.py, /engine/src/senti/installers.py, /engine/tests/test_more_agents.py
    title: Adapter, installer and tests
---
# Mechanism

OpenClaw has no shell hook for tool calls; the only gate is the typed plugin hook `before_tool_call`. `senti install openclaw`
writes a plugin to `~/.openclaw/plugins/senti` (`index.ts`, `package.json` with `openclaw.extensions`, `openclaw.plugin.json`
with `activation.onStartup`) and runs `openclaw plugins install --link … --force` + `openclaw plugins enable senti` when the CLI is
present (otherwise it prints those commands). The plugin spawns `senti-hook openclaw pre` per call.

- Tools: `exec`/`bash`, `read`, `write`, `edit` (`edits[{oldText,newText}]`), `apply_patch {input}`, `web_fetch`, `browser`, others as tools.
- Returns: block `{block: true, blockReason}`; **ask** `{requireApproval: {title, description, severity, timeoutMs}}`; allow `undefined`;
  secrets rewrite `{params}`. `after_tool_call` is observed for injection context.
- Fails closed: OpenClaw blocks when the handler throws or times out; the plugin also blocks if Senti can't be reached.
- The plugin exports a plain entry object (same shape as `definePluginEntry`), so it doesn't depend on the OpenClaw SDK package.

# Status

Adapter, installer, uninstaller and fail-closed hook replies are implemented and covered by `engine/tests/test_more_agents.py`.
Not yet exercised with the real agent (it isn't installed on the dev Mac, except Antigravity, whose live test would use the
person's Google account). Peer-process verification is recorded but not enforced for this agent until it is tested live.
