---
type: Use Case
title: Role-based rules for a whole team
description: An admin gives engineers, PMs and bots different agent permissions from one panel; changes reach every Mac in a fraction of a second.
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

Security or IT admin at a company with many people using AI agents.

# Situation

Engineers need shell and packages; PMs only docs and trackers; unattended bots only a few domains. Each agent vendor has its own permission system.

# What Senti does

1. The admin edits **Developer**, **PM / Product** and **Autonomous agent** profiles in the admin panel (files, sites, shell, MCP tools, packages, judge mode).
2. People get profiles by role; one person's agent can be made stricter (e.g. "no network for OpenCode"); agents can only be narrowed, never given more than their person.
3. Saving pushes a **signed** bundle to every enrolled Mac over SSE (~0.2 s); Macs keep working with the cached profile if the server is down.
4. One policy covers Claude Code, Codex and OpenCode alike.

# Features involved

Org backend, admin panel, signed profiles, per-agent overrides, delegation rule.

# How well it is verified

**Tested** end to end (`scripts/e2e_modes.py` 14/14: all judge modes, push, overrides).

# Limits

Profiles are assigned by role/email inside Senti; identity-provider sync (Okta, Entra ID) is not built.

# Related

- [org backend and profiles](/architecture/org-backend-and-profiles.md)
- [admin panel](/architecture/admin-panel.md)
