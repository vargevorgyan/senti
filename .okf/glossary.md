---
type: Glossary
title: Glossary
description: Definitions of terms used across the Senti knowledge base.
tags: [glossary]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
---

| Term | Meaning |
|---|---|
| **Agent** | An AI tool that takes actions on the computer: Claude Code, Codex CLI, OpenCode, Cursor, custom agents. |
| **Hook** | A program an agent runs before (or after) each action, which can allow/deny it. Senti's is `senti-hook`. |
| **PreToolUse** | Claude Code / Codex hook event fired before a tool call. |
| **UserPromptSubmit** | Hook event fired when the user sends a prompt; Senti stores it as the session **task**. |
| **Engine / Senti agent** | The local background process that decides allow/ask/block. |
| **Cascade** | Cache → rules → detectors → LLM judge; cheap checks first. |
| **Judge** | The LLM that decides grey-zone actions: the company AI filter on company Macs; a local Qwen3-4B only for personal use. |
| **Verdict** | allow / ask / block. `block` maps to hook `deny`. |
| **Fail closed** | On any error/timeout/missing component, answer ask or block — never allow. |
| **Hard rule** | A deterministic deny the LLM can never override. |
| **Detector** | Pattern-based check: secrets, base64 decoding, script static scan, taint. |
| **Taint** | Tracking that sensitive data (e.g. a secret file) is flowing to a network sink. |
| **Prefix cache** | Reusing the model's processed system prompt across requests (4.6× faster verdicts). |
| **Logit verdict** | Reading allow/ask/block probabilities from one forward pass instead of generating text. |
| **Write-time pre-check / prefetch** | Judging a script when the agent writes it, so the later run hits the cache. |
| **Sandbox / srt** | OS-level file/network limits (anthropics/sandbox-runtime on macOS Seatbelt). |
| **Profile** | Policy for a user/role/agent: file, network, shell rules, judge mode, instructions. |
| **Judge mode** | `corporate` (Company AI, default), `local`, `local_then_corporate`, `none`; company Macs always use the company AI. |
| **Corporate model** | An organization's internal LLM reached through Senti's backend judge gateway. |
| **MCP** | Model Context Protocol: how agents call tools on other systems. |
| **Prompt injection** | Untrusted text (README, web page, tool output) that instructs the agent to do something harmful. |
| **Exfiltration** | Sending private data (keys, `.env`, files) off the machine. |
| **Honeytoken** | A fake secret planted as bait; any use signals compromise. |
| **OKF** | Open Knowledge Format — the markdown+YAML format of this knowledge base. |
| **Company AI filter** | The company's one LLM in its cloud (the corporate model) that decides unclear actions for every employee's Mac and supervises the server gateway. |
| **Thin Senti agent** | The engine on an employee's Mac: rules, detectors, file checks, no AI model (~100 MB). |
| **Server gateway** | Senti's MCP endpoint (`/api/v1/mcp/`) through which agents use the company server's files, database and commands under role rules. |
| **Server policy** | The admin's plain-English description of who may do what on the server, compiled into role rules and approved. |
| **Supervisor** | The company AI deciding gateway calls the rules don't cover; only a clear "allow" passes. |
| **Server role** | A person's role on the server gateway (People page); their assistants use it through their Mac. |
| **Local MCP bridge** | `senti mcp`: stdio MCP server on the Mac that forwards to the gateway with the Mac's pinned certificate and device token. |
| **Invite key (`sti_`)** | Personal one-time key to enroll one Mac; 48 h; stored hashed. |
| **Device token (`sdt_`)** | An enrolled Mac's credential; stored hashed; revocable. |
| **Agent token (`sag_`)** | A bot's gateway credential; the token decides its role. |
| **`./senti-server`** | Installer and manager for the company side. |
| **`senti setup` / `senti connect`** | One-step Mac setup from an invite / add the `company-server` entry to installed assistants. |
