---
type: Evaluation
title: Laya evaluation (rejected as judge)
description: Why the Laya zero-shot decision model was rejected for command and access limiting after testing on an M1.
tags: [research, laya, rejected]
status: stable
resource: https://github.com/NandhaKishorM/laya
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
sources:
  - id: laya
    resource: https://github.com/NandhaKishorM/laya
    title: Laya repository (v0.3.20, Apache-2.0)
  - id: results
    resource: /prototype/results/
    title: results_laya_*.json
---

# What Laya is

A non-autoregressive "System 1" classifier (ModernBERT-large 421M English, mmBERT-base 322M multilingual) that answers
typed questions (choice / score / yes-no) over text in one forward pass. Claims ~33 ms on a T4 GPU.[^laya]
It is a **classifier, not an enforcement mechanism** — something else must still limit commands.

# Results on 43 agent actions[^results]

English: 49% exact, 13/18 dangerous stopped, **missed the hidden-exfiltration script**, `curl | sudo sh`, `dd`; flagged `ls` and `grep`.
Multilingual: let 14/18 dangerous actions through. Latency on M1: 125–415 ms (not 33 ms). Memory 2.2–3.9 GB.
Its own benchmark shows zero-shot 0.36 → 0.77 only after fine-tuning. No plain-language explanations.

# Decision

Rejected — see [ADR-005](/decisions/adr-005-reject-laya.md). Qwen3-4B beat it on every axis except raw speed.

[^laya]: Laya repository (v0.3.20, Apache-2.0)
[^results]: results_laya_*.json
