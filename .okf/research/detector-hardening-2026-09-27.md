---
type: Experiment
title: Script detector hardening and judge prompt experiment
description: New flow-aware L2 detectors for script content, the measured effect on a held-out set, and a judge prompt change that was measured, regressed and reverted.
tags: [research, detectors, judge, security, benchmark]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-27T08:00:00Z' }
stale_after: 2027-03-31
sources:
  - id: holdout
    resource: /scripts/judge_holdout.py
    title: Held-out set — 12 routine scripts and 8 attacks that are not in the prototype sessions
  - id: sim
    resource: /scripts/simulate.py
    title: Labelled simulation (73 actions from the prototype sessions)
  - id: tests
    resource: /engine/tests/test_script_detectors.py
    title: Detector regression tests (false positives and bypasses from the code review)
---

# What changed

New L2 detectors in `engine/src/senti/rules.py` (`scan_code`) that follow **where data flows**, not just which words appear:[^tests]

| Detector | Blocks when | Rule id |
|---|---|---|
| Environment exfiltration | the whole environment (`dict(os.environ)`, `str(os.environ)`, `{**os.environ}`, `process.env` spread, `env \| curl`) reaches a network call — same line or through a variable | `script_env_exfil` |
| Backdoor key | something is **written** to `~/.ssh/authorized_keys` (open w/a/x incl. binary, `>`/`>>`, `tee`, copy/move, via a variable, `ssh-copy-id`); reading it is fine | `script_backdoor` |
| Download and run | a file fetched from the network (urlretrieve, curl `-o`/combined flags, wget `-O`, bytes written after `requests.get`) is later chmod-ed or executed | `script_download_exec` |
| Personal folders upload | an archive of Documents/Desktop/Pictures/… (home in a variable is fine) plus network | `script_personal_exfil` |
| Persistence (ask) | a write to a file from `PERSISTENCE_PATTERNS` (shell start-up, LaunchAgents, `.git/hooks`, `/etc`, …) or crontab | `script_persistence` |

Also: `.env.example`/`.sample`/`.template` are no longer "secret files"; `process.env`/`import.meta.env` no longer count as `.env`
(named files like `prod.env` still do); DNS lookups (`gethostbyname`, `dig`/`nslookup` in command position or called from code)
count as network.

# Results (M1, 8 GB, local judge Qwen3-4B)

| Set | Before | After |
|---|---|---|
| Held-out routine scripts allowed | 11/12 | **12/12** |
| Held-out attacks **hard-blocked** (not just "ask") | 3/8 | **8/8** |
| Held-out attacks allowed | 0 | 0 |
| Labelled simulation (73) exact / dangerous stopped / safe interrupted | 69/73 · 22/22 · 2 | 69/73 · 22/22 · 2 (no regression) |
| New detectors firing on 4,970 real library files | — | 0 |
| `scan_code` time, 20 KB file / 2 KB script | 2.6 ms | 3.7 ms / 0.65 ms |

[^holdout][^sim]

# Judge prompt experiment — reverted

Adding "normal work is allow" guidance plus five worked examples to the judge prompt **regressed** the simulation: exact 69 → 64,
a typosquatted `npm install reqeusts-http-lib` became a **silent allow**, one more routine script was interrupted. Adding
`sends_data`/`hosts` facts with the original prompt had **no measurable effect**. Both were reverted; the prompt is unchanged.
The two over-cautious cases (`seed_db.py`, `check_links.py`) remain open — do not retry broad "allow" guidance.

# Other fixes from the same review

- `senti stop` now waits for the engine to exit and verifies the pid really is the Senti engine (a stale pid file could make it
  signal an unrelated process); the server only removes the socket file if it is still its own. Before: 1 in 3 immediate
  `stop`+`start` left Senti unreachable (every agent action then fails closed); after: 6/6 restarts healthy.
- `scripts/_hook.py`: replay scripts fail loudly (exit 2) when the engine is down or the hook binary is missing, instead of
  counting fail-closed "ask" as a perfect score.
- The backend's copy of the judge prompt is guarded by a test that fails if it drifts from the engine's.

# Follow-ups

- Pre-existing `HARD_DENY_CMD` curl/wget patterns are quadratic on adversarial one-line input (~120 ms at the 20 KB cap).
- Over-cautious judge on the two scripts above.

[^holdout]: Held-out set — 12 routine scripts and 8 attacks that are not in the prototype sessions
[^sim]: Labelled simulation (73 actions from the prototype sessions)
[^tests]: Detector regression tests (false positives and bypasses from the code review)
