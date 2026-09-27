---
type: Use Case
title: Local models, offline agents and home-made agents
description: OpenCode on a local model, or a custom Python agent on Ollama, gets the same protection fully offline — via a plugin or the model gateway.
tags: [use-case, individual]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-27T09:00:00Z' }
sources:
  - id: kb
    resource: /.okf (architecture, research, business sections)
    title: Senti knowledge base — implemented behaviour and test results
    author: claude-code/2.1.283
---

# Who

Privacy-minded user, researcher, or team building its own agents.

# Situation

They run agents on local models (Ollama, LM Studio) with no cloud, or write their own agent loop that has no hook system.

# What Senti does

1. **OpenCode:** the Senti plugin checks every tool call before it runs (verified with `qwen2.5:3b` in Ollama).
2. **DIY agents:** point the agent's base URL at `http://127.0.0.1:11435/v1`; the gateway checks each tool call the model proposes and removes blocked ones with an explanation.
3. The judge itself is local (Qwen3-4B on MLX), so nothing leaves the Mac.
4. Custom systems can also call `POST /v1/check` on the engine socket directly.

# Features involved

OpenCode plugin, model gateway, local judge, generic API.

# How well it is verified

**Verified live** (OpenCode on Ollama; DIY agent via the gateway: SSH-key exfiltration removed, `ls` passed).

# Limits

Tool-call mapping in the gateway is name-based; unusual tool names go to the judge as generic tools.

# Related

- [model gateway](/architecture/model-gateway.md)
- [opencode](/integrations/opencode.md)
- [local models](/integrations/local-models.md)
