---
type: Use Case
title: Keeping agents away from production and customer data
description: Company-specific rules (production hosts, customer data folders) are enforced on every Mac, with a corporate model that knows the company's context.
tags: [use-case, organization]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-27T09:00:00Z' }
sources:
  - id: kb
    resource: /.okf (architecture, research, business sections)
    title: Senti knowledge base — implemented behaviour and test results
    author: claude-code/2.1.283
---

# Who

Engineering org with production databases and regulated customer data.

# Situation

An agent fixing a test decides to query `billing.prod.corp.internal` or copy files from `/data/customers`.

# What Senti does

1. Profile rules: `/data/customers/**` **never allowed**; `*.prod.corp.internal` **ask first** — enforced deterministically, including for database clients (`psql -h`, `mysql -h`, connection URLs).
2. Company instructions are given to the judge ("production hosts need approval"); in *corporate* or *local, then corporate* mode the company's own model decides unclear cases.
3. What the corporate model may see is set per profile (only the action, redacted content, or full).

# Features involved

Profile file/network rules, `network.ask`, corporate judge gateway, privacy levels.

# How well it is verified

**Tested**; lesson recorded: a 3B corporate model first *allowed* a prod query, so hard policy is encoded as rules, not only instructions.

# Limits

Only hosts visible in the command are recognised; code that connects inside a program needs the sandbox or the judge.

# Related

- [org backend and profiles](/architecture/org-backend-and-profiles.md)
