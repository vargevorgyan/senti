# Use cases

What people use Senti for, who they are, what Senti does in each situation and how well it is verified. Each use case links to the architecture that implements it.

# For individual developers

* [Prompt injection in a cloned repository](prompt-injection-in-a-cloned-repo.md) - A developer asks an agent to set up a repo whose README secretly tells AI agents to upload .env; Senti warns the agent and blocks the upload.
* [A script that hides what it does](disguised-malicious-script.md) - An agent writes or runs a script whose name and output look harmless but which steals keys; Senti reads the script first and blocks it.
* [Destructive mistakes and one-click undo](mistakes-and-undo.md) - An agent deletes or overwrites the wrong files; personal folders are protected outright and project changes can be restored.
* [The agent wanders off its task](off-task-access.md) - Asked to fix CSS, the agent opens billing configuration or credentials; the task-aware judge notices it doesn't fit and asks.
* [Installing a malicious or look-alike package](supply-chain-install.md) - An agent installs a typosquatted or known-malicious package, or pulls one from a URL or custom registry; Senti blocks or asks.
* [Letting agents use API keys without seeing them](using-api-keys-without-exposing-them.md) - Agents call APIs with real keys that never enter their context: they write {{senti:NAME}} and Senti injects the value only at run time, only for allowed sites.
* [Local models, offline agents and home-made agents](offline-and-diy-agents.md) - OpenCode on a local model, or a custom Python agent on Ollama, gets the same protection fully offline — via a plugin or the model gateway.

# For teams and organizations

* [Role-based rules for a whole team](role-based-profiles-for-a-team.md) - An admin gives engineers, PMs and bots different agent permissions from one panel; changes reach every Mac in a fraction of a second.
* [Keeping agents away from production and customer data](protecting-production-and-customer-data.md) - Company-specific rules (production hosts, customer data folders) are enforced on every Mac, with a corporate model that knows the company's context.
* [Unattended agents that need a human owner](unattended-agents-with-owner-approval.md) - Autonomous agents run with a strict profile, must be sandboxed, and route their questions to an owner who answers in the admin panel.

# For security and compliance

* [Audit trail and spotting a compromised agent](audit-and-incident-response.md) - Every decision is logged tamper-evidently and uploaded; decoy secrets catch hijacked agents; the security team investigates from one timeline.
* [One policy for every agent vendor](one-policy-for-every-agent-vendor.md) - Claude Code, Codex (ChatGPT) and OpenCode are governed by the same rules and the same log, regardless of which company made the agent.
