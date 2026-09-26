---
type: Decision
title: "ADR-007: OS sandbox as the enforcement backstop"
description: "Every agent's commands run under an OS-level sandbox (sandbox-runtime / Seatbelt) with per-agent file and network limits, because hooks cannot see inside running code."
tags: [decision, sandbox, security]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
sources:
  - id: session
    resource: claude-code session 973dd678-f568-4b80-aeca-b6d8963be82d (2026-09-26)
    title: Ideathon planning session
    author: claude-code/2.1.283
---

# Decision
Use anthropics/sandbox-runtime (srt) profiles generated from Senti policies; enable Claude Code's built-in sandbox where available.

# Consequences
Downloaded/obfuscated code is contained even if every check misses it. Beta dependency; ~0.4 s wrapper start via npx.
See [Enforcement sandbox](/architecture/enforcement-sandbox.md).
