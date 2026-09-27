---
type: Use Case
title: Letting agents use API keys without seeing them
description: "Agents call APIs with real keys that never enter their context: they write {{senti:NAME}} and Senti injects the value only at run time, only for allowed sites."
tags: [use-case, individual]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-27T09:00:00Z' }
sources:
  - id: kb
    resource: /.okf (architecture, research, business sections)
    title: Senti knowledge base — implemented behaviour and test results
    author: claude-code/2.1.283
---

# Who

Developer who wants an agent to call Stripe, GitHub or internal APIs.

# Situation

Pasting keys into the chat or `.env` means the agent (and any injected instruction) can read and leak them.

# What Senti does

1. The person stores the key once: `senti secret add STRIPE_KEY --hosts api.stripe.com` (macOS Keychain).
2. The agent writes `curl -H "Authorization: Bearer {{senti:STRIPE_KEY}}" https://api.stripe.com/…`.
3. Senti checks the command; sending the secret anywhere but its allowed hosts is **blocked**.
4. If allowed, the command is rewritten to a one-time wrapper that fetches the value, runs it and masks the value in the output (`[senti:STRIPE_KEY]`).

# Features involved

Secret brokering, grants, output masking.

# How well it is verified

**Verified live** with the Keychain and the real hook (value never in the reply, masked output, replayed grant refused, wrong host blocked).

# Limits

Values transformed before printing (e.g. base64) aren't masked; the substituted command is briefly visible in the local process list.

# Related

- [secret brokering](/architecture/secret-brokering.md)
