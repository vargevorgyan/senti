# Integrations

* [Agent coverage](agent-coverage.md) - Which AI agents Senti supports and how each is intercepted (hooks, plugin, MCP proxy, sandbox), including the demo trio Claude Code, Codex and OpenCode with local models.
* [Claude Code integration](claude-code.md) - How Senti hooks into Claude Code (PreToolUse and UserPromptSubmit) and the results of a real session run through the prototype.
* [Codex CLI integration (ChatGPT agent)](codex-cli.md) - Codex CLI (the locally running ChatGPT agent) protected through its PreToolUse/UserPromptSubmit/PostToolUse hooks; verified live.
* [Local models support](local-models.md) - The three meanings of local-model support in Senti (agents on local models, DIY agents, Senti's own judge), memory limits by Mac size, and judge auto-selection.
* [OpenCode integration (local models)](opencode.md) - OpenCode (open-source agent for local models) protected by a Senti plugin using tool.execute.before/after and chat.message; verified live with a local Ollama model.
* [Cursor integration](cursor.md) - Cursor (IDE and cursor-agent) protected through hooks.json permission hooks with failClosed; implemented and unit-tested, not yet run against a real Cursor.
* [Cline integration](cline.md) - Cline (VS Code extension and CLI) protected by executable hook files PreToolUse / UserPromptSubmit / PostToolUse; implemented and unit-tested, not yet run against a real Cline.
* [Google Antigravity integration](antigravity.md) - Antigravity (IDE and agy CLI) protected by its hooks.json PreToolUse hook; implemented and unit-tested, not yet run against a real session.
* [ZCode integration](zcode.md) - ZCode (Z.ai) protected through its Claude-Code-compatible hooks in ~/.zcode/cli/config.json; implemented and unit-tested, not yet run against a real ZCode.
* [Hermes Agent integration](hermes.md) - Hermes Agent (Nous Research) protected by pre_tool_call shell hooks with fail_closed; ask uses Hermes' own approval gate. Implemented and unit-tested, not yet run against a real Hermes.
* [OpenClaw integration](openclaw.md) - OpenClaw protected by a native TypeScript plugin on before_tool_call; ask uses OpenClaw's requireApproval. Implemented and unit-tested, not yet run against a real OpenClaw.
