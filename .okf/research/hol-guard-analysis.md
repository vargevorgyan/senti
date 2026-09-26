---
type: Competitor Analysis
title: HOL Guard analysis
description: What HOL Guard is, its architecture, what it does not do (no LLM, no .py script reading), and what Senti can reuse under Apache-2.0.
tags: [research, competitor, hol-guard]
status: stable
stale_after: 2026-12-31
resource: https://github.com/hashgraph-online/hol-guard
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
sources:
  - id: repo
    resource: https://github.com/hashgraph-online/hol-guard
    title: HOL Guard repository (shallow clone analysed 2026-09-26, v3.6.2 on PyPI)
    last_modified: 2026-09-26
  - id: adr
    resource: https://github.com/hashgraph-online/hol-guard/tree/main/docs/guard/adr
    title: HOL Guard ADRs 0003, 0006, 0008, 0013 and hook-review-engine.md
---

# What it is

"Open-source antivirus for AI agents" (Apache-2.0, ~669★, created 2026-03, very active). ~380k lines of Python,
~47k lines of Rust, React dashboard. Supports ~16 agents via native hooks, launcher wrappers and managed MCP proxies.
Also ships `plugin-scanner` (CI scanning of agent plugins/skills/MCP servers). Optional paid **Guard Cloud**.[^repo]

# Architecture[^adr]

- **Python control plane** (CLI + local daemon): adapters per agent, policy, SQLite store, receipts, approvals.
- **Rust runtime data plane** (`hol-guard-runtime`) for latency-sensitive hook evaluation; authenticated resident protocol; fail closed on native failure/overload.
- **Deterministic rules only**: command extension catalog, secret scanner, "Safe Decode" (base64/hex/gzip/heredoc/`python -c` unwrapping). Docs state the scanner "never runs an LLM".
- **UI**: CLI + local browser dashboard (approval center, command activity, protection center, policies, supply chain, fleet); macOS notifications via osascript/terminal-notifier. The native menu-bar app is a **separate product (`hol-guard-desktop`, not public)**.

# Gaps Senti exploits

- **No LLM / no task context** (does not install `UserPromptSubmit` for Claude Code).
- **Python scripts not read**: `python script.py` in the workspace is explicitly excluded from the destructive category; only shell scripts (`bash x.sh`, `./x.sh`, `source`) are opened and scanned. A `.py` that uploads `~/.ssh/id_rsa` would likely pass.
- Developer/security-team UX, not plain language; no open-source native Mac app.

A live test via `uvx hol-guard command test` was inconclusive (native runtime unavailable in the sandboxed install).

# Reuse (Apache-2.0, keep NOTICE)

Secret rule catalog (`guard/secrets/public_rule_catalog.py`), command extension rules (`contributions/extensions/`),
red-team fixtures (`tests/fixtures/guard-red-team`, `malicious-skill-plugin`), agent adapters (Codex, OpenCode, Cursor, ...).
Not a fork base: too large, Python+Rust, and the Mac app is not included. See [ADR-004](/decisions/adr-004-do-not-fork-hol-guard.md).

[^repo]: HOL Guard repository (shallow clone analysed 2026-09-26, v3.6.2 on PyPI)
[^adr]: HOL Guard ADRs 0003, 0006, 0008, 0013 and hook-review-engine.md
