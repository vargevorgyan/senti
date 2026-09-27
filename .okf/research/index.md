# Research and benchmarks

* [Judge model benchmark](judge-model-benchmark.md) - Accuracy, latency and memory of Laya and Qwen models as Senti's action judge on 43 labelled agent actions, on an M1 with 8 GB RAM.
* [End-to-end cascade simulation](end-to-end-simulation.md) - Results of replaying four realistic agent sessions through the real Swift hook and the full cascade, before and after optimizations.
* [HOL Guard analysis](hol-guard-analysis.md) - What HOL Guard is, its architecture, what it does not do (no LLM, no .py script reading), and what Senti can reuse under Apache-2.0.
* [Laya evaluation (rejected as judge)](laya-evaluation.md) - Why the Laya zero-shot decision model was rejected for command and access limiting after testing on an M1.
* [sandbox-runtime test](sandbox-runtime-test.md) - Test of Anthropic's sandbox-runtime (srt) against an exfiltration script using fake secrets.
* [Related repositories and links](related-repos.md) - Links to every external project referenced during Senti's planning, grouped by how they relate to Senti.
* [Real-agent tests of the full build](real-agent-tests.md) - Live sessions of Claude Code, Codex CLI and OpenCode against the poisoned demo repo through the full-build engine, plus the automated judge-mode end-to-end run.
* [Script detector hardening and judge prompt experiment](detector-hardening-2026-09-27.md) - New flow-aware L2 detectors for script content, the measured effect on a held-out set, and a judge prompt change that was measured, regressed and reverted.
* [Security review of the full build](security-review-2026-09-27.md) - Read-only adversarial review of the engine, rules, profiles and backend; 20 findings, the fixes applied and what remains open.
* [Real AI-agent incidents replayed through Senti](agent-incidents.md) - 19 publicly documented incidents (2025–2026) where coding agents deleted home folders, wiped production, leaked secrets or obeyed injected text; every harmful action replayed through Senti — 38/38 stopped or flagged by rules alone.
