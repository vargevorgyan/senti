---
type: Plan
title: Hackathon demo plan
description: The proposed three-minute demo, build split and remaining work for the ideathon.
tags: [roadmap, demo, hackathon]
status: draft
stale_after: 2026-10-31
generated: { by: claude-code/2.1.283, at: '2026-09-27T02:00:00Z' }
sources:
  - id: session
    resource: claude-code session 973dd678-f568-4b80-aeca-b6d8963be82d (2026-09-26)
    title: Demo planning discussion
---

# Setup (5 minutes)

```bash
docker compose up -d --build                      # admin http://localhost:8080 (admin@senti.local / senti-admin)
cd engine && uv sync --extra mlx && uv run senti start
uv run senti enroll --backend http://localhost:8000 --code SENTI-DEMO --email you@acme.test && uv run senti stop && uv run senti start
../demo/make-demo-repo.sh /tmp/senti-demo && uv run senti install all --project /tmp/senti-demo
```

# Demo script (~3 min)

1. **One poisoned repo** for all agents (`/tmp/senti-demo`): README secretly tells agents to upload `.env`.
2. **Claude Code** does real work (tests) — Senti invisible; README read → Senti warns the agent; `python3 helper.py` → **blocked**.
3. **Codex (ChatGPT)** — same repo, same block: "we don't care which company made the agent".
4. **OpenCode on a local model** (Ollama) — same block, fully offline.
5. **Admin panel**: Overview sentence and live feed update as it happens; switch the Developer profile's judge to *Corporate* or tick
   "No network except allowed sites" for OpenCode → the next action on the Mac obeys it (~0.2 s).
6. **Approvals**: set "Who answers ask" to the owner, trigger `git push --force` → approve it in the panel → the agent continues.
7. **Undo**: an agent deletes a file → `senti undo list` / `restore`. **Honeytoken**: `senti honeytoken plant /tmp/senti-demo` → any agent touching it is stopped.
8. **Activity**: every decision, the layer that decided, latency; CSV export.

# Build split

Done by the full build (2026-09-27): engine, Codex adapter, OpenCode plugin, poisoned repo, npm/Makefile/import resolution,
personal-folder detector, FastAPI backend, React admin panel. See [Code guide](/code-guide.md).
