# Integrations

* [Agent coverage](agent-coverage.md) - Which AI agents Senti supports and how each is intercepted (hooks, plugin, MCP proxy, sandbox), including the demo trio Claude Code, Codex and OpenCode with local models.
* [Claude Code integration](claude-code.md) - How Senti hooks into Claude Code (PreToolUse and UserPromptSubmit) and the results of a real session run through the prototype.
* [Codex CLI integration (ChatGPT agent)](codex-cli.md) - Plan for hooking OpenAI's Codex CLI, the locally running ChatGPT coding agent, using its PreToolUse hooks.
* [Local models support](local-models.md) - The three meanings of local-model support in Senti (agents on local models, DIY agents, Senti's own judge), memory limits by Mac size, and judge auto-selection.
* [OpenCode integration (local models)](opencode.md) - Plan for protecting OpenCode — the open-source agent the team chose for local models — via a tool.execute.before plugin.
