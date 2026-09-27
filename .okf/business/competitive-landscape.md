---
type: Market Analysis
title: Competitive landscape
description: Existing open-source and commercial projects that overlap with Senti, what each does, and how Senti differs.
tags: [business, competitors, research]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
stale_after: 2026-12-31
sources:
  - id: gh-search
    resource: GitHub repository search via gh CLI, 2026-09-26
    title: GitHub searches for agent firewall / MCP guardrail / Claude Code hooks projects
  - id: hol-guard
    resource: https://github.com/hashgraph-online/hol-guard
    title: HOL Guard repository (analysed in depth)
    last_modified: 2026-09-26
---

# Closest competitors

| Project | What it is | License | Relevance |
|---|---|---|---|
| **[HOL Guard](/research/hol-guard-analysis.md)** (hashgraph-online/hol-guard, ~669★) | "Antivirus for AI agents": hooks for ~16 agents, deterministic rules (Rust runtime + Python control plane), browser dashboard, optional paid Guard Cloud | Apache-2.0 | **Main competitor.** No LLM in the decision path; does not read `.py` scripts before `python x.py`. Separate closed desktop app. |
| unalome-ai/unalome-firewall | Desktop app (Rust) showing agent activity in plain language, MCP config scanning, cost tracking, PII detection | **no license** (cannot fork) | Closest *UX* competitor, but mostly observes after the fact |
| iainnash/flowgate | Native macOS (Swift) approval UI for Claude Code PreToolUse hooks; Go server + Go hook | MIT | Was a reference for a Swift approval UI; not needed since Senti has no client app ([ADR-010](/decisions/adr-010-no-client-ui-fastapi-react.md)); small (3★), last push May 2026 |
| mayankjain0141/nixis | Go "AI agent firewall" for Claude Code; CEL policies, secret scanning, dashboard | MIT | Good rule ideas (`.env`→curl, reverse shells, typosquatting) |
| luckyPipewrench/pipelock | Go agent firewall / egress proxy; scans HTTP, MCP, WebSocket for exfiltration, SSRF, injection | Apache-2.0 | Egress/DLP patterns |
| darfaz/clawmoat | JS agent firewall (data leaks, dangerous tools, poisoned deps) | MIT | Rule ideas |
| rulebricks/claude-code-guardrails | Claude Code hook → hosted rules API | MIT | Simple hook example |
| preloop/preloop | "Agent control plane": MCP firewall, model gateway, approvals | — | Enterprise overlap |

Commercial (per concept draft): Lasso Security (MCP gateway), Palo Alto Prisma AIRS, Check Point AI Guardrails —
mostly API/cloud level, not on the developer machine.

# Platform vendors (biggest strategic risk)

Claude Code and Codex already ship permission modes and sandboxes; Claude Code's auto mode uses an AI check
of actions. A **single-vendor** guard will be absorbed; a **cross-vendor** one will not. See [Risks](/business/risks.md).

# Useful building blocks (not competitors)

| Project | Use in Senti |
|---|---|
| anthropics/sandbox-runtime (`srt`, Apache-2.0) | OS-level file/network enforcement — [Enforcement sandbox](/architecture/enforcement-sandbox.md) |
| cisco-ai-defense/mcp-scanner, Tencent/AI-Infra-Guard | MCP/skill scanning ideas |
| NandhaKishorM/laya | Evaluated and rejected as judge — [Laya evaluation](/research/laya-evaluation.md) |
