---
type: Component
title: Admin panel
description: The React admin panel for organization administrators — overview, live activity, approvals, profile editor with judge modes, people and roles, devices and enrollment, corporate judge settings and playground, change log.
tags: [architecture, admin, react, ui]
status: stable
resource: /admin/src
generated: { by: claude-code/2.1.283, at: '2026-09-27T01:45:00Z' }
sources:
  - id: admin
    resource: /admin/src
    title: Admin panel source
  - id: design
    resource: /docs/design (copy of claude.ai artifact CZ821iLED5QtDoAh7JWzQg)
    title: Senti design system by the team's designer
    author: human:anahit
---

# Overview

Single-page React app (Vite, TypeScript, react-router) served by nginx in the `admin` container, which proxies `/api/`
(including Server-Sent Events, unbuffered) to the backend. Auth: admin email/password → JWT in `localStorage`.
Live updates arrive over one `EventSource` (`/api/v1/admin/stream?token=`).[^admin]

# Pages

| Page | What the admin does |
|---|---|
| Overview | First-person summary ("In the last 24 hours I checked N actions, stopped B and asked about A"), per-hour chart, by agent, top rules, recent blocks as Blocked alerts, live feed |
| Activity | Filter/search every decision, expand for task, layer, profile, input; CSV export; new rows stream in |
| Approvals | Answer `ask` requests routed to the owner/admin (ApprovalPrompt component: Block primary, Allow once) |
| Profiles / editor | Judge mode (**Company AI** — default and recommended; on each Mac; Mac first then company; none), company instructions, privacy of corporate calls, files/network/shell/MCP/packages rules, per-agent overrides (e.g. "no network for OpenCode"), protections (undo, decoys, injection warnings, task scope, sandbox), who answers ask, offline behaviour. Save pushes to Macs within ~0.2 s |
| People and roles | **Add person and invite** (one-time `sti_` key, 48 h, copy-once `senti setup` command), invite status ("Joined from <Mac>"), role per person, **server access** role for the gateway, per-agent profile override, role CRUD |
| Devices | Points to People for invites (shared codes are off); legacy codes list; device status (online, judge, profile version), revoke |
| Corporate judge | OpenAI-compatible endpoint/model/key, reachability, playground with profile instructions and p(allow/ask/block) |
| **Server gateway** | Plain-English policy → Generate rules → review role cards, warnings and example actions → Approve; agents (bot tokens shown once, connect commands, revoke); live gateway activity |
| Change log | Who changed what |

# Design

Tokens, type (Bricolage Grotesque, DM Sans, JetBrains Mono), Alert and ApprovalPrompt follow the designer's system in
`docs/design/`; light and dark themes; responsive to 390 px (Playwright checks no horizontal overflow).[^design]
The real logo SVGs are not exportable from the artifact API; `admin/public/senti-app-icon.svg` is a placeholder drawn from the brand book.

[^admin]: Admin panel source
[^design]: Senti design system by the team's designer
