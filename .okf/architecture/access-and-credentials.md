---
type: Architecture
title: Access and credentials
description: Every credential in Senti (admin login, invite keys, device tokens, agent tokens, hook token), how each is issued, stored, limited and revoked, and the enrollment and device-API protections.
tags: [architecture, security, auth, credentials]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-27T16:00:00Z' }
sources:
  - id: backend
    resource: /backend/app/security.py, /backend/app/routers/device.py, /backend/app/routers/admin.py, /backend/app/routers/gateway.py
    title: Backend auth, enrollment, device API, gateway auth
  - id: tests
    resource: /backend/tests/test_invites.py, /backend/tests/test_first_admin.py, /backend/tests/test_gateway_api.py
    title: Invite, first-admin and gateway access tests
---

# Credentials

| Credential | Prefix | Who holds it | Issued by | Stored as | Grants | Revoke |
|---|---|---|---|---|---|---|
| Admin login | – (JWT after sign-in) | admins | installer / `reset-password` | scrypt hash; JWT with token version | admin panel + admin API | `reset-password`, "Sign out everywhere" (bumps token version) |
| **Invite key** | `sti_` | one employee, once | People page → Invite | SHA-256 only, shown once | enroll **one** Mac as that person/role; single use, 48 h | new invite (replaces unused), revoke button |
| **Device token** | `sdt_` | one enrolled Mac | enrollment | SHA-256 only | signed profiles, `/judge`, events, approvals, and the **server gateway if the person has a server role** | Devices → revoke; clearing the server role removes gateway access |
| **Agent token** | `sag_` | one bot | Server gateway → Add agent | SHA-256 only, shown once | the server gateway as its role | Server gateway → Revoke |
| Hook token | – | the Mac's hooks | `senti start` | `~/.senti/hook.token` (0600) | talk to the local engine socket | regenerate by deleting it |

Senti's own secret scanner flags `sti_` and `sdt_` strings, so agents can't quietly paste or upload them.[^backend]

# Enrollment rules
- People join only with a **personal invite key**: who they are and their role come from the invite, never from what they type.
  The key is claimed atomically (two Macs racing → one wins) and the admin sees "used on <host>"; a key used by someone else is
  noticed when the real employee sees "already used".
- **Shared multi-use codes are refused** unless `SENTI_ALLOW_SHARED_CODES=true`; the opt-in demo code still works for demos.
- The first admin is never created with an empty password; admin emails are case-insensitive.[^tests]

# Device API protections
- `/judge` only accepts a profile that is in the calling device's own bundle (another role's policy text can't be pulled
  through the model); per-device limits: `/judge` 60/min, `/approvals` 20/min, gateway 120/min per agent → `429`
  (the engine treats it like any judge failure: ask).
- The whole MCP endpoint returns `401` without a valid agent token or an enrolled Mac whose person has a server role.

[^backend]: Backend auth, enrollment, device API, gateway auth
[^tests]: Invite, first-admin and gateway access tests
