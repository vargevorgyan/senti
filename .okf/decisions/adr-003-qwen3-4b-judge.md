---
type: Decision
title: "ADR-003: Qwen3-4B-Instruct (4-bit, MLX) as the local judge"
description: "The local judge is Qwen3-4B-Instruct-2507 4-bit on MLX, the smallest tested model that let no dangerous action through."
tags: [decision, llm, judge]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
sources:
  - id: session
    resource: claude-code session 973dd678-f568-4b80-aeca-b6d8963be82d (2026-09-26)
    title: Ideathon planning session
    author: claude-code/2.1.283
---

# Context
Candidates tested on an 8 GB M1: Laya (English/multilingual), Qwen2.5-1.5B/3B, Qwen3-0.6B/1.7B/4B.

# Decision
**Qwen3-4B-Instruct-2507 4-bit via MLX**, with prefix KV cache, logit verdict, safety bias (allow only if p ≥ 0.6) and async reasons.

# Consequences
0 dangerous allowed; verdict 0.5–1.5 s; 3.1–3.4 GB process footprint (tight on 8 GB → unload when idle, or share a model, or use a corporate judge).
No fine-tuning planned; a smaller model may be tried with few-shot prompting. See [Judge model benchmark](/research/judge-model-benchmark.md).
