---
type: Open Questions
title: Open questions
description: Decisions still pending from the team, from the planning session and the concept draft.
tags: [roadmap, questions]
status: draft
stale_after: 2026-10-31
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
sources:
  - id: session
    resource: claude-code session 973dd678-f568-4b80-aeca-b6d8963be82d (2026-09-26)
    title: Questions asked to the team and not yet answered
  - id: concept-draft
    resource: AI_Agent_Guardrails_Concept_Draft.docx (concept draft v0.1)
    title: Concept draft — open questions section
    author: human:vargevorgyan
---

# From the planning session (awaiting team answers)

- Permission to install **Codex CLI** and **OpenCode** globally and run test sessions (Codex uses the ChatGPT plan).
- Which wow features for the demo — suggested: **Undo + honeytokens**.
- Org backend for the demo: **same Mac or a small cloud VM**?
- Admin panel stack: **React served by FastAPI** or **Next.js**?
- What plays the **corporate model** in the demo: local Qwen as a server, or a cloud model via an OpenAI-compatible API?
- Commit/push the knowledge base and prototype to the repo (done locally, not pushed as of 2026-09-26).
- Clean up ~7 GB of downloaded test models in `~/.cache/huggingface` (disk was 91% full).

# From the concept draft[^concept-draft]

- First customer segment (company size, industry, regulatory pressure)?
- Deployment: single appliance, Kubernetes chart, or both?
- Recommended local model and hardware baseline? (Current answer: Qwen3-4B, ≥16 GB RAM comfortable, 8 GB tight.)
- Pricing: per seat, per agent, or per protected service?
- Personal and unmanaged devices?
- Relationship with HOL Guard: dependency, fork, or partnership?

[^concept-draft]: Concept draft — open questions section
