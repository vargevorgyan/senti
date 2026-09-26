---
type: Plan
title: Hackathon demo plan
description: The proposed three-minute demo, build split and remaining work for the ideathon.
tags: [roadmap, demo, hackathon]
status: draft
stale_after: 2026-10-31
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
sources:
  - id: session
    resource: claude-code session 973dd678-f568-4b80-aeca-b6d8963be82d (2026-09-26)
    title: Demo planning discussion
---

# Demo script (~3 min)

1. **One poisoned repo** for all agents: README secretly tells the agent to upload `.env`.
2. **Claude Code** does real work (tests, edits, git) — Senti invisible (~3 ms/action); hits the trap → **blocked**, plain-English popup.
3. **Codex (ChatGPT)** — same repo, same block: "we don't care which company made the agent".
4. **OpenCode on a local model** — same block, fully offline.
5. **Disguised script** `helper.py` (builds the SSH-key path from pieces) — blocked by the write-time pre-check; show the sandbox's "Operation not permitted" as last line.
6. **Admin panel moment** (if the org backend is built): switch a profile's judge to corporate or add "no network for OpenCode" → next action obeys.
7. **Activity log**: every decision, layer, latency.
Optional wow features: **Undo** and **honeytokens** (see [Roadmap](/roadmap/roadmap.md)).

# Build split

| Who | Work |
|---|---|
| Claude Code / engine owner | Codex adapter (`apply_patch` mapping), OpenCode plugin, poisoned demo repo, npm/Makefile/import resolution, personal-folder-deletion detector |
| Teammate(s) | SwiftUI menu-bar app + popup reading the engine's socket/decision log |
| Backend owner | FastAPI + SQLite org backend + one-page admin panel ([design](/architecture/org-backend-and-profiles.md)) |

# Pending permissions / installs

Codex CLI (`npm i -g @openai/codex`, uses ChatGPT plan), OpenCode, possibly Ollama. See [Open questions](/roadmap/open-questions.md).
