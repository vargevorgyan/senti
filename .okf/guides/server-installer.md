---
type: Guide
title: Server installer and manager (./senti-server)
description: Reference for the organization-side installer — what it asks, what it writes, every management command, backups and troubleshooting.
tags: [guide, installer, operations]
status: stable
resource: /senti-server
generated: { by: claude-code/2.1.283, at: '2026-09-27T16:00:00Z' }
sources:
  - id: script
    resource: /senti-server
    title: Installer script (bash, macOS and Linux, ShellCheck clean)
---

# Install

```bash
./senti-server                       # guided: press Enter to accept suggestions
./senti-server install --yes --org "Acme" --network lan --ai api --ai-url https://… --ai-model … --ai-key …   # unattended
```

Questions (all have defaults): company name · admin email (lowercased) · admin password (Enter = a strong random one, shown
once) · who reaches Senti (**network** = team's Macs and agents connect, binds 0.0.0.0, certificate for hostname + LAN IP;
**only this computer** = 127.0.0.1) · **AI for unclear actions**: private model in Docker (Ollama `qwen2.5:3b`, ~2 GB download,
~6 GB RAM) / a model API the company already uses (any OpenAI-compatible URL + model + key) / none for now (corporate judge
switched off → unclear actions are asked about) · demo "company server" data.[^script]

What it does: checks Docker (installs it on Linux with confirmation; starts Docker Desktop on macOS), memory, disk and ports;
writes `.env` (mode 600, old one backed up as `.env.bak.*`) with a generated `SENTI_SECRET_KEY`; builds and starts; waits for
`/api/v1/health`; signs in once to apply the AI choice; seeds demo data inside the backend container (no host Python needed);
**removes the admin password from `.env`** afterwards; prints the admin URL, the one-time password, the certificate
fingerprint and next steps. Re-running on an existing install keeps data (people, Macs, audit).

# Manage

| Command | Does |
|---|---|
| `status` | containers + whether Senti answers |
| `info` | admin URL (LAN only if shared), admin login, AI mode, certificate fingerprint |
| `logs [service]` | follow logs |
| `stop` / `start` | Macs keep protecting with their saved rules while it's stopped |
| `update` | `git pull --ff-only` (if a checkout) + rebuild + restart; data kept (tested: 14 s) |
| `backup [file]` | people, profiles, devices, audit, **TLS certificate** and `.env` → `senti-backup-*.tar.gz` (mode 600) + shared files → `*-server-data.tar.gz` (mode 600). Keeping the certificate means Macs don't have to re-enroll after a restore |
| `restore FILE` | replace data from a backup (asks first) |
| `reset-password [email]` | new random password, signs out every session (tested: the new password signs in) |
| `uninstall [--delete-data]` | stop and remove; with `--delete-data` (type DELETE) also the volumes; `server-data/` is kept |

Backups, `.env` and `.env.bak.*` are git-ignored.

# Safety details
- If the data volume is wiped and `.env` has no password, the backend creates the admin with a **random** password printed
  once to its log — never an empty one (`backend/tests/test_first_admin.py`).
- The installer refuses ports used by other programs and passwords shorter than 10 characters.

# Troubleshooting
- *"Senti didn't start"* → `./senti-server logs backend`.
- Browser certificate warning → expected (self-signed); compare the fingerprint from `info`. Macs pin it at enrollment.
- AI assistants can't use the self-signed certificate → they connect through the local bridge, see
  [Connecting assistants](/guides/connecting-assistants.md).

[^script]: Installer script (bash, macOS and Linux, ShellCheck clean)
