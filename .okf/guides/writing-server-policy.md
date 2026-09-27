---
type: Guide
title: Writing a server policy in plain English
description: How admins describe what AI agents may do on the company server, how the text becomes rules, how to review them before approving, and which model to use.
tags: [guide, gateway, policy, admin]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-27T16:00:00Z' }
sources:
  - id: compiler
    resource: /backend/app/policy_compiler.py
    title: Policy compiler (prompt, schema checks, warnings, example replay)
  - id: live
    resource: /architecture/server-gateway.md
    title: Measured compiles with a local 4B model
---

# Write it like you'd brief a new employee
Name the **roles**, what each may **read**, **change** and **query**, and what is **never** allowed:

> Support agents can read support tickets and customer names, emails and phone numbers (files and database) and write notes in
> tickets/notes. They must never see card numbers, anything in payments or hr, or secrets like .env files. The analytics agent
> can query the orders and tickets tables and read reports, but never customer emails, card numbers or salaries, and it cannot
> change anything.

Tips: use the real folder and table names (the page shows "What the server shares"); say "never" for sensitive things; say
"cannot change anything" for read-only roles. Anything the text doesn't clearly grant is left to the supervisor model.

# What happens on "Generate rules"
The policy model receives the text plus the server's folder list and database schema and proposes per-role rules: file globs
(read / write / deny), allowed programs, readable/writable tables and hidden columns, and notes for the supervisor.[^compiler]
Senti then **checks, it doesn't trust**:
- drops unsafe items (paths outside the shared folder, shells, interpreters, network tools) and lists them as warnings;
- warns about contradictions (granted and denied), unknown tables/columns, and hidden columns to double-check;
- replays the model's example actions through the real checker (SQL on a throwaway copy of the database) and shows
  ✓ / ⚠ / "supervisor decides".

# Review, then approve
Fix the text and generate again until the examples match what you meant; **Approve and go live** creates a new version
(logged in the change log). Agents follow the new rules on their next call.

# Which model
Compilation runs rarely, so use the strongest model you can (`SENTI_POLICY_MODEL_URL` / `SENTI_POLICY_MODEL`; default: the
corporate model). Measured with a 4B local model: ~52 s per compile and real mistakes (hid emails the policy allowed; denied a
folder it also granted) that the warnings and examples exposed.[^live]

[^compiler]: Policy compiler (prompt, schema checks, warnings, example replay)
[^live]: Measured compiles with a local 4B model
