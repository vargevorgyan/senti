---
type: Environment
title: Development environment
description: The team's primary dev Mac, installed and missing tools, accounts, and resource constraints observed on 2026-09-26.
tags: [environment, setup]
status: stable
stale_after: 2026-10-31
generated: { by: claude-code/2.1.283, at: '2026-09-26T19:10:00Z' }
---

# Primary dev Mac (repo owner)

| Item | Value |
|---|---|
| Hardware | Apple M1, 8 CPU cores, **8 GB RAM** |
| Disk | 228 GB, **~91% full (~19 GB free)** after model downloads |
| OS | macOS (Darwin 25.5) |
| Toolchain | Xcode 26.5, Swift 6.3.2, Python 3.10 (system) / 3.12 via uv, uv 0.12.6, Node 24, git 2.50 |
| GitHub | `gh` logged in as `vargevorgyan` |
| Agents installed | Claude Code 2.1.283; ChatGPT.app (agent mode not hookable); `~/.codex/` exists with a login but **Codex CLI not installed** |
| Not installed | Codex CLI, OpenCode, Ollama, LM Studio, Rust |
| Model cache | `~/.cache/huggingface`: Qwen3-4B-Instruct-2507-4bit (keep), plus test models (Qwen2.5-1.5B/3B, Qwen3-0.6B/1.7B, Laya) — ~7 GB total, candidates for cleanup |

# Constraints that shaped decisions

- 8 GB RAM → one 4B model at a time (~3.1–3.4 GB Senti process); agent model + judge cannot both fit → shared-model mode ([Local models](/integrations/local-models.md)).
- Python 3.10 framework install lacks CA certificates (urllib HTTPS fails) — use curl or install certs when testing.
- Unix socket paths must be ≤104 chars → socket at `/tmp/senti-proto.sock`.
