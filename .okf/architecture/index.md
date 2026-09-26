# Architecture

* [System overview](system-overview.md) - The four local parts of Senti (hooks, engine, sandbox, app) plus the optional organization backend, and how a single agent action flows through them.
* [senti-hook (hook client)](hook-client.md) - Tiny compiled Swift binary that agents run before each action; forwards the hook JSON to the engine over a Unix socket and fails closed.
* [Decision engine (cascade)](decision-engine.md) - The layered decision pipeline — context, cache, rules, detectors, LLM judge — that turns an agent action into allow / ask / block.
* [LLM judge](llm-judge.md) - The local Qwen3-4B judge for grey-zone actions, its prompt contract, and the four speed optimizations that make it usable.
* [Script inspection before execution](script-inspection.md) - What Senti can read before an agent runs code (scripts, written files, inline code) and the known gaps (npm scripts, imports, downloaded code, binaries).
* [Enforcement sandbox (sandbox-runtime)](enforcement-sandbox.md) - OS-level file and network limits per agent using Anthropic's sandbox-runtime (macOS Seatbelt), the backstop for everything hooks cannot see.
* [Organization backend, profiles and judge routing](org-backend-and-profiles.md) - Admin panel and backend that define profiles per user/role/agent, push them to each Mac, and optionally route grey-zone decisions to a corporate model.
* [Senti macOS app](macos-app.md) - Planned native SwiftUI menu-bar app — approval popup, activity log, per-agent settings — that fronts the local engine.
