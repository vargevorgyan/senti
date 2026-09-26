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
| **Judge** | The LLM that decides grey-zone actions (local Qwen3-4B or a corporate model). |
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
| **Judge mode** | `local`, `corporate`, `local_then_corporate`, `none`. |
| **Corporate model** | An organization's internal LLM reached through Senti's backend judge gateway. |
| **MCP / MCP proxy / gateway** | Model Context Protocol tools; Senti can sit between agents and MCP servers. |
| **Prompt injection** | Untrusted text (README, web page, tool output) that instructs the agent to do something harmful. |
| **Exfiltration** | Sending private data (keys, `.env`, files) off the machine. |
| **Honeytoken** | A fake secret planted as bait; any use signals compromise. |
| **OKF** | Open Knowledge Format — the markdown+YAML format of this knowledge base. |
