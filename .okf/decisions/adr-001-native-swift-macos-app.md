---
type: Decision
title: "ADR-001: Native Swift macOS app for the MVP"
description: "The MVP is a native SwiftUI menu-bar app with an in-process or sidecar engine, chosen by the team over Tauri, Electron and SwiftUI+Python."
tags: [decision, macos, stack]
status: superseded
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
sources:
  - id: session
    resource: claude-code session 973dd678-f568-4b80-aeca-b6d8963be82d (2026-09-26)
    title: Ideathon planning session
    author: human:vargevorgyan
---

> **Superseded by [ADR-010](/decisions/adr-010-no-client-ui-fastapi-react.md) (2026-09-27):** there is no client UI app; the Mac side is hooks + a FastAPI engine.

# Context
The team said the MVP is a macOS app. Options: native Swift; Tauri + React (Rust not installed); Electron + TS; SwiftUI + Python engine.

# Decision
**Native Swift / SwiftUI** (team choice). Positioned as "Little Snitch for AI agents".

# Consequences
- Native popups, menu bar, notifications; one language long-term.
- Hackathon pragmatism: the Python engine prototype runs as a sidecar; port to Swift (MLX Swift) later.
- The hook client is compiled Swift regardless (3 ms vs 19 ms in Python).
