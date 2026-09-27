---
type: Benchmark
title: Company AI filter — live measurements
description: Measurements of employees' Macs using the organization's cloud AI filter through the hook, with no local model, plus the typosquat fix it surfaced.
tags: [research, benchmark, judge, enterprise]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-27T15:00:00Z' }
stale_after: 2027-03-31
sources:
  - id: runs
    resource: /scripts/simulate.py, /scripts/judge_holdout.py
    title: Replays through the real hook on an enrolled test Mac; company AI = Qwen3-4B (mlx_lm server) behind the Docker backend
---

# Setup
Docker stack installed with `./senti-server`; the corporate model pointed at a stand-in "company cloud" model (Qwen3-4B on
this M1 8 GB via an OpenAI-compatible server); a test Mac enrolled with `senti setup`, Developer profile.[^runs]

# Results
| Measure | Result |
|---|---|
| Senti process on the Mac | **97 MB**, no model loaded (local judge: ~3.1–3.4 GB) |
| Held-out: routine scripts allowed | **12/12** (company AI, ~2.6–6.3 s each on the stand-in model) |
| Held-out: attacks | **8/8 blocked on the Mac** by detectors in ~15 ms, no cloud needed |
| 73-action simulation: dangerous stopped | **22/22** |
| Decided on the Mac / sent to the company AI | **64/73 (median 10 ms)** / 9 (median 3.2 s) |
| Exact vs. labels | 63/73 — 5 are stricter on purpose (Developer profile forbids `sudo`, `.env`, `rm -rf ~*`), 3 routine scripts asked (see below), 1 miss (typosquat, fixed) |

# Found and fixed
`npm install reqeusts-http-lib` was allowed: the typosquat check counted a swapped pair of letters as 2 edits, only compared
npm names and not the name's leading part. Now: swaps count as 1 edit, the leading part is checked unless it is itself a
known package, npm and PyPI names are compared with each other (not unrelated ecosystems), and legitimate look-alikes
(`preact`, `nuxt`, `vuex`, `serve-static`, …) are listed. On 226 real package names: **0 false alarms**; 11/12 test
misspellings flagged, the 12th (`reqeusts` on PyPI) is on the known-malicious list and blocked.

# Open
The seeded Developer note ("production databases need approval…") made the stand-in model ask about 3 routine scripts. It
was reworded to say local/test/seed databases and public APIs are normal work; a re-measurement failed because the stand-in
model server timed out (every call → ask, i.e. failed safe), so **the effect of the new wording is not measured yet**.
Latency depends on the company's model hardware; 3 s per unclear action is the 8 GB laptop stand-in, not a GPU server.

[^runs]: Replays through the real hook on an enrolled test Mac; company AI = Qwen3-4B (mlx_lm server) behind the Docker backend
