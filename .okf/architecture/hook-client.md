---
type: Component
title: senti-hook (hook client)
description: Tiny compiled Swift binary that agents run before each action; forwards the hook JSON over HTTP on a Unix socket to the engine and fails closed per agent.
tags: [architecture, hook, swift, component]
status: stable
resource: /prototype/engine/senti-hook.swift
generated: { by: claude-code/2.1.283, at: '2026-09-27T02:00:00Z' }
sources:
  - id: sim
    resource: /prototype/results/res_rules_swift.json
    title: Rules-only simulation with the Swift hook (71 actions)
  - id: sim-py
    resource: /prototype/results/res_rules_py.json
    title: Same simulation with a Python hook client
  - id: build
    resource: /engine/src/senti, /backend/app, /admin/src (branch feat/full-build)
    title: Full-build source code
    author: claude-code/2.1.283
---

# Overview

Agents (Claude Code, Codex, the OpenCode plugin) launch this program **once per action**, passing the action as JSON on stdin:
`senti-hook <agent> <pre|prompt|post>`. It POSTs the JSON over HTTP/1.1 to the engine's Unix socket
(`/v1/hook/<agent>`), prints the engine's reply in the agent's format and exits. Source: `engine/hook/senti-hook.swift`;
`senti install` compiles it to `~/.senti/bin/senti-hook` (Python fallback `hook_client.py` if `swiftc` is missing).

# Why these choices

| Choice | Reason | Evidence |
|---|---|---|
| Compiled Swift, POSIX only (no Foundation) | Agents spawn it hundreds of times per session | 3 ms end-to-end vs 19 ms for a Python client[^sim][^sim-py] |
| Unix domain socket, mode `0600`, HTTP framing | Only the user's own processes can connect; FastAPI serves it directly | design decision |
| Fail closed per agent | Engine down / slow (290 s internal timeout) / non-200 / empty reply → Claude Code `ask`, Codex explicit `deny` (Codex fails *open* on hook errors), OpenCode `block`; prompt/post events never block | tested: engine stopped → ask/deny |

# Protocol

- Socket: `$SENTI_SOCKET`, else `$SENTI_HOME/senti.sock`, else `~/.senti/senti.sock` (falls back to `/tmp/senti-<uid>.sock` if the path exceeds 100 bytes).
- Replies: Claude Code `hookSpecificOutput.permissionDecision` allow/ask/deny; Codex empty stdout = allow, `deny` + reason otherwise; PostToolUse `additionalContext` for injection warnings; OpenCode `{verdict, reason, context}`.
- Agent hook timeouts are set to 600 s so the hook's own fail-closed path always wins (an agent-side timeout would fail open).

# Future hardening

Per-agent identity token and peer-process verification (`LOCAL_PEERPID` / audit token) so a same-user process cannot impersonate an agent.

[^sim]: Rules-only simulation with the Swift hook (71 actions)
[^sim-py]: Same simulation with a Python hook client
