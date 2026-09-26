---
type: Component
title: Enforcement sandbox (sandbox-runtime)
description: OS-level file and network limits per agent using Anthropic's sandbox-runtime (macOS Seatbelt), the backstop for everything hooks cannot see.
tags: [architecture, sandbox, enforcement, security]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-27T02:00:00Z' }
sources:
  - id: srt
    resource: https://github.com/anthropics/sandbox-runtime
    title: anthropics/sandbox-runtime (srt), Apache-2.0, beta research preview
    last_modified: 2026-09-26
  - id: srt-test
    resource: /research/sandbox-runtime-test.md
    title: Senti test of srt against an exfiltration script
---

# Why it is needed

Hooks only see what the agent *reports* (e.g. `python3 x.py`). Code downloaded or generated while a script runs,
compiled binaries, or clever obfuscation are invisible to hooks. The sandbox enforces limits **inside** the
process tree regardless of what any check decided.

# How

`srt` wraps a command with a dynamically generated macOS Seatbelt (`sandbox-exec`) profile plus an HTTP/SOCKS
proxy for network allowlisting.[^srt]

- Files: `denyRead` (e.g. `~/.ssh`, `**/.env`), `allowWrite` (project only; write is deny-by-default).
- Network: `allowedDomains` allowlist (deny-by-default); traffic goes through srt's proxy.

Senti generates **one profile per agent** from its policy/profile (see [Org backend and profiles](/architecture/org-backend-and-profiles.md)).
For Claude Code, its built-in sandbox (same srt) can be enabled; for other agents and MCP servers, Senti wraps the launch command.

# In the full build

`senti sandbox --agent codex --show` writes `~/.senti/sandbox/<agent>.srt.json` from the active profile (base secret paths +
profile `files.deny` → `denyRead`; project, `/tmp`, the agent's own state dir → `allowWrite`; Senti and hook configs →
`denyWrite`; base registries + agent API hosts + profile `network.allow` → `allowedDomains`; the Senti socket in
`allowUnixSockets` so hooks still reach the engine from inside). `senti run --agent codex -- codex …` launches through srt.
Per agent (verified 2026-09-27):

- **Claude Code:** `senti install claude --sandbox` writes Claude Code's built-in Bash sandbox block (`sandbox.enabled`,
  `failIfUnavailable`, `filesystem.denyRead/denyWrite`, `network.allowedDomains/deniedDomains/allowUnixSockets/strictAllowlist`)
  derived from the same profile. Tested live: commands run sandboxed, hooks still reach Senti.
- **OpenCode (and any CLI agent):** `eval "$(senti shell-init --agents opencode)"` defines a shell function that starts the agent
  under `senti run` (srt). Tested: `.env` unreadable, home writes denied, `example.com` blocked, `pypi.org` allowed.
- **Codex:** keeps its own command sandbox (`-s workspace-write`); wrapping the whole Codex process in Seatbelt breaks Keychain-based login.

Profiles carry `features.sandbox` so admins can state the requirement; enforcing it per device is still manual.

# Measured

Blocked reading a fake `~/.ssh/id_rsa` and `.env`, upload to an unlisted domain (HTTP 403 at proxy), and writes
outside the project, while the allowlisted `pypi.org` still worked. Overhead ≈0.43 s and ≈64 MB per wrapped command
when started via `npx` (mostly Node start-up).[^srt-test]

# Caveats

Deeper OS enforcement — Apple's **Endpoint Security** framework (see every process exec/file open) and **Network Extension** content filters (per-process egress) — requires special entitlements/approval from Apple; roadmap only, and worth stating honestly in the pitch because judges will ask.


Beta research preview; APIs may change. `sandbox-exec` is deprecated by Apple but still functional.

[^srt]: anthropics/sandbox-runtime (srt), Apache-2.0, beta research preview
[^srt-test]: Senti test of srt against an exfiltration script
