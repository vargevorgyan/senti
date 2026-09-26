---
type: Component
title: Decision engine (cascade)
description: The layered decision pipeline — context, cache, rules, detectors, LLM judge — that turns an agent action into allow / ask / block.
tags: [architecture, engine, rules, detectors]
status: stable
resource: /prototype/engine/server.py
generated: { by: claude-code/2.1.283, at: '2026-09-27T02:00:00Z' }
sources:
  - id: rules
    resource: /prototype/engine/rules.py
    title: Rules (L1) and detectors (L2) implementation
  - id: server
    resource: /prototype/engine/server.py
    title: Engine server with cascade, cache, prefetch, async reasons
  - id: concept-draft
    resource: AI_Agent_Guardrails_Concept_Draft.docx (concept draft v0.1)
    title: Concept draft — decision cascade section
    author: human:vargevorgyan
  - id: build
    resource: /engine/src/senti (engine.py, rules.py, profiles.py, judge/)
    title: Full-build engine source
    author: claude-code/2.1.283
---

# Overview

Cheap deterministic checks run first; the LLM sees only what rules cannot settle.[^concept-draft]
In prototype tests ≈75% of actions were settled by rules/detectors in ~3 ms; ≈25% went to the LLM. Implementation: `engine/src/senti/engine.py`.

# Layers (full build)

| # | Layer | What it does | Latency |
|---|---|---|---|
| 0 | **Context** | Session → user's TASK (`UserPromptSubmit` / OpenCode `chat.message`); agent → profile (role profile + per-agent override, strictest wins) | — |
| 0 | **Honeytokens** | Any touch of a planted decoy file or fake key value → block (critical) | µs |
| 1 | **Built-in rules** | Hard deny (never overridable), clearly safe allow, and facts (network? secrets? scripts? packages? deletes?) | µs |
| 1 | **Profile rules** | Org file/network/shell/MCP deny/ask/allow lists and "otherwise" policy from the signed profile | µs |
| 2 | **Detectors** | Script content + followed local imports; inline `-c/-e` code; npm/Makefile targets resolved; secret scanner; base64/hex unwrapping; supply chain (known-bad / typosquat); taint; session tainted by prompt injection → network needs a yes | ms |
| 0 | **Allowlist / cache / prefetch / scope** | "Always allow" choices; identical decision cache (keyed by task, input, script, profile version); write-time script verdicts; task scope contract (optional) | ~ms |
| 3 | **LLM judge router** | Profile mode: `local` (MLX Qwen3-4B), `corporate` (backend gateway), `local_then_corporate` (escalate when local is unsure: ask or confidence < 0.8), `none` (ask) | 0.5–1.5 s local, 1–5 s CPU corporate |
| — | **Decision** | allow / ask / block → agent reply; ask resolved by the agent prompt, a macOS dialog (Codex, OpenCode), or owner approval in the admin panel; undo snapshot for allowed destructive actions; audit | — |

Strictness merge: a profile or detector can make a decision stricter than a built-in allow, never looser than a built-in block.
Backend unreachable + `on_backend_unreachable: strict_local` → corporate mode uses the local judge instead; judge errors → ask.

# Hard-deny rules (examples)

`curl|wget … | sh` or `| python`; `/dev/tcp/`, `nc -e`, `bash -i >&`; `base64 -d | sh`; `dd of=/dev/disk*`; `mkfs`/`diskutil erase`;
`chmod -R 777 /`; Keychain password reads; `crontab` + network; `csrutil disable`; `rm -rf ~|/|~/Documents…`; stopping Senti
(`launchctl unload …senti`, `pkill senti`); history wiping; reading `~/.ssh`, `~/.aws`, `~/.gnupg`, Keychains, browser profiles,
`~/.codex/auth.json`; editing Senti or agent hook configs (self-protection: `~/.claude/settings*.json`, `~/.codex/config.toml|hooks.json`, OpenCode plugins, `~/.senti`).

# Clearly-safe rules (examples)

Read/Grep/Glob inside the project (config-like files go to the judge); Write/Edit inside the project with no secrets or malicious
content (package.json, Makefile, CI files go to the judge — they run later); `ls`, `grep`, `git status/diff/log/commit`, `npm test`
(after resolving what it runs), popular package installs, `rm -rf node_modules|dist|build`, `curl localhost`, docs domains.

# Ask rules (examples)

Reading `.env`/secrets files; persistence (LaunchAgents, shell profiles, git hooks); raw-IP URLs; force-push; typosquatted packages; obfuscated code (`exec(base64…)`).

# Background work

- **Write-time script pre-check**: code files are judged the moment they are written; running them later is instant (seen live with Codex).
- **Undo snapshots**: APFS clones before `rm`/`mv`/overwrites/`git reset --hard`; `senti undo list|restore`.
- **Model unload** after idle (default 15 min), lazy reload.

# Known gaps

Binaries and runtime-downloaded code (sandbox backstop), deeper import graphs, Python GIL contention while the LLM runs.
See [Script inspection](/architecture/script-inspection.md) and [Real-agent tests](/research/real-agent-tests.md).

[^rules]: Rules (L1) and detectors (L2) implementation
[^server]: Engine server with cascade, cache, prefetch, async reasons
[^concept-draft]: Concept draft — decision cascade section
