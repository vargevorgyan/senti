---
type: Risk Register
title: Business and technical risks
description: Main risks for Senti with mitigations, combining the concept draft's risk table and findings from prototyping.
tags: [business, risks, security]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
sources:
  - id: session
    resource: claude-code session 973dd678-f568-4b80-aeca-b6d8963be82d (2026-09-26)
    title: Ideathon planning session
  - id: concept-draft
    resource: AI_Agent_Guardrails_Concept_Draft.docx (concept draft v0.1)
    title: Role-Based Guardrails for AI Agents — concept draft v0.1
    author: human:vargevorgyan
---

| Risk | Mitigation |
|---|---|
| Agent vendors build equivalent guardrails into their own agents | Be vendor-neutral: one policy/log across all agents; task-aware judgment; on-prem |
| Direct open-source competition (HOL Guard, free, many agents) | Differentiate on LLM judgment, script reading, plain language, native app, org profiles |
| Individuals will not pay | Enterprise direction (org backend, profiles, audit) |
| Hooks are advisory — code inside a running script is invisible | [Sandbox](/architecture/enforcement-sandbox.md) as OS-level backstop; read scripts pre-execution |
| Guard LLM manipulated by injected text | Hard rules the LLM cannot override; `<untrusted>` wrapping; metadata-only inputs where possible; fail closed[^concept-draft] |
| Added latency annoys users | Cascade (≈75% decided by rules in ~3 ms), caching, prefix cache, logit verdict, write-time pre-check — see [End-to-end simulation](/research/end-to-end-simulation.md) |
| Memory: local 4B judge uses ~3.1–3.4 GB (tight on 8 GB Macs) | Unload after idle; share one model with local agents; corporate judge |
| False positives → prompt fatigue | Observe mode first; tune prompt; "always allow for this project" becomes a rule |
| Employee privacy (GDPR, works councils) in org version | Log actions and decisions, not full content; retention limits; transparency[^concept-draft] |
| Backend outage | Cached signed profiles + local rules + local judge; strict local mode |
| Agent disables Senti (edits hook config) | Hard rule blocks writes to `~/.claude/settings*.json`, `.cursor/hooks.json`, Senti's own files; MDM-managed settings in org version |

[^concept-draft]: Role-Based Guardrails for AI Agents — concept draft v0.1
