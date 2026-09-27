---
type: Guide
title: Connecting AI assistants and bots to the company server (MCP)
description: How employees' assistants and unattended bots reach the server gateway — the local bridge, what senti connect writes for each assistant, bot tokens, access control and troubleshooting.
tags: [guide, mcp, gateway, bridge, onboarding]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-27T16:00:00Z' }
sources:
  - id: bridge
    resource: /engine/src/senti/mcp_bridge.py, /engine/src/senti/connect.py
    title: senti mcp (bridge) and senti connect
  - id: tests
    resource: /engine/tests/test_connect_bridge.py, /backend/tests/test_gateway_api.py
    title: Bridge, connect and device-access tests
---

# Why a bridge
Claude Code, Claude Desktop, Cursor and similar clients **refuse the server's self-signed certificate** (tested: Claude Code
fails with `DEPTH_ZERO_SELF_SIGNED_CERT`), and a token pasted into their config files is easy to leak. So assistants don't
talk to `https://server:8443/api/v1/mcp/` directly: they start the **local bridge** `senti mcp`, a stdio MCP server that
forwards every message to the gateway using this Mac's **pinned certificate and device token** from enrollment.[^bridge]

# Employees (people with a Mac)
1. Admin → **People and roles** → pick the person's **Server access** role (a role from the approved server policy).
2. The person runs `senti setup …` (from their invite) or later `senti connect`.
3. Each installed assistant gets one entry named **`company-server`** with **no secret in it**:

| Assistant | Where `senti connect` writes it |
|---|---|
| Claude Code | `claude mcp add-json --scope user company-server {…}` (its own CLI; `mcp add -e` would swallow the name) |
| Claude Desktop | `~/Library/Application Support/Claude/claude_desktop_config.json` → `mcpServers` |
| Cursor | `~/.cursor/mcp.json` → `mcpServers` |
| Codex CLI | `~/.codex/config.toml` → `[mcp_servers.company-server]` between `# >>> senti` markers |
| OpenCode | `~/.config/opencode/opencode.json` → `mcp` (`type: local`) |

Assistants that aren't installed are skipped; configs are backed up (`*.senti-backup-…`); running it twice changes nothing;
`senti connect --remove` takes it out again. Verified: Claude Code's health check shows `company-server … ✔ Connected`, and a
real session read tickets while Senti refused the card-number column and `payments/cards.csv`.[^tests]

**Access control**: the person's server role decides what the gateway allows; clearing the role or revoking the Mac cuts
access immediately (the bridge then tells the assistant: *"this Mac has no access to the company server — ask your
administrator"*).

# Bots and services (no person, no Mac)
Admin → **Server gateway** → *Add agent* (name + role) → a `sag_…` token shown once, with three ways to connect:
- direct: `claude mcp add --transport http senti-server https://server:8443/api/v1/mcp/ --header "Authorization: Bearer sag_…"`
  (only for clients that trust the certificate);
- bridge: `senti mcp --backend https://server:8443 --token sag_… --fingerprint <sha256>` (pins the certificate; no enrollment);
- MCP JSON: `{"command": "senti", "args": ["mcp", "--backend", …, "--token", …, "--fingerprint", …]}`.
Revoke on the same page; the token stops working immediately.

# Troubleshooting
| Symptom | Cause / fix |
|---|---|
| Tools missing, assistant says it can't connect | restart the assistant after `senti connect`; check `claude mcp list` |
| "no access to the company server" | the person has no server role, or the Mac was revoked |
| `401` in bot logs | wrong/revoked `sag_` token |
| Certificate errors (direct mode) | use the bridge instead |

[^bridge]: senti mcp (bridge) and senti connect
[^tests]: Bridge, connect and device-access tests
