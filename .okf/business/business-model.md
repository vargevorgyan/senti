---
type: Business Model
title: Target customers and business model
description: Two candidate go-to-market directions (individual Mac app vs. company on-prem control plane) and the current recommendation.
tags: [business, go-to-market, pricing]
status: draft
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
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
| Product | Native macOS menu-bar app, local judge | Endpoint client + on-prem policy server + admin panel + LLM gateway |
| Buyer | Individual developers, power users | Security / IT teams |
| Willingness to pay | Low (individuals rarely pay for security) | High (compliance, data-leak risk) |
| Policy source | Local settings | Role profiles synced from the identity provider (Okta, Entra ID, Google Workspace) |
| Judge | Local Qwen3-4B | Local, corporate model, or local-then-corporate escalation |

# Current recommendation

Build the **Mac app (A) for the hackathon demo** and pitch **B as the business**: the same engine runs on
each Mac, and the organization adds the backend, profiles, corporate judge and audit.[^session]
The concept draft proposes starting each role in **observe-only mode** for 1–2 weeks before enforcing.[^concept-draft]

# Pricing ideas (open)

Per seat, per agent, or per protected service — undecided. See [Open questions](/roadmap/open-questions.md).

# Pilot success metrics (from concept draft)

Share of actions decided automatically; approval prompts per user per day; false-positive rate;
risky actions blocked; 95th-percentile added latency.[^concept-draft]

[^session]: Ideathon planning session
[^concept-draft]: Role-Based Guardrails for AI Agents — concept draft v0.1
