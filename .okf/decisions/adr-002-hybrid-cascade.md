---
type: Decision
title: "ADR-002: Hybrid cascade, not LLM-only or rules-only"
description: "Decisions use rules and detectors first and a local LLM only for the grey zone, because LLM-only is too slow and rules-only prompts too often and misses obfuscated scripts."
tags: [decision, engine, performance]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
sources:
  - id: session
    resource: claude-code session 973dd678-f568-4b80-aeca-b6d8963be82d (2026-09-26)
    title: Ideathon planning session
    author: claude-code/2.1.283
---

# Context
Measured: rules-only settles ~75% in 3 ms but sends every unclear action to the user; LLM-only would add 0.7–2 s to **every** action.
Concept draft independently proposed the same cascade.

# Decision
Cascade: cache → rules (hard deny / clearly safe) → detectors → LLM judge → decision. The LLM can never override a hard deny; everything fails closed.

# Consequences
~25% of actions reach the LLM; 22/22 dangerous actions stopped in simulation; ~10% overhead on a real Claude Code session.
See [Decision engine](/architecture/decision-engine.md), [End-to-end simulation](/research/end-to-end-simulation.md).
