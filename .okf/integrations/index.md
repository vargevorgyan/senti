# Integrations

* [Agent coverage](agent-coverage.md) - Which AI agents Senti supports and how each is intercepted (hooks, plugin, MCP proxy, sandbox), including the demo trio Claude Code, Codex and OpenCode with local models.
* [Claude Code integration](claude-code.md) - How Senti hooks into Claude Code (PreToolUse and UserPromptSubmit) and the results of a real session run through the prototype.
* [Codex CLI integration (ChatGPT agent)](codex-cli.md) - Codex CLI (the locally running ChatGPT agent) protected through its PreToolUse/UserPromptSubmit/PostToolUse hooks; verified live.
* [Local models support](local-models.md) - The three meanings of local-model support in Senti (agents on local models, DIY agents, Senti's own judge), memory limits by Mac size, and judge auto-selection.
* [OpenCode integration (local models)](opencode.md) - OpenCode (open-source agent for local models) protected by a Senti plugin using tool.execute.before/after and chat.message; verified live with a local Ollama model.
