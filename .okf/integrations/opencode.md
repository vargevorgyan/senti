---
type: Integration
title: OpenCode integration (local models)
description: Plan for protecting OpenCode — the open-source agent the team chose for local models — via a tool.execute.before plugin.
tags: [integrations, opencode, local-models]
status: draft
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
sources:
  - id: hol-opencode
    resource: https://github.com/hashgraph-online/hol-guard/blob/main/src/codex_plugin_scanner/guard/adapters/opencode_pretool.py
    title: HOL Guard OpenCode pretool plugin template
    last_modified: 2026-09-26
  - id: opencode
    resource: https://github.com/anomalyco/opencode
    title: OpenCode repository (~210k stars)
---

# Why OpenCode

The team wants local-model support in the demo via **OpenCode** — a real, popular open-source agent that can use
Ollama, LM Studio or any OpenAI-compatible server — instead of a custom demo agent.

# Mechanism[^hol-opencode]

A TypeScript plugin in `~/.config/opencode/plugins/` exporting a hook `"tool.execute.before": async (input, output) => {...}`.
`input.tool` is the tool name; `output.args` the arguments (e.g. `command`). **Throwing an Error blocks the tool**
and the message is shown to the model. The Senti plugin (~30 lines) sends the event to `senti-hook`/the socket.

- No native "ask": for `ask`, Senti shows its own popup and holds the promise until the user decides, then returns or throws.
- HOL Guard intercepts only bash/shell there; Senti should also map read/write/edit tools.

# Memory constraint on 8 GB Macs

OpenCode's local model + Senti's 2.6 GB judge does not fit. Options: Senti serves **one** Qwen model (OpenAI-compatible
endpoint) used both as OpenCode's model and as the judge; or demo on a 16 GB+ Mac with a bigger agent model.
A 4B model is a weak coding agent but fine for a demo.

# Status

OpenCode not installed on the dev Mac; Ollama not installed (MLX + Qwen3-4B are available).
