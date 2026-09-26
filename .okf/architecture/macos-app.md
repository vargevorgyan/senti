---
type: Component
title: Senti macOS app
description: Planned native SwiftUI menu-bar app — approval popup, activity log, per-agent settings — that fronts the local engine.
tags: [architecture, macos, swiftui, ui]
status: superseded
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
sources:
  - id: session
    resource: claude-code session 973dd678-f568-4b80-aeca-b6d8963be82d (2026-09-26)
    title: Stack decision and UI discussion
    author: human:vargevorgyan
---

> **Superseded (2026-09-27):** no client UI app will be built — see [ADR-010](/decisions/adr-010-no-client-ui-fastapi-react.md). Its responsibilities moved to the agents' native prompts, macOS notifications/dialogs from the engine, the `senti` CLI, and the org [admin panel](/architecture/admin-panel.md).

# Overview

The team chose **native Swift / SwiftUI** for the MVP (see [ADR-001](/decisions/adr-001-native-swift-macos-app.md)).
Xcode 26.5 / Swift 6.3 are available on the dev Mac. Not started yet.

# Responsibilities

- Menu-bar icon with status, pause/kill switch for all agents.
- **Approval popup** for `ask`: plain-English reason (streams in), Allow / Block, "always allow for this project" (becomes a rule).
- Notifications for `block`.
- Decision log that agents cannot quietly edit (append-only, outside agent-writable paths).
- Activity timeline across all agents (which layer decided, latency) — also the seed of the enterprise dashboard.
- Per-agent settings (files, network, shell) → generates sandbox profiles.
- Installer that writes hook configs for Claude Code, Codex, OpenCode.

# Integration with the engine

Hackathon: the app talks to the Python engine sidecar (decision log / socket). Product: port the engine to Swift
(MLX Swift for the model) inside the app. Reference UI project: iainnash/flowgate (MIT, SwiftUI approval cards).
