---
type: Codebase Guide
title: Prototype code guide
description: Map of the prototype engine and benchmark code in prototype/, how to set it up and run the simulations and real-agent tests.
tags: [prototype, code, how-to]
status: stable
resource: /prototype/
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
---

# Layout

| Path | What |
|---|---|
| `prototype/engine/rules.py` | L1 rules + L2 detectors (`check_action`, `check_bash`, secret scanner, base64 decode) |
| `prototype/engine/judge.py` | L3 LLM judge (MLX, prefix cache, logit verdict, lazy reason) |
| `prototype/engine/server.py` | Unix-socket engine: cascade, decision cache, task tracking, `--async-reason`, `--prefetch`, `--no-llm` |
| `prototype/engine/senti-hook.swift` | Hook client (compile with `swiftc -O`) |
| `prototype/engine/hook_py.py` | Python hook client (for latency comparison) |
| `prototype/engine/sessions.py` | Simulated sessions + demo project files (creates `engine/webapp/`) |
| `prototype/engine/simulate.py`, `analyze.py`, `run.sh` | Replay sessions through the hook; report accuracy/latency |
| `prototype/engine/t_judge.py`, `t_models.py` | Judge micro-benchmarks |
| `prototype/engine/hooks-settings.example.json` | Claude Code hook settings template |
| `prototype/bench/` | Standalone judge benchmark (43 labelled cases; Laya and Qwen scripts) |
| `prototype/results/` | Raw JSON results referenced by [Judge model benchmark](/research/judge-model-benchmark.md) and [End-to-end simulation](/research/end-to-end-simulation.md) |

# Setup

```bash
uv venv .venv-mlx --python 3.12 && uv pip install --python .venv-mlx/bin/python mlx-lm psutil
cd prototype/engine && swiftc -O senti-hook.swift -o senti-hook
# first run downloads mlx-community/Qwen3-4B-Instruct-2507-4bit (~2.2 GB)
```

# Run

```bash
# simulation (rules only / full / optimized)
PY=../../.venv-mlx/bin/python ./run.sh res.json 1 --no-llm
PY=../../.venv-mlx/bin/python THINK=1.0 ./run.sh res.json 1 --async-reason --prefetch
../../.venv-mlx/bin/python analyze.py res.json decisions.jsonl -v

# real Claude Code session: start server.py <sock> <project>, then
claude -p "<task>" --settings hooks-settings.json
```

**Safe-testing practice:** demos and tests use fake secrets (e.g. `FAKE-PRIVATE-KEY-123`, `sk_live_fake`) in scratch folders and unreachable upload targets (`https://collector.example.invalid`, `example.com`) so a guard failure can never leak anything real.

Apple Silicon required for MLX. Unix socket paths must be ≤104 chars (default `/tmp/senti-proto.sock`).
Laya benchmark needs a separate venv with `laya psutil` (PyTorch).
