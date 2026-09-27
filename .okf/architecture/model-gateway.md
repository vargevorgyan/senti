---
type: Component
title: Local model gateway (DIY agents)
description: OpenAI-compatible proxy on 127.0.0.1:11435 in front of Ollama/LM Studio that checks every tool call a model proposes before a hook-less agent sees it.
tags: [architecture, gateway, local-models, integrations]
status: stable
resource: /engine/src/senti/gateway.py
generated: { by: claude-code/2.1.283, at: '2026-09-27T08:00:00Z' }
sources:
  - id: code
    resource: /engine/src/senti/gateway.py, /engine/tests/test_gateway.py, /demo/diy_agent.py
    title: Gateway implementation, tests and demo agent
---

# Overview

Custom agents (a Python loop on Ollama, LangChain, …) have no hooks. They point their base URL at `http://127.0.0.1:11435/v1`
(started with the engine; `gateway_enabled`, `gateway_port`, `gateway_upstream` in `~/.senti/config.json`, default upstream
`http://localhost:11434/v1`). Loopback only.

# Flow

`POST /v1/chat/completions` is forwarded upstream (non-streaming). Each proposed `tool_call` is mapped to a Senti action by name and
arguments (shell-like → Bash, read/write/edit/delete file, fetch URL, search, otherwise `mcp__gateway__<name>`) and run through the
engine (task = last user message; headers `X-Senti-Agent`, `X-Senti-Cwd`, `X-Senti-Session`). Blocked calls are removed and explained
in the message content; if none remain, `finish_reason` becomes `stop`. `ask` shows the macOS dialog (no GUI → block). Brokered
secrets are rewritten like for hooks. Streaming clients get the checked answer re-emitted as SSE. Other `/v1/*` paths pass through.

Verified live with `qwen2.5:3b` in Ollama (`demo/diy_agent.py`): the SSH-key exfiltration call was removed, `ls -la` passed.
