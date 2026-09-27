---
type: Experiment
title: Security review of the full build (2026-09-27)
description: Read-only adversarial review of the engine, rules, profiles and backend; 20 findings, the fixes applied and what remains open.
tags: [research, security, review, rules]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-27T03:10:00Z' }
sources:
  - id: review
    resource: claude-code session 8fd63895-c55e-48ec-ab07-6bef962bedbe (review sub-agent report)
    title: Security review sub-agent report
    author: claude-code/2.1.283
  - id: tests
    resource: /engine/tests/test_review_fixes.py, /backend/tests/test_api.py
    title: Regression tests for every confirmed bypass
---

# Summary

A review sub-agent ran every rule directly and found actions the **rules alone allowed** without reaching the judge.
All high findings and most medium ones are fixed and pinned by regression tests (`engine/tests/test_review_fixes.py`).[^review][^tests]

# Fixed

| Finding | Fix |
|---|---|
| `awk 'BEGIN{system(...)}'`, `sed -i`/`e` allowed | awk/sed are only safe without `system/getline/pipes/redirects` or in-place/`e`/`w` |
| Runners (`uv run`, `npm exec`, `npx`, `go run`, `pytest -p`, `python -m pip.__main__`) ran anything | inner command re-checked recursively; executed packages go through the supply-chain check; exact module match |
| `git clone https://evil…` safe, hosts invisible to profiles | git network subcommands extract hosts → profile network rules, taint, judge |
| `git config core.fsmonitor …`, writes to `.git/config` | dangerous git keys (`-c` too) → ask; `.git/config`, `.envrc`, `.vscode/tasks.json`, `.mcp.json`, … are run-later files (scanned, ask) |
| Symlinks to `~/.ssh` / hook configs read as project files | classification uses the symlink target too (stricter wins); "inside the project" requires the real path inside |
| `curl http://localhost … evil.com`, secrets to localhost tunnels | every destination argument is parsed; secrets or uploads are never excused for localhost |
| `open`, `source`, `.` on the safe list | removed; `source` scripts are read and scanned |
| Globs hiding secrets (`cat .en?`, `rm -rf ~/*`, Grep `glob: .env`) | globs expanded before classification; Grep over secret-file globs → ask |
| Device token readable (`~/.senti/config.json`) | anything under `~/.senti` is unreadable (tools and shell) |
| Engine socket usable by agents | per-install `hook.token` required on every request (hook, CLI and scripts send it); `--unix-socket` to guard paths blocked |
| Agent overrides could loosen (empty allow intersection, scalars) | empty intersection allows nothing; `outside_allow`, `write`, `packages`, `ask_goes_to` take the stricter value; protections can only be switched on |
| Shell deny evaded (`command git push`, `git -C . push`, `/usr/bin/git`, `rm -rf` without `*`) | patterns matched per normalised segment (wrappers and git globals removed), prefix match without `*` |
| Prefetch verdict reused with extra script arguments | prefetch only for a bare `runner script`; personal-folder arguments → ask |
| Judge cache ignored cwd/project | cache key includes agent, cwd, project and bundle version |
| Bundles not bound to the device / rollback | `device_id` checked, older versions refused; enrolled Mac without a valid cache uses a strict profile |
| `pkill -f Senti`, `killall senti` | case-insensitive hard deny |
| Backend: spoofed `user`/`verdict` in events | user always from the device token; verdict whitelisted |
| Backend: JWT in query on every admin endpoint | only accepted for `/admin/stream` |
| Backend: enrolling as an existing user with another role's code | refused (403) |
| Default credentials exposed | ports bound to 127.0.0.1 by default (`SENTI_BIND`); admin panel warns while the default password is in use and can change it |

# Second review (/code-review, max effort)

A second pass found 15+ more issues, all fixed with tests in `engine/tests/test_review2.py` and `backend/tests/test_api.py`:
newline-separated commands treated as one safe command; profile allow patterns prefix-matching compound commands (now every
segment must match); unparsable shell syntax failing open (now ask); `.env` leaks via `grep -r`, `git show HEAD:.env`, brace globs;
org file denies not applied to shell reads; dot-file patterns (`.env*`) never matching; `dangerouslyDisableSandbox`; exec-capable
environment variables (`GIT_PAGER`, `DYLD_*`, `NODE_OPTIONS`, `GIT_CONFIG_*`…) and wrappers (`timeout`, `nice`); npm aliases, URL
specs and custom registries; curl `-F f=@file`/`-d@file`; value-less flags swallowing URLs; `git rebase -x`, `rg --pre`, `fd -x`,
`awk -f`; prefetch reuse across pipes/profiles; unreadable hook bodies; "Always allow" overriding profile asks; taint cleared by the
next prompt; override dropping judge privacy/instructions; enrollment hijack of existing accounts; user deletion no-op; malformed
events poisoning batches; engine `git status` running repo fsmonitor.

# Open

- `SAFE_DOMAINS` still includes `github.com` for `WebFetch` (attacker content can live there; injection scanning is the mitigation).
- Same-user processes can still read `hook.token` through uninspected means (peer verification now asks when the caller isn't the claimed agent).
- The judge sometimes over-blocks (e.g. `DROP TABLE` in a script → block instead of ask).

After both reviews: engine 161 tests, backend 22, Playwright 7, e2e 14/14, simulation 22/22 dangerous stopped (95–97% exact across runs).

[^review]: Security review sub-agent report
[^tests]: Regression tests for every confirmed bypass
