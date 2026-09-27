---
type: Guide
title: Customer onboarding — the easy path
description: How a company goes from nothing to protected laptops and a supervised server gateway using the server installer, personal invites, senti setup and the local MCP bridge.
tags: [guide, onboarding, installer, mcp, customers]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-27T13:00:00Z' }
sources:
  - id: installer
    resource: /senti-server
    title: Server installer and manager
  - id: setup
    resource: /engine/src/senti/cli.py
    title: senti setup, senti connect, senti mcp
---

# Three people, three steps

| Who | Does | Time |
|---|---|---|
| **Admin (IT)** | `./senti-server` on a company server: answers ~5 questions (company, login, network, which AI, demo data) | ~1–5 min |
| **Admin** | Admin panel → People → *Add person and invite* (+ choose their **server access** role) → sends the one-line command | 30 s per person |
| **Employee** | Runs the command: `senti setup --backend … --fingerprint … --key sti_…` | ~1 min |

Employees' Macs run **no AI model**: a thin Senti agent (~100 MB) decides obvious actions itself and sends unclear ones to the
company's AI filter ([ADR-012](/decisions/adr-012-company-cloud-ai-filter.md)). `senti setup` = join the organization → start Senti → protect the assistants that are installed (hooks) → connect them to
the company server (`senti connect`) → start at login. Safe to run again.[^setup]

# Server installer (`./senti-server`)[^installer]

Checks/starts Docker (installs it on Linux with confirmation), checks memory/disk/ports, writes `.env` (mode 600) with
generated secrets, builds and starts, creates the admin (random password shown once, then removed from `.env`), optional
private AI model / existing model API / none, optional demo data, prints URL + certificate fingerprint + next steps.
Management: `status · info · logs · stop · start · update · backup · restore · reset-password · uninstall [--delete-data]`.
Tested on this Mac: install ~1 min (without the model download), update 14 s keeping data, backup/restore, password reset.

# Connecting AI assistants to the server gateway (MCP)

Assistants (Claude Code, Claude Desktop, Cursor, Codex, OpenCode) **refuse the server's self-signed certificate** (tested:
Claude Code fails with `DEPTH_ZERO_SELF_SIGNED_CERT`). So they don't connect directly: `senti connect` gives each one a
`company-server` entry that runs the local bridge `senti mcp`, which forwards to `/api/v1/mcp/` using the Mac's pinned
certificate and device token. The entry contains no secret; the person's **server role** (People page) decides access;
revoking the Mac or clearing the role cuts access immediately. Claude Code reports the entry as ✔ Connected, and a real
session read tickets while Senti refused the card-number column and `payments/cards.csv`.

**Bots** (no person, no Mac): an agent token from the Server gateway page, used either directly (clients that accept the
certificate) or through the same bridge: `senti mcp --backend URL --token sag_… --fingerprint FP`.

# Still missing for non-technical customers

A packaged Mac install (today `senti setup` needs the engine from the repo + `uv`): serve a signed installer from the
company's own Senti server so the invite is a single link; a real certificate for a company domain; SSO for admins.

[^setup]: senti setup, senti connect, senti mcp
[^installer]: Server installer and manager
