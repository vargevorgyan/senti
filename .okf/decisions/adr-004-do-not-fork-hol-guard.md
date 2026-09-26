---
type: Decision
title: "ADR-004: Do not fork HOL Guard; borrow rules and adapters"
description: "Senti is built fresh in Swift and borrows HOL Guard's Apache-2.0 rule catalogs, fixtures and agent adapters with attribution instead of forking."
tags: [decision, competitor, licensing]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
sources:
  - id: session
    resource: claude-code session 973dd678-f568-4b80-aeca-b6d8963be82d (2026-09-26)
    title: Ideathon planning session
    author: claude-code/2.1.283
---

# Context
HOL Guard covers much of the rules layer and many agents, but is ~430k lines of Python+Rust, has no LLM, and its Mac app is closed.

# Decision
Do not fork. Reuse secret/command rule catalogs, red-team fixtures and agent adapter knowledge (Codex, OpenCode, Cursor), keeping Apache-2.0 NOTICE attribution.
The concept draft also considers depending on its integration layer or contributing upstream (open question: dependency, fork or partnership).

# Consequences
Clear pitch ("we built the understanding layer"), one stack, no Go/Rust/Python bundle inside the app.
Also rejected as fork base: iainnash/flowgate (Swift UI is useful reference, but Go server + committed binaries).
