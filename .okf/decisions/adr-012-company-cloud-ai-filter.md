---
type: Decision
title: "ADR-012: One company AI filter in the cloud; no model on employees' Macs"
description: "Employees' Macs run a thin Senti agent (rules, detectors, file checks) and send unclear actions to the organization's cloud AI filter; the local Qwen judge is only for personal use."
tags: [decision, architecture, judge, enterprise]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-27T15:00:00Z' }
sources:
  - id: owner
    resource: claude-code session 973dd678-f568-4b80-aeca-b6d8963be82d (2026-09-27)
    title: "Owner: employees should not run an LLM locally; the company buys it, sets it up once, all employees' agents are safe"
    author: human:vargevorgyan
  - id: results
    resource: /research/company-ai-filter.md
    title: Live measurements of the company AI filter
---

# Context
The owner wants a company to buy Senti, set it up once, and have every employee's agents protected by one AI filter in the
company's cloud, with employees connecting easily through the hook. The MCP server gateway stays as is and uses the same
company AI as its supervisor.[^owner]

# Decision
**Thin local agent + company AI** (not "hook straight to the cloud"):
- Company (enrolled) Macs never load a local model (`local_judge_on_company_macs=false`); profiles set to "local" or
  "local then corporate" use the company AI there. New company profiles default to "Company AI".
- The Mac keeps rules, detectors, script reading, undo, honeytokens and caller checks, so obvious actions stay local and fast
  and hard rules still protect when the company AI is unreachable (then: ask or block, never allow).
- The company AI now receives script contents with secrets redacted by default (`send_to_corporate: with_redacted_content`):
  it runs on the company's own infrastructure and must see what a script does. Admins can set `metadata_only` per profile.
- Write-time script pre-checks go to the company AI too, so running a just-written script reuses the verdict.

# Rejected: hook → cloud for every action
A network round trip per action, the cloud can't read the Mac's files (scripts, undo), and a network blip would block all work.

# Consequences
Employees need ~100 MB instead of ~3 GB and no model download; one place to choose and upgrade the AI; decision quality and
latency now depend on the company's model and its hardware. See [Company AI filter](/research/company-ai-filter.md).

[^owner]: "Owner: employees should not run an LLM locally; the company buys it, sets it up once, all employees' agents are safe"
