---
type: Component
title: Decision engine (cascade)
description: The layered decision pipeline — context, cache, rules, detectors, LLM judge — that turns an agent action into allow / ask / block.
tags: [architecture, engine, rules, detectors]
status: stable
resource: /prototype/engine/server.py
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
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
---

# Overview

Cheap deterministic checks run first; the LLM sees only what rules cannot settle.[^concept-draft]
In testing ≈75% of actions were settled by rules/detectors in ~3 ms; ≈25% went to the LLM.

# Layers

| # | Layer | What it does | Latency |
|---|---|---|---|
| 0 | **Context** | Session → user's TASK (from `UserPromptSubmit`); agent identity → profile | — |
| 0 | **Decision cache** | Key = sha256(task, tool, input, script text). Same question → same answer | ~3 ms end-to-end |
| 1 | **Rules** | Hard deny (can never be overridden) and clearly-safe allow; also collect *facts* (uses network? touches secrets? runs a script?) | µs |
| 2 | **Detectors** | Secret scanner (AWS/GitHub/OpenAI/Anthropic/Stripe/Slack keys, private keys, high-entropy assignments); base64 unwrapping → re-check; script static scan (reads secrets **and** network → block); taint (sensitive file + network tool in one command → block) | ms |
| 3 | **LLM judge** | Task-aware verdict for the grey zone; see [LLM judge](/architecture/llm-judge.md) | 0.5–1.5 s local |
| — | **Decision** | allow / ask (popup) / block (deny + reason to the agent); log + cache | — |

# Hard-deny rules (examples)

`curl|wget … | sh`; `/dev/tcp/` reverse shells, `nc -e`; `base64 -d | sh`; `dd of=/dev/disk*`; `mkfs`/`diskutil erase`;
`chmod -R 777 /`; `security dump-keychain`/`find-generic-password -w`; `crontab` + network; `csrutil disable`;
`rm` of `~` or personal folders (Documents, Desktop, Pictures, Library, ...) outside the project; reading
`~/.ssh`, `~/.aws`, `~/.gnupg`, Keychains, browser profiles; editing Senti/agent hook configs (self-protection).[^rules]

# Clearly-safe rules (examples)

Read/Grep/Glob inside the project (except config/secret-looking files, which go to the judge with the task);
Write/Edit inside the project with no detected secrets; `ls`, `grep`, `git status/diff/log/commit`, `npm test`,
`npm run …`, `rm -rf ./build|dist|node_modules|…` inside the project; `curl` to localhost; docs domains.[^rules]

# Ask rules (examples)

Reading `.env`/secrets files; writing LaunchAgents or shell profiles (persistence); fetching from raw IP URLs.

# Background work (never blocks the agent)

- **Write-time script pre-check**: when an agent writes/edits a code file, the judge evaluates it immediately; the verdict is cached by content hash so the later run is usually instant. This blocked the injected `helper.py` in tests.[^server]
- **Async reasons**: popup opens on the verdict; the plain-English reason streams in ~1 s later.
- **Model unload** after idle (planned).

# Known gaps

See [Script inspection](/architecture/script-inspection.md) (npm scripts, Makefiles, imports not yet resolved)
and the misses listed in [End-to-end simulation](/research/end-to-end-simulation.md).

[^rules]: Rules (L1) and detectors (L2) implementation
[^server]: Engine server with cascade, cache, prefetch, async reasons
[^concept-draft]: Concept draft — decision cascade section
