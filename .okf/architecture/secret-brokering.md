---
type: Component
title: Secret brokering
description: Agents only see {{senti:NAME}} placeholders; values from the Keychain are injected at execution by a one-time wrapper, restricted to allowed hosts and masked in output.
tags: [architecture, secrets, security]
status: stable
resource: /engine/src/senti/secrets.py
generated: { by: claude-code/2.1.283, at: '2026-09-27T08:00:00Z' }
sources:
  - id: code
    resource: /engine/src/senti/secrets.py, /engine/src/senti/secret_exec.py, /engine/tests/test_secrets.py
    title: Secret brokering implementation and tests
---

# How it works

1. The person stores a secret: `senti secret add STRIPE_KEY --hosts api.stripe.com` (value read hidden or from stdin) → macOS
   Keychain (service `am.tumo.senti.secret`); names and allowed hosts in `~/.senti/secrets.json`. `SENTI_SECRET_STORE=file` for tests/Linux.
2. The agent writes `curl -H "Authorization: Bearer {{senti:STRIPE_KEY}}" https://api.stripe.com/v1/charges`.
3. The engine checks the command with a neutral marker (`SENTI_SECRET_STRIPE_KEY`): unknown secret → block; any destination not in
   the secret's hosts → block; no clear destination or a file write → ask; then the normal cascade.
4. If allowed, the hook reply carries `updatedInput`: `python -m senti.secret_exec <grant> -- '<original command>'`
   (Claude Code and Codex `permissionDecision: allow` + `updatedInput`; OpenCode plugin assigns `output.args`; gateway rewrites arguments).
5. The wrapper redeems the grant over the socket (`/v1/secrets/redeem`: single use, 120 s, bound to the SHA-256 of the exact command),
   substitutes values, runs `/bin/sh -c`, and masks values as `[senti:NAME]` in stdout/stderr (holding back partial matches across reads).

Verified live with the Keychain: the reply to the agent has no value, the output shows `[senti:DEMO_TOKEN]`, a replayed grant is refused,
and sending the secret to another host is blocked.

# Limits

The substituted command is visible in the process list to the same user for its lifetime; programs that transform the value before
printing it (base64) are not masked; secrets in file writes are never substituted.
