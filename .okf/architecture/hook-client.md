---
type: Component
title: senti-hook (hook client)
description: Tiny compiled Swift binary that agents run before each action; forwards the hook JSON to the engine over a Unix socket and fails closed.
tags: [architecture, hook, swift, component]
status: stable
resource: /prototype/engine/senti-hook.swift
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
sources:
  - id: sim
    resource: /prototype/results/res_rules_swift.json
    title: Rules-only simulation with the Swift hook (71 actions)
  - id: sim-py
    resource: /prototype/results/res_rules_py.json
    title: Same simulation with a Python hook client
---

# Overview

Agents (Claude Code, Codex, OpenCode plugin) launch this program **once per action**, passing the action
as JSON on stdin. It connects to the engine's Unix socket, sends the JSON, prints the engine's reply
(Claude Code / Codex hook response format) and exits.

# Why these choices

| Choice | Reason | Evidence |
|---|---|---|
| Compiled Swift, POSIX only (no Foundation) | Agents spawn it hundreds of times per session | 3 ms end-to-end vs 19 ms for a Python client[^sim][^sim-py] |
| Unix domain socket, mode `0600` | Only the user's own processes can connect; browsers/DNS-rebinding cannot reach it (unlike `localhost:7777`) | design decision |
| Fail closed | If the engine is down, slow (30 s timeout) or returns nothing → `ask` | Observed in testing: engine not ready → hook answered `ask` |

# Protocol

- Input: the agent's hook JSON (e.g. Claude Code `PreToolUse`: `session_id`, `cwd`, `tool_name`, `tool_input`; `UserPromptSubmit`: `prompt`).
- Output (PreToolUse): `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow|ask|deny","permissionDecisionReason":"Senti: ..."}}`.
- Socket path in the prototype: `/tmp/senti-proto.sock` (Unix socket paths are limited to 104 chars on macOS).

# Build

```bash
swiftc -O prototype/engine/senti-hook.swift -o prototype/engine/senti-hook
```

# Future hardening

Per-agent identity token (from Keychain) and peer-process verification (`LOCAL_PEERPID` / audit token) so the
engine knows which agent is calling and a same-user process cannot impersonate one.

[^sim]: Rules-only simulation with the Swift hook (71 actions)
[^sim-py]: Same simulation with a Python hook client
