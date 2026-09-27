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

## Ports, sub-path and a reverse proxy in front

| Option | `.env` | Default | What |
|---|---|---|---|
| `--https-port N` | `SENTI_HTTPS_PORT` | 8443 | admin panel, device API, MCP gateway, `/join`, `/install.sh` |
| `--http-port N` | `SENTI_ADMIN_PORT` | 8081 | plain HTTP, only redirects to the HTTPS port |
| `--admin-base PATH` | `SENTI_ADMIN_BASE` | `/` | admin panel under a sub-path such as `/admin/`; `/api/`, `/join`, `/install.sh`, `/downloads/` stay at the root |
| `--public-url URL` | `SENTI_PUBLIC_URL`, `SENTI_PUBLIC_TLS=true` | empty | Macs reach Senti through a reverse proxy with a publicly trusted certificate (e.g. `https://senti.acme.com`, no port): invites carry no fingerprint, Macs verify the normal way, and Senti's own port stays on `127.0.0.1` (implies `--network local`) |
| `--trusted-proxy CIDRS` | `SENTI_TRUSTED_PROXY` | empty | a reverse proxy on the same server (e.g. `172.16.0.0/12` for the host's nginx reaching Docker); its `X-Forwarded-For` becomes the client address, so `SENTI_ADMIN_ALLOW` and rate limits see real callers |

The backend port is no longer published (only the admin container reaches it), so it can't clash with other services.
A re-install keeps the previous ports, sub-path and proxy unless new ones are given. The admin container writes the
redirect port and `set_real_ip_from` lines at start (`admin/senti-nginx-env.sh`).

Behind a site's nginx on 443 (as on the demo server `senti.gagik.one`): proxy `/admin/`, `/api/`, `/join`, `/install.sh`
and `/downloads/` to `https://127.0.0.1:8443` with `proxy_ssl_verify off` and `proxy_set_header X-Forwarded-For $remote_addr`
(overwrite, never append), and install with `--public-url https://senti.example --admin-base /admin/ --trusted-proxy 172.16.0.0/12`.
Everything, Macs included, then uses port 443 and paths; device requests stay signed by each Mac's key (the signature covers
the path, which the proxy passes unchanged). Without `--public-url`, Macs connect to `https://<host>:8443` and pin Senti's own CA.

```bash
./senti-server install --yes --org Senti --public-url https://senti.gagik.one --admin-allow any --ai none \
  --demo-data --https-port 8443 --http-port 8081 --admin-base /admin/ --trusted-proxy 172.16.0.0/12
```

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
