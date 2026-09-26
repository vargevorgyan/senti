---
type: Experiment
title: sandbox-runtime test
description: Test of Anthropic's sandbox-runtime (srt) against an exfiltration script using fake secrets.
tags: [research, sandbox, srt, experiment]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
sources:
  - id: srt
    resource: https://github.com/anthropics/sandbox-runtime
    title: anthropics/sandbox-runtime (npx @anthropic-ai/sandbox-runtime)
---

# Setup

Fake `~/.ssh/id_rsa` and `.env` in a scratch dir; settings: `denyRead` on the fake `.ssh` and `**/.env`, `allowWrite` project only,
`allowedDomains: [pypi.org]`. Upload target `example.com` (harmless).[^srt]

# Results

| Script action | Without sandbox | With srt |
|---|---|---|
| Read `~/.ssh/id_rsa` | read | Operation not permitted |
| Read `.env` | read | Operation not permitted |
| Upload to unlisted domain (curl) | HTTP 405 (reached server) | 000 / 403 at proxy (blocked) |
| Write outside project | written | Operation not permitted |
| Allowlisted pypi.org (curl) | 405 | 405 (reached) |

Overhead: ~0.43 s and ~64 MB per wrapped command via `npx` (mostly Node start-up).

[^srt]: anthropics/sandbox-runtime (npx @anthropic-ai/sandbox-runtime)
