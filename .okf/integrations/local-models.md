---
type: Integration
title: Local models support
description: The three meanings of local-model support in Senti (agents on local models, DIY agents, Senti's own judge), memory limits by Mac size, and judge auto-selection.
tags: [integrations, local-models, memory]
status: draft
generated: { by: claude-code/2.1.283, at: '2026-09-26T19:10:00Z' }
sources:
  - id: session
    resource: claude-code session 973dd678-f568-4b80-aeca-b6d8963be82d (2026-09-26)
    title: Local models discussion
---

# Three meanings

1. **Agents running on a local model** (OpenCode, Cline on Ollama/LM Studio): covered by hooks/plugins — the model behind the agent is irrelevant. Demo choice: [OpenCode](/integrations/opencode.md).
2. **DIY agents without hooks** (Python loop on Ollama, LangChain): possible later via a *local model gateway* — an OpenAI-compatible proxy that inspects the tool calls the model proposes and replaces blocked ones; plus the sandbox. Not in the current scope.
3. **Senti's own judge** can be any local runtime (MLX, Ollama, LM Studio, llama.cpp) behind one interface.

# Memory: agent model + Senti judge (typical 4-bit sizes; only Qwen3-4B measured)

| Mac RAM | Agent model | + Senti judge (Qwen3-4B, ~2.6 GB) | Verdict |
|---|---|---|---|
| 8 GB | 7–8B (~4.5–5 GB) | ~7.5 GB | too tight, swapping |
| 16 GB | 7–8B | ~7.5 GB | OK |
| 32 GB+ | up to ~30B | fine | OK |

# Judge auto-selection (planned)

Dedicated judge if memory allows → otherwise **shared model** (reuse the model already loaded for the agent, with a separate clean prompt;
weaker isolation but no extra memory) → otherwise **rules + sandbox only** (unclear → ask).
For the 8 GB demo Mac: Senti serves one Qwen model used both as OpenCode's model and as the judge.
