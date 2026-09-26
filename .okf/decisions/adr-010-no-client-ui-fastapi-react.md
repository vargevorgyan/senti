---
type: Decision
title: "ADR-010: No client UI app; FastAPI engine and backend, React admin panel"
description: "The Mac side is only hooks/plugins plus a host-native FastAPI engine on a Unix socket; the organization side is a FastAPI backend and a React admin panel in Docker. Supersedes ADR-001."
tags: [decision, architecture, stack, ui]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-27T01:40:00Z' }
sources:
  - id: owner
    resource: claude-code session 8fd63895-c55e-48ec-ab07-6bef962bedbe (2026-09-27)
    title: Repo owner's build instructions for the full implementation
    author: human:gagik
---

# Context

ADR-001 planned a native SwiftUI menu-bar app. For the full build the repo owner decided that the client side has **no UI
application at all** — only the hook and the local engine — and that backend code is Python **FastAPI** and any web UI is
**React**. Everything that can run in Docker should, so the organization side is quick to deploy; local components
(the MLX judge, hooks, the Unix socket) stay native on the Mac.[^owner]

# Decision

- **Mac:** `senti-hook` (compiled Swift) and the OpenCode plugin → **Senti engine** (Python package `senti`, FastAPI served by
  uvicorn on a `0600` Unix socket) → local MLX judge. Started with `senti start` or a LaunchAgent (`senti service install`).
- **"ask" without an app:** Claude Code shows its own permission prompt. Codex CLI and OpenCode have no hook-level ask, so the
  engine shows a native macOS dialog (`osascript`) with Block / Allow once / Always allow; timeout or no GUI → block.
- **Organization (Docker Compose):** FastAPI + SQLite backend, React (Vite) admin panel behind nginx, and an Ollama container
  that plays the corporate model (`qwen2.5:3b` by default, CPU; fits a 16 GB laptop).
- The designer's approval-prompt component is used in the admin panel's **Approvals** page (profile `ask_goes_to: owner|admin`).

# Consequences

- No Xcode app to build or sign; the product surface is the agents' own prompts, macOS notifications and the admin panel.
- The engine stays in Python (GIL contention measured in [End-to-end simulation](/research/end-to-end-simulation.md) remains a known cost).
- ADR-001 is superseded; [macOS app](/architecture/macos-app.md) is kept only as history.

[^owner]: Repo owner's build instructions for the full implementation
