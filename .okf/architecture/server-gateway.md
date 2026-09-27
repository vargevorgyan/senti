---
type: Architecture
title: Server gateway (MCP) — plain-English policy, supervisor-enforced
description: An MCP endpoint through which AI agents use a company server's files, commands and database; an admin describes access in plain English, Senti compiles role rules, and a supervisor model decides what the rules don't cover.
tags: [architecture, gateway, mcp, server, enterprise]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-27T12:00:00Z' }
sources:
  - id: code
    resource: /backend/app/routers/gateway.py
    title: Gateway router, MCP tools, admin API
  - id: policy
    resource: /backend/app/gateway_policy.py
    title: Compiled policy schema, deterministic checker, safe executors
  - id: compiler
    resource: /backend/app/policy_compiler.py
    title: Plain English → role rules + checked examples
  - id: tests
    resource: /backend/tests/test_gateway_policy.py
    title: Checker attack tests and MCP end-to-end tests (101 backend tests in total)
---

# Why

On a laptop Senti can only advise the agent through hooks. On a server the agent never gets direct access: it reaches the
server's files, commands and database **only through Senti**, which holds the access and performs every action itself.
Nobody writes rules by hand: the admin describes access in plain English, per role.[^code]

# Flow

```
Admin panel ─ "Support agents can read tickets and customer names… never card numbers or payments…"
     │  Generate rules (policy model) → role rules + example actions replayed through the real checker → Approve
     ▼
Agents (Claude Code, custom bots…) ── MCP over HTTPS, token = role ──► /api/v1/mcp/
   tools: list_files · read_file · write_file · run_command · query_db
     │ 1 hard rules   path escape (../, absolute, symlinks), shells/interpreters/network tools, exec/delete flags,
     │                recursive tools over folders with hidden files, SQL outside the role's tables → block
     │ 2 role rules   compiled from the policy; deny beats allow; SQLite's authorizer checks every table/column → allow/block
     │ 3 supervisor   anything not covered → supervisor LLM with the plain-English policy; only a clear "allow" passes
     ▼                (no human in the loop; supervisor down → block)
Senti performs the action itself: no shell, confined to the shared folder, minimal env, time and size limits; logged
```

# What agents can reach (sources)

The installer mounts one host folder into the runner as `/srv` (`SENTI_GATEWAY_DIR`, default `./server-data`; another folder
with `./senti-server install --gateway-dir /path` — its files keep their owner, the runner gets an ACL). In the admin panel
(**Server gateway → What agents can reach**) the admin ticks, inside it, **any number of folders** and **SQLite files**.
Paths in the policy are relative to the shared folder (`northwind/support/tickets/**`); everything outside the ticked folders is
refused before any rule (listing only shows the way to them; recursive commands must stay inside them). With several
databases `query_db` takes a `database` name (file name without `.db`; `main` works when there is one) and rules may qualify
tables as `<db>.<table>` / `<db>.<table>.<column>`; unqualified rules apply to every database. The choice is stored in the
backend (`gateway_sources`), sent with every runner call and re-checked by the runner (nothing outside `/srv`; database files
never readable as files). A chosen source that disappears is dropped; nothing left fails closed. Demo data (`--demo-data`) is
opt-in only.

# Security properties (tested)[^tests]

- **Token = identity and role**: `sag_…` tokens, only the SHA-256 stored, shown once, revocable; the whole MCP endpoint
  (even tool listing) returns 401 without a valid token; per-agent rate limit (`SENTI_GATEWAY_RPM`).
- **Files**: resolved real paths must stay inside the shared folder (symlinks followed); listings hide denied and unrelated entries.
- **Commands**: parsed with `shlex`, run without a shell; 70+ programs never allowed (shells, interpreters, network, `sed`/`awk`,
  `git`, `sqlite3`…); `find -exec/-delete`, `sort -o` etc. blocked; path arguments pass the same file rules; programs that write
  (`cp`, `mv`, `rm`…) need write rules; recursive tools (`grep -r`, `ls -R`, `find`) only on folders the role fully owns.
  Absolute or `~` paths in commands are refused (the program would get the real path, not the shared folder's).
- **Database**: SQLite opened read-only unless the role has write tables; `set_authorizer` decides every read/write per
  table and column (so `select *` fails if it includes a hidden column); no PRAGMA/ATTACH/DDL; table names visible, full schema not.
  `WITH` names are allowed but their bodies are checked; queries stop after 5 s; checks and commands run off the event loop.
- **Compilation is checked, not trusted**: the schema drops paths outside the root and dangerous programs; warnings list
  contradictions (granted and denied), unknown tables/columns and hidden columns to double-check; example actions are replayed
  (SQL against a throwaway copy of the database) and shown as ✓/⚠ before the admin approves.

# Measured (M1 8 GB, local Qwen3-4B as policy model and supervisor)

| Step | Result |
|---|---|
| Compile a 3-sentence, 2-role policy | ~52 s; 9/11 examples as intended; model mistakes surfaced as warnings |
| Rule decisions through MCP | 3–15 ms |
| Supervisor decisions | 3.4–8.8 s |
| Scripted agent (13 calls, real MCP client) | all forbidden reads, the card-number column, `../`, `.env`, `bash -c`, `grep -r .` blocked |
| Real Claude Code session using the gateway | card-number lookup refused; Claude stopped instead of working around it |

# Who can connect

- **People's AI assistants**: through their enrolled Mac and the local bridge (`senti connect` / `senti mcp`); the admin picks
  each person's server role on the People page. See [Customer onboarding](/guides/customer-onboarding.md).
- **Bots**: an agent token (`sag_…`), directly or through the bridge.

# Known limits

- A 4B model is a weak **policy compiler** (e.g. hid email/phone the policy allowed, denied a folder it also granted):
  the review step catches it, and `SENTI_POLICY_MODEL_URL` can point compilation at a stronger model (it runs rarely).
- The 4B **supervisor** can be lenient: it allowed support to read a report the policy never mentioned. Add explicit denies
  for anything sensitive; a stricter supervisor prompt / threshold is future work.
- SQLite only; rate limits are in-memory (one backend process).

# Admin API

`GET /admin/gateway/policy`, `POST /admin/gateway/policy/compile {text}`, `POST /admin/gateway/policy/approve`,
`GET|POST /admin/gateway/agents`, `DELETE /admin/gateway/agents/{id}`, `GET /admin/gateway/events`. MCP: `/api/v1/mcp/`.

[^code]: Gateway router, MCP tools, admin API
[^tests]: Checker attack tests and MCP end-to-end tests (101 backend tests in total)
