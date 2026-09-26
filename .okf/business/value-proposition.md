---
type: Positioning
title: Value proposition and pitch
description: What Senti promises, the differentiators that the big agent vendors will not build, and the one-line pitch.
tags: [business, positioning, pitch]
status: draft
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
stale_after: 2026-12-31
sources:
  - id: session
    resource: claude-code session 973dd678-f568-4b80-aeca-b6d8963be82d (2026-09-26)
    title: Ideathon planning session
---

# One-liners

- **Consumer/MVP:** "Senti is the neutral safety layer for every AI agent on your Mac — one policy, one log, fully local."
- **Enterprise (concept draft):** "IAM and antivirus for AI agents, running entirely on the company's own infrastructure."
- **Versus rule-only tools:** "HOL Guard is antivirus with fixed signatures; Senti is a security guard who understands what the agent is trying to do and explains it in plain words."[^session]

# Differentiators (where Senti should compete)

| Differentiator | Why it matters | Who else has it |
|---|---|---|
| **Vendor-neutral**: one policy + one activity log across Claude Code, Codex, OpenCode, ... | Anthropic will not protect Codex; OpenAI will not protect Claude. Neutrality is the moat. | HOL Guard (rules only) |
| **Task-aware judgment** (local LLM sees the user's task) | Catches "fix CSS" → reads billing config; rules cannot | nobody found |
| **Reads scripts before they run** | Catches `python3 run_tests.py` that exfiltrates secrets | HOL Guard reads shell scripts only, not `.py` |
| **100% local / on-prem**, including the judge model | Privacy; nothing about the user's activity leaves the machine/company | — |
| **Plain-language explanations** for non-technical users | Users can make informed allow/block choices | Unalome (observability, after the fact) |
| **Native macOS app** | Open-source competitors ship CLI + browser dashboards only | HOL Guard Desktop is closed/separate |

# Candidate differentiating features (not built yet)

Undo/"time machine" before destructive actions, honeytokens, secret brokering, task-scope contracts —
see [Roadmap](/roadmap/roadmap.md).

# Honest risks to address in the pitch

See [Risks](/business/risks.md): platform vendors absorbing the feature, open-source competition, willingness to pay.

[^session]: Ideathon planning session
