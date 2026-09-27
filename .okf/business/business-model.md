---
type: Business Model
title: Target customers and business model
description: Two candidate go-to-market directions (individual developers with the local hooks + engine vs. company on-prem control plane) and the current recommendation.
tags: [business, go-to-market, pricing]
status: draft
generated: { by: claude-code/2.1.283, at: '2026-09-27T12:00:00Z' }
stale_after: 2026-12-31
sources:
  - id: session
    resource: claude-code session 973dd678-f568-4b80-aeca-b6d8963be82d (2026-09-26)
    title: Ideathon planning session
  - id: concept-draft
    resource: AI_Agent_Guardrails_Concept_Draft.docx (concept draft v0.1)
    title: Role-Based Guardrails for AI Agents — concept draft v0.1
    author: human:vargevorgyan
---

# Directions

| | A. Individual / developer | B. Organization (concept draft) |
|---|---|---|
| Product | Hooks for the person's agents + local engine and judge (no UI app; the agents' own prompts ask) | The same hooks + engine on every Mac, plus the org backend, admin panel and corporate judge (Docker) |
| Buyer | Individual developers, power users | Security / IT teams |
| Willingness to pay | Low (individuals rarely pay for security) | High (compliance, data-leak risk) |
| Policy source | Local settings | Role profiles synced from the identity provider (Okta, Entra ID, Google Workspace) |
| Judge | Local Qwen3-4B | Local, corporate model, or local-then-corporate escalation |

# Current recommendation

Demo **A** (hooks + local engine, fully offline) and pitch **B as the business**: the same hooks and engine run on
each Mac, and the organization adds the backend, profiles, corporate judge and audit.[^session] Since
[ADR-010](/decisions/adr-010-no-client-ui-fastapi-react.md) there is no Mac UI app in either direction.
The concept draft proposes starting each role in **observe-only mode** for 1–2 weeks before enforcing.[^concept-draft]

# Pricing ideas (open)

Per seat, per agent, or per protected service — undecided. See [Open questions](/roadmap/open-questions.md).

# Pilot success metrics (from concept draft)

Share of actions decided automatically; approval prompts per user per day; false-positive rate;
risky actions blocked; 95th-percentile added latency.[^concept-draft]

[^session]: Ideathon planning session
[^concept-draft]: Role-Based Guardrails for AI Agents — concept draft v0.1
