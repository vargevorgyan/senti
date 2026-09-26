# Update Log

## 2026-09-27
* **Update**: `network.ask` profile rules + DB-client host extraction; judge prompts make org policy binding after the corporate 3B model allowed a prod-DB query — [Org backend](/architecture/org-backend-and-profiles.md). Sandbox per agent verified — [Sandbox](/architecture/enforcement-sandbox.md).
* **Decision**: No client UI app; FastAPI engine/backend and React admin panel in Docker — [ADR-010](/decisions/adr-010-no-client-ui-fastapi-react.md) supersedes ADR-001.
* **Creation**: Full build documented — [Code guide](/code-guide.md), [Admin panel](/architecture/admin-panel.md), [Real-agent tests](/research/real-agent-tests.md).
* **Update**: Architecture concepts rewritten for the implemented system — [System overview](/architecture/system-overview.md), [Hook client](/architecture/hook-client.md), [Decision engine](/architecture/decision-engine.md), [LLM judge](/architecture/llm-judge.md), [Org backend](/architecture/org-backend-and-profiles.md), [Script inspection](/architecture/script-inspection.md), [Sandbox](/architecture/enforcement-sandbox.md).
* **Update**: Codex CLI and OpenCode integrations verified live (formats, ask handling, fail-open caveat) — [Codex CLI](/integrations/codex-cli.md), [OpenCode](/integrations/opencode.md), [Agent coverage](/integrations/agent-coverage.md).
* **Update**: Roadmap implementation status, answered open questions, runnable demo plan, second dev Mac — [Roadmap](/roadmap/roadmap.md), [Open questions](/roadmap/open-questions.md), [Demo plan](/roadmap/hackathon-demo-plan.md), [Development environment](/dev-environment.md), [Start here](/getting-started.md).

## 2026-09-26
* **Creation**: Gap-fill after a completeness review — [Concept draft summary](/business/concept-draft-summary.md), [Development environment](/dev-environment.md), [Local models](/integrations/local-models.md); added sub-agents, Apple entitlement limits, safe-testing practice and tamper-resistant log notes.
* **Update**: Team removed the MCP gateway and judge fine-tuning from the roadmap; Qwen3-4B without training stays the judge — [Roadmap](/roadmap/roadmap.md), [LLM judge](/architecture/llm-judge.md).
* **Creation**: Initial knowledge base distilled from the ideathon planning and prototyping session and the team's concept draft v0.1 — [Start here](/getting-started.md).
* **Creation**: Business section (problem, positioning, business model, competitors, risks) — [Business](/business/).
* **Creation**: Architecture section (system overview, hook client, decision engine, LLM judge, script inspection, sandbox, org backend and profiles, macOS app) — [Architecture](/architecture/).
* **Creation**: Integrations for Claude Code (tested), Codex CLI and OpenCode (planned) — [Integrations](/integrations/).
* **Creation**: Research results (judge benchmark, end-to-end simulation, HOL Guard analysis, Laya evaluation, sandbox test) backed by code and JSON results in `prototype/` — [Research](/research/).
* **Creation**: Decision records ADR-001 to ADR-009 — [Decisions](/decisions/).
* **Creation**: Demo plan, roadmap and open questions — [Roadmap](/roadmap/).
