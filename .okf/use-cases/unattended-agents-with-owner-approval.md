---
type: Use Case
title: Unattended agents that need a human owner
description: Autonomous agents run with a strict profile, must be sandboxed, and route their questions to an owner who answers in the admin panel.
tags: [use-case, organization]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-27T09:00:00Z' }
sources:
  - id: kb
    resource: /.okf (architecture, research, business sections)
    title: Senti knowledge base — implemented behaviour and test results
    author: claude-code/2.1.283
---

# Who

Team running agents in CI, cron jobs or background automations.

# Situation

Nobody is at the keyboard to answer "should I let this through?", yet some actions (a git push, a new domain) need a human.

# What Senti does

1. The **Autonomous agent** profile blocks every site not on its list and asks before packages.
2. `ask` goes to the **owner**: the request appears in the admin panel's Approvals page; the agent waits; no answer in time → blocked.
3. **Require a sandbox**: if the agent isn't running inside its sandbox, every command needs approval; attempts to leave the sandbox are blocked.
4. The engine verifies which process is calling, so a script can't pretend to be the agent.

# Features involved

Owner approvals, required sandbox, peer-process verification, fail-closed timeouts.

# How well it is verified

**Tested** (approval round-trip in `e2e_modes.py`; sandbox requirement and identity in unit tests; sandbox enforcement verified with srt and Claude Code's sandbox).

# Limits

Approvals go to administrators; per-agent named owners and Slack routing are not built.

# Related

- [enforcement sandbox](/architecture/enforcement-sandbox.md)
- [hook client](/architecture/hook-client.md)
