---
type: Capability
title: Script inspection before execution
description: What Senti can read before an agent runs code (scripts, written files, inline code) and the known gaps (npm scripts, imports, downloaded code, binaries).
tags: [architecture, scripts, detection]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
sources:
  - id: session
    resource: claude-code session 973dd678-f568-4b80-aeca-b6d8963be82d (2026-09-26)
    title: Discussion of script reading and its limits
---

# Overview

The hook fires **before** execution and the Senti agent runs as the user, so it can open any file the agent is
about to run. The engine parses the command (`python3 x.py`, `node x.js`, `bash x.sh`, `./x.sh`), resolves the path
against the agent's cwd, reads up to ~20 KB, hashes it, runs detectors and the judge, and caches the verdict by
content hash (any byte change → re-check). Files written by the agent are checked **at write time** from the hook
payload, before they exist on disk. This is independent of the agent vendor.

# Coverage

| Case | Readable? | Prototype | Needed |
|---|---|---|---|
| `python x.py`, `node x.js`, `bash x.sh`, `./x.sh` | yes | done | — |
| Script written by the agent in this session | yes, at write time | done | — |
| `python -c "…"`, `node -e "…"` | yes (in the command) | partial | send inline code to the judge as a script |
| `npm test`, `npm run build` | indirect (`package.json` → `scripts`) | no | resolve package.json scripts |
| `make`, `pytest`, `python -m pkg` | indirect | no | per-tool resolvers |
| Script importing a local module with the bad code | if imports are followed | no | follow local imports 1–2 levels |
| Code downloaded at runtime (`exec(requests.get(u).text)`, `curl … \| python`) | no | pattern rules | block pattern + sandbox |
| Compiled binaries | not meaningfully | — | unknown binary → ask + sandbox |
| Runtime string building / `eval` | partially (LLM caught `'ss'+'h'`) | via LLM | sandbox backstop |
| File changed between check and run | rare | hash recorded | re-check hash + sandbox |

# Also watch

Edits to "run later" files: `package.json` scripts, `Makefile`, git hooks, CI configs.

# Privacy

Whether file contents may be sent to a corporate judge is a per-profile setting
(`send_to_corporate: metadata_only | with_redacted_content | full`).
