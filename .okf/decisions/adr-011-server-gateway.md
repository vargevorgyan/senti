---
type: Decision
title: "ADR-011: Server gateway over MCP, policy in plain English, supervisor LLM"
description: "Agents reach a company server only through a Senti MCP gateway; access is written in plain English and compiled to role rules; unclear cases go to a supervisor model, not a human."
tags: [decision, gateway, mcp, enterprise]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-27T12:00:00Z' }
sources:
  - id: owner
    resource: claude-code session 973dd678-f568-4b80-aeca-b6d8963be82d (2026-09-27)
    title: Repo owner's request — server with many agents, limits set by an LLM from plain English, supervisor LLM enforces
    author: human:vargevorgyan
---

# Context
The owner wants agents to connect to a server full of data without hand-writing rules per connection: write the limits in
plain English, let an LLM set them per role, and have a supervisor LLM prevent every read, write or command that violates
them. On 2026-09-26 the team had removed the "MCP gateway" from the roadmap; this request brings back a focused version.[^owner]

# Decision
- The gateway lives in the existing backend (roles, admin panel, corporate judge, audit already there): MCP at `/api/v1/mcp/`.
- Agents authenticate with per-agent tokens; the token decides the role.
- The admin approves compiled rules once (after reviewing examples and warnings); after that no human is in the loop:
  the supervisor model decides uncovered cases and only a clear "allow" passes; failures block.
- Hard rules and SQLite's authorizer are deterministic and can't be overridden by any model.

# Consequences
Real enforcement on servers (agents hold no credentials), a sharper pitch ("describe access in plain English"), reuse of the
same judge and admin panel. Quality of compilation and supervision depends on the model; see
[Server gateway](/architecture/server-gateway.md) for measured limits.

[^owner]: Repo owner's request — server with many agents, limits set by an LLM from plain English, supervisor LLM enforces
