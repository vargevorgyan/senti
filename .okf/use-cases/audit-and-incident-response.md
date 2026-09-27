---
type: Use Case
title: Audit trail and spotting a compromised agent
description: Every decision is logged tamper-evidently and uploaded; decoy secrets catch hijacked agents; the security team investigates from one timeline.
tags: [use-case, security]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-27T09:00:00Z' }
sources:
  - id: kb
    resource: /.okf (architecture, research, business sections)
    title: Senti knowledge base — implemented behaviour and test results
    author: claude-code/2.1.283
---

# Who

Security team, compliance officer, incident responder.

# Situation

They must show which agents did what, and detect an agent that has been steered by prompt injection before data leaves.

# What Senti does

1. Every decision (who, which agent, action, verdict, deciding layer, reason, latency) goes to a **hash-chained** local log (`senti audit verify`) and to the org backend.
2. The admin panel shows an Overview, a live Activity feed with filters and CSV export, and a change log of admin actions.
3. **Honeytokens:** fake keys planted in projects (`senti honeytoken plant DIR`); any agent reading or sending one is stopped at once and flagged as a likely compromise.
4. Plain-English reasons make reviews possible for non-specialists.

# Features involved

Audit log, admin Activity/Overview, honeytokens, change log.

# How well it is verified

**Tested** (audit chain tamper test, honeytoken tests, admin Playwright tests).

# Limits

The org copy of the log is only as trustworthy as the device that uploaded it; SIEM export is not built.

# Related

- [admin panel](/architecture/admin-panel.md)
- [decision engine](/architecture/decision-engine.md)
