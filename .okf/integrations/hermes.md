---
type: Integration
title: Hermes Agent integration
description: Hermes Agent (Nous Research) protected by pre_tool_call shell hooks with fail_closed; ask uses Hermes' own approval gate. Implemented and unit-tested, not yet run against a real Hermes.
tags: [integrations, hermes]
status: draft
generated: { by: claude-code/2.1.283, at: '2026-09-27T11:00:00Z' }
sources:
  - id: primary
    resource: NousResearch/hermes-agent website/docs/user-guide/features/hooks.md, agent/shell_hooks.py
    title: Primary sources used for the adapter (docs, source code, binaries)
  - id: code
    resource: /engine/src/senti/adapters.py, /engine/src/senti/installers.py, /engine/tests/test_more_agents.py
    title: Adapter, installer and tests
---
# Mechanism

`senti install hermes` adds `hooks.pre_tool_call` (`matcher: ".*"`, `fail_closed: true`) and `post_tool_call` to
`~/.hermes/config.yaml` (or `$HERMES_HOME`), and records consent for exactly these commands in
`~/.hermes/shell-hooks-allowlist.json` (Hermes would otherwise ask once, and skip unapproved hooks in cron/gateway runs).

- Payload: `{hook_event_name, tool_name, tool_input, session_id, cwd}`. Tools: `terminal`, `execute_code` (checked as inline Python),
  `read_file`, `write_file`, `patch`, `search_files`, `web_extract` (each URL), `browser_navigate`, others as tools.
- Reply: block `{"decision": "block", "reason"}`; **ask** `{"action": "approve", "message", "rule_key"}` → Hermes' human approval
  (denial/timeout = block); allow `{}`; secrets rewrite via `{"action": "modify"}`.
- Gap in Hermes itself: if its dispatcher raises, the tool runs (only logged). Hermes has no prompt hook that carries the task.

# Status

Adapter, installer, uninstaller and fail-closed hook replies are implemented and covered by `engine/tests/test_more_agents.py`.
Not yet exercised with the real agent (it isn't installed on the dev Mac, except Antigravity, whose live test would use the
person's Google account). Peer-process verification is recorded but not enforced for this agent until it is tested live.
