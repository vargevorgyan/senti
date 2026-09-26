---
type: Document Summary
title: Concept draft v0.1 summary
description: Faithful summary of the team's "Role-Based Guardrails for AI Agents" concept draft (for mentor review), including components, role profiles and example scenarios.
tags: [business, enterprise, concept-draft]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-26T19:10:00Z' }
sources:
  - id: concept-draft
    resource: AI_Agent_Guardrails_Concept_Draft.docx (concept draft v0.1, September 2026, for mentor review)
    title: Role-Based Guardrails for AI Agents — concept draft v0.1
    author: human:vargevorgyan
---

# Summary

A **company-hosted control layer** that gives every AI agent an identity, a role-based profile and enforced boundaries —
"like an employee badge that opens only certain doors". Every action is checked against the profile before it runs;
dangerous actions blocked, ambiguous ones explained in plain language, all monitoring data stays inside the company.
One line: *IAM and antivirus for AI agents, running entirely on the company's own infrastructure.*[^concept-draft]

Note: the team later removed the **MCP gateway** from the roadmap (2026-09-26); it is kept here only as part of the original draft.

# Components (as drafted)

| Component | Role |
|---|---|
| Policy server (on-prem) | Role profiles synced from the identity provider (Okta, Entra ID, Google Workspace), decision engine with filter model, audit log, admin console |
| Endpoint client | Detects agents, installs hooks (reusing HOL Guard integrations), local rules, forwards grey-zone cases, reports compliance; strict local mode if server unreachable |
| MCP gateway | *(removed from roadmap)* single entry to internal services with short-lived scoped credentials |
| LLM gateway | OpenAI/Anthropic-compatible proxy that redacts secrets and controls which models each role may use |
| Autonomous agents | Own service identity, named human owner, rate/budget limits, expiry; approvals escalate to the owner (e.g. Slack) |

# Decision cascade (as drafted)

1. Local rules (µs–ms) · 2. Specialized detectors (secret scanning, small injection classifiers, PII, taint) (ms) ·
3. Filter LLM on the policy server (hundreds of ms – seconds). The LLM gets structured metadata rather than raw content where possible,
returns strict JSON, is cached per task and action pattern, never overrides a hard deny; failures fail closed.

# Role profiles (as drafted)

| Profile | Allowed | Blocked or requires approval |
|---|---|---|
| Developer | Own projects' code, tests, package installs with supply-chain checks, dev environment | Production DBs, other teams' repos, production secrets, sending code to external models unfiltered |
| PM / Product | Jira, Confluence, analytics (read-only) | Shell, writing to repos, exports with customer personal data |
| Designer | Figma, design folders, image generation | Shell, source code, internal databases |
| Autonomous agent | Only explicitly granted tools and domains | Everything else; approvals go to the owner |

**Delegation rule:** an agent acting for an employee gets the intersection of the employee's rights, the agent's profile and the task scope — never more than the employee.

# Example scenarios (as drafted)

- **Secret exfiltration:** agent tries `curl` to post `.env` to an unknown paste site → a local rule blocks instantly.
- **Out-of-profile access:** a PM's agent asks for a GitHub repo's contents → refused and logged (drafted via the MCP gateway).
- **Grey zone:** task "fix CSS on the landing page", agent reads billing service config → filter LLM sees it does not fit the task → plain-language question. (Reproduced in our [simulation](/research/end-to-end-simulation.md).)

# Key design decisions (as drafted)

Hybrid, not LLM-only; enforced rollout via MDM and managed settings; roles plus context (project, environment, task);
observe first (1–2 weeks per role), then enforce. Risks and open questions: see [Risks](/business/risks.md), [Open questions](/roadmap/open-questions.md).

[^concept-draft]: Role-Based Guardrails for AI Agents — concept draft v0.1
