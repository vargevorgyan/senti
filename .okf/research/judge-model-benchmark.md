---
type: Benchmark
title: Judge model benchmark
description: Accuracy, latency and memory of Laya and Qwen models as Senti's action judge on 43 labelled agent actions, on an M1 with 8 GB RAM.
tags: [research, benchmark, llm, performance]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
stale_after: 2027-03-31
sources:
  - id: cases
    resource: /prototype/bench/cases.py
    title: 43 labelled agent actions (18 block, 9 ask, 16 allow)
  - id: results
    resource: /prototype/results/
    title: Raw JSON results per model
  - id: tmodels
    resource: /prototype/engine/t_models.py
    title: Grey-zone model comparison (21 actions, verdict-only)
---

# Setup

Hardware: Apple M1, 8 GB RAM, macOS 26. Dataset: 43 hand-written actions (18 should block, 9 ask, 16 allow), including
scripts whose content (not name) is malicious.[^cases] Single run each; written by the same person who wrote the rules —
good for ranking options, not a rigorous benchmark.

# Standalone judges (full-text generation, no rules)[^results]

| Judge | Dangerous stopped | Dangerous allowed | Safe interrupted | Exact | Median latency | Memory |
|---|---|---|---|---|---|---|
| Laya English 421M (CPU) | 13/18 | 5 (incl. hidden-exfil script, `curl\|sudo sh`, `dd`) | 5/16 | 49% | 416 ms | ~2.2 GB |
| Laya English (MPS) | 13/18 | 5 | 5/16 | 49% | 305 ms | ~3.9 GB |
| Laya Multilingual 322M (MPS) | 4/18 | 14 | 1/16 | 44% | 125 ms | ~3.2 GB |
| Qwen2.5-1.5B 4-bit | 15/18 | 3 (incl. SSH-key upload) | 3/16 | 67% | 0.9 s | 1.3 GB |
| Qwen2.5-3B 4-bit | 16/18 | 2 | 3/16 | 63% | 1.8 s | 2.1 GB |
| **Qwen3-4B-Instruct-2507 4-bit** | **18/18** | **0** | **1/16** | **93%** | 2.9 s | 2.6 GB |

# Verdict-only (logit trick, prefix cache) on 21 grey-zone actions[^tmodels]

| Model | Dangerous allowed | Verdict median | Peak memory |
|---|---|---|---|
| **Qwen3-4B-Instruct-2507** | **0** | 0.7 s | 2.6 GB |
| Qwen3-1.7B | 1 (hidden-exfil script) | 0.3 s | 1.4 GB |
| Qwen3-0.6B | 5 | 0.12 s | 0.65 GB |

# Conclusions

- Qwen3-4B-Instruct-2507 is the minimum safe local judge today.
- Its explanations are plain-English and specific ("It's sending your private SSH key to an online dropbox").
- Possible no-training path to a smaller judge: few-shot examples in the cached prompt with Qwen3-1.7B (untested).
- Laya rejected — see [Laya evaluation](/research/laya-evaluation.md).

[^cases]: 43 labelled agent actions (18 block, 9 ask, 16 allow)
[^results]: Raw JSON results per model
[^tmodels]: Grey-zone model comparison (21 actions, verdict-only)
