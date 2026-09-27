---
type: Open Questions
title: Open questions
description: Decisions still pending from the team, from the planning session and the concept draft.
tags: [roadmap, questions]
status: draft
stale_after: 2026-10-31
generated: { by: claude-code/2.1.283, at: '2026-09-27T02:00:00Z' }
sources:
  - id: session
    resource: claude-code session 973dd678-f568-4b80-aeca-b6d8963be82d (2026-09-26)
    title: Questions asked to the team and not yet answered
  - id: concept-draft
    resource: AI_Agent_Guardrails_Concept_Draft.docx (concept draft v0.1)
    title: Concept draft — open questions section
    author: human:vargevorgyan
---

# Answered (2026-09-27)

- Install Codex CLI / OpenCode and run test sessions — **yes**, done (see [Real-agent tests](/research/real-agent-tests.md)).
- Wow features — undo, honeytokens, injection warnings, supply chain and task scope are all implemented ([Roadmap](/roadmap/roadmap.md)).
- Org backend location — **Docker Compose**, same laptop for the demo; any Docker host for real use.
- Admin panel stack — **React (Vite) behind nginx**, backend FastAPI ([ADR-010](/decisions/adr-010-no-client-ui-fastapi-react.md)).
- Corporate model in the demo — **Ollama container** with `qwen2.5:3b` (configurable to any OpenAI-compatible endpoint in the admin panel).
- Client UI — **none**; hooks + engine only ([ADR-010](/decisions/adr-010-no-client-ui-fastapi-react.md)).

# Still open

- Real logo SVGs from the designer (artifact blobs are not downloadable; admin uses a placeholder icon).
- Make `senti run` (sandbox) automatic for agents when a profile sets `features.sandbox`.
- Codex hook trust for managed rollouts (`requirements.toml` managed hooks skip trust).
- Clean up ~7 GB of test models on the original dev Mac.

# From the concept draft[^concept-draft]

- First customer segment (company size, industry, regulatory pressure)?
- Deployment: single appliance, Kubernetes chart, or both?
- Pricing: per seat, per agent, or per protected service?
- Personal and unmanaged devices?
- Relationship with HOL Guard: dependency, fork, or partnership?

[^concept-draft]: Concept draft — open questions section
