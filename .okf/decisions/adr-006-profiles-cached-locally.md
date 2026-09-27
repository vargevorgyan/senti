---
type: Decision
title: "ADR-006: Profiles cached locally, pushed from the backend"
description: "Hooks never call the organization backend per action; the local Senti agent holds signed, cached profiles pushed on change, and routes grey-zone decisions to a local or corporate judge per profile."
tags: [decision, backend, profiles, enterprise]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
sources:
  - id: session
    resource: claude-code session 973dd678-f568-4b80-aeca-b6d8963be82d (2026-09-26)
    title: Ideathon planning session
    author: human:vargevorgyan
---

# Context
Team requirement: hook → profile from backend → local or corporate LLM. Per-action backend calls would add latency and break during outages.

# Decision
Local Senti agent caches signed profiles (SSE/WebSocket push). Judge router per profile: `local | corporate | local_then_corporate | none`.
Hard rules always local; backend unreachable → strict local mode.

# Consequences
Near-zero added latency for rule decisions; admin changes apply within seconds; corporate model sees metadata only by default (changed by [ADR-012](/decisions/adr-012-company-cloud-ai-filter.md): scripts are now sent with secrets redacted).
See [Org backend and profiles](/architecture/org-backend-and-profiles.md).
