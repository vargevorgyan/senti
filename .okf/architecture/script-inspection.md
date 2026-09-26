---
type: Capability
title: Script inspection before execution
description: What Senti can read before an agent runs code (scripts, written files, inline code) and the known gaps (npm scripts, imports, downloaded code, binaries).
tags: [architecture, scripts, detection]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-27T02:00:00Z' }
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

| Case | Readable? | Full build | Remaining |
|---|---|---|---|
| `python x.py`, `node x.js`, `bash x.sh`, `./x.sh` | yes | done | — |
| Script written by the agent in this session | yes, at write time | done (write-time scan + LLM prefetch; malicious content blocked at write) | — |
| `python -c "…"`, `node -e "…"` | yes (in the command) | done (sent to detectors and judge as a script) | — |
| `npm test`, `npm run build`, `npm install` hooks | indirect | done (`package.json` scripts incl. pre/post and install hooks resolved and checked) | — |
| `make target` | indirect | done (Makefile recipe lines) | `pytest` plugins, `python -m pkg` |
| Script importing a local module with the bad code | if imports are followed | done (Python/JS/shell local imports, 2 levels, up to 8 files) | deeper graphs |
| Code downloaded at runtime | no | hard-deny patterns + obfuscation ask | sandbox backstop |
| Compiled binaries | not meaningfully | unknown program → judge | sandbox |
| Runtime string building / `eval` | partially | LLM + reviewer-injection detector | sandbox |
| File changed between check and run | rare | decision cache keyed by content | sandbox |

# Also watch

Edits to "run later" files: `package.json` scripts, `Makefile`, git hooks, CI configs.

# Privacy

Whether file contents may be sent to a corporate judge is a per-profile setting
(`send_to_corporate: metadata_only | with_redacted_content | full`).
