---
type: Use Case
title: AI agents working on the company server, with rules in plain English
description: "Support and analytics agents use a server's files, database and commands only through Senti's gateway; the admin describes access in plain English and a supervisor model handles the rest."
tags: [use-case, organization, gateway, mcp]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-27T16:00:00Z' }
---

# Actor
A company that wants agents (employees' assistants and unattended bots) to use data on a server — tickets, customers,
reports — without ever touching payment data, HR files or secrets.

# Flow
1. IT installs Senti (`./senti-server`) and shares the server's folders and SQLite database with the gateway.
2. The admin writes the policy in plain English, reviews the generated rules and examples, approves
   ([Writing a server policy](/guides/writing-server-policy.md)).
3. Employees get a **server role** on the People page; their assistants connect automatically via `senti connect`. Bots get
   their own token ([Connecting assistants](/guides/connecting-assistants.md)).
4. Every read, write, command and query is decided by hard rules, the role rules (SQLite's authorizer for every column) and,
   for anything not covered, the supervisor model. Every call is logged on the Server gateway page.

# Verified
Scripted agent through a real MCP client and a real Claude Code session: tickets and customer names readable; card-number
column, `payments/`, `.env`, `../../etc/passwd`, `bash -c`, `grep -r .` refused with reasons. See
[Server gateway](/architecture/server-gateway.md).

# Limits
SQLite only; a small supervisor model can be lenient on things the policy never mentions (add explicit "never" rules).
