# Architecture

* [System overview](system-overview.md) - The local parts of Senti (hooks, engine, sandbox) plus the organization side in Docker, and how a single agent action flows through them.
* [senti-hook (hook client)](hook-client.md) - Tiny compiled Swift binary that agents run before each action; forwards the hook JSON over HTTP on a Unix socket to the engine and fails closed per agent.
* [Decision engine (cascade)](decision-engine.md) - The layered decision pipeline — context, cache, rules, detectors, LLM judge — that turns an agent action into allow / ask / block.
* [LLM judge](llm-judge.md) - The local Qwen3-4B judge for grey-zone actions, its prompt contract, and the four speed optimizations that make it usable.
* [Script inspection before execution](script-inspection.md) - What Senti can read before an agent runs code (scripts, written files, inline code) and the known gaps (npm scripts, imports, downloaded code, binaries).
* [Enforcement sandbox (sandbox-runtime)](enforcement-sandbox.md) - OS-level file and network limits per agent using Anthropic's sandbox-runtime (macOS Seatbelt), the backstop for everything hooks cannot see.
* [Organization backend, profiles and judge routing](org-backend-and-profiles.md) - FastAPI backend and React admin panel (Docker) that define profiles per role/user/agent, push signed bundles to each Mac, route grey-zone decisions to a corporate model, collect audit and approvals.
* [Admin panel](admin-panel.md) - The React admin panel for organization administrators — overview, live activity, approvals, profile editor with judge modes, people and roles, devices and enrollment, corporate judge settings and playground, change log.
* [Secret brokering](secret-brokering.md) - Agents only see {{senti:NAME}} placeholders; values from the Keychain are injected at execution by a one-time wrapper, restricted to allowed hosts and masked in output.
* [Local model gateway (DIY agents)](model-gateway.md) - OpenAI-compatible proxy on 127.0.0.1:11435 in front of Ollama/LM Studio that checks every tool call a model proposes before a hook-less agent sees it.
* [Senti macOS app](macos-app.md) - *(superseded by ADR-010)* Planned native SwiftUI menu-bar app — approval popup, activity log, per-agent settings — that fronts the local engine.
* [Server gateway (MCP) — plain-English policy, supervisor-enforced](server-gateway.md) - An MCP endpoint through which AI agents use a company server's files, commands and database; an admin describes access in plain English, Senti compiles role rules, and a supervisor model decides what the rules don't cover.
* [Access and credentials](access-and-credentials.md) - Every credential in Senti (admin login, invite keys, device tokens, agent tokens, hook token), how each is issued, stored, limited and revoked, and the enrollment and device-API protections.
