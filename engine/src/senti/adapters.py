"""Agent adapters: normalise each agent's hook payload into an Action and render the reply it expects.

- Claude Code: PreToolUse / UserPromptSubmit / PostToolUse; reply hookSpecificOutput.permissionDecision allow|ask|deny.
- Codex CLI: same payload shape; allow = empty stdout, deny = permissionDecision "deny" (Codex has no 'ask'
  and fails open on hook errors, so the hook client turns every failure into an explicit deny).
- OpenCode: the Senti plugin posts a compact JSON; reply {verdict, reason}; the plugin throws on block.
- generic: any custom agent / multi-agent system: POST /v1/check {agent, tool, input, cwd, session_id, task}.
"""
from __future__ import annotations

import json
import os
from typing import Any

from .models import Action, Decision

EVENT_MAP = {"PreToolUse": "pre_tool", "UserPromptSubmit": "prompt", "PostToolUse": "post_tool",
             "pre": "pre_tool", "prompt": "prompt", "post": "post_tool", "pre_tool": "pre_tool", "post_tool": "post_tool"}

OPENCODE_TOOLS = {"bash": "Bash", "read": "Read", "write": "Write", "edit": "Edit", "multiedit": "MultiEdit",
                  "apply_patch": "apply_patch", "patch": "apply_patch", "webfetch": "WebFetch", "websearch": "WebSearch",
                  "grep": "Grep", "glob": "Glob", "list": "LS", "ls": "LS", "task": "Task", "todowrite": "TodoWrite",
                  "todoread": "TodoWrite", "question": "AskUserQuestion", "skill": "Skill", "lsp": "Grep"}
CODEX_TOOLS = {"shell": "Bash", "exec_command": "Bash", "local_shell": "Bash", "unified_exec": "Bash", "container.exec": "Bash",
               "Bash": "Bash", "apply_patch": "apply_patch", "spawn_agent": "Task", "Agent": "Task", "read_file": "Read",
               "view_image": "Read", "web_search": "WebSearch", "update_plan": "TodoWrite"}


def voice(d: Decision) -> str:
    """Brand voice: first person, plain words, always the reason."""
    r = d.reason.rstrip(".")
    if d.verdict == "block":
        return f"Senti: I stopped this. {r}."
    if d.verdict == "ask":
        return f"Senti: should I let this through? {r}."
    return f"Senti: {r}."


def _cmd(v: Any) -> str:
    if isinstance(v, list):
        import shlex
        if len(v) == 3 and v[0] in {"bash", "sh", "zsh", "/bin/bash", "/bin/sh", "/bin/zsh"} and v[1] in {"-lc", "-c"}:
            return v[2]
        return shlex.join(str(x) for x in v)
    return str(v or "")


def parse(agent: str, ev: dict) -> Action:
    if agent == "opencode":
        tool_raw = ev.get("tool", "")
        args = dict(ev.get("args") or {})
        tool = OPENCODE_TOOLS.get(tool_raw, tool_raw)
        inp: dict[str, Any] = {}
        for k, v in args.items():
            nk = {"filePath": "file_path", "oldString": "old_string", "newString": "new_string", "patchText": "patchText",
                  "workdir": "workdir"}.get(k, k)
            inp[nk] = v
        cwd = inp.get("workdir") or ev.get("cwd") or ev.get("directory") or os.getcwd()
        if tool not in OPENCODE_TOOLS.values() and "_" in tool_raw and tool_raw not in OPENCODE_TOOLS:
            server, _, name = tool_raw.partition("_")
            tool = f"mcp__{server}__{name}"
        return Action(agent, tool, inp, cwd, ev.get("sessionID") or ev.get("session_id", ""),
                      EVENT_MAP.get(ev.get("event", "pre"), "pre_tool"), tool_raw, ev.get("prompt", ""), ev.get("output"))
    if agent == "generic":
        return Action(ev.get("agent", "generic"), ev.get("tool", ""), ev.get("input") or {}, ev.get("cwd") or os.getcwd(),
                      ev.get("session_id", ""), EVENT_MAP.get(ev.get("event", "pre_tool"), "pre_tool"), ev.get("tool", ""),
                      ev.get("task", "") or ev.get("prompt", ""), ev.get("response"))
    # claude / codex (Claude-compatible hook payloads)
    name = ev.get("hook_event_name", "PreToolUse")
    raw = ev.get("tool_name", "")
    inp = dict(ev.get("tool_input") or {})
    tool = raw
    if agent == "codex":
        tool = CODEX_TOOLS.get(raw, raw)
        if tool == "Bash":
            inp["command"] = _cmd(inp.get("command") or inp.get("cmd") or "")
            if inp.get("workdir"):
                ev["cwd"] = inp["workdir"]
        if tool == "apply_patch" and "command" in inp and isinstance(inp["command"], list):
            inp["command"] = inp["command"][-1]
        if tool == "Read" and "path" in inp:
            inp["file_path"] = inp["path"]
    return Action(agent, tool, inp, ev.get("cwd") or os.getcwd(), ev.get("session_id", ""), EVENT_MAP.get(name, "pre_tool"), raw,
                  ev.get("prompt", ""), ev.get("tool_response"))


def render(agent: str, action: Action, d: Decision | None, context: str | None) -> str:
    """Body the hook client prints to stdout."""
    if agent == "opencode" or agent == "generic":
        if d is None:
            return json.dumps({"verdict": "allow", "reason": "", "context": context})
        out = {"verdict": d.verdict, "reason": voice(d), "layer": d.layer, "rule": d.rule, "context": context,
               "severity": d.severity, "snapshot": d.meta.get("snapshot")}
        if d.meta.get("updated_input"):
            upd = dict(d.meta["updated_input"])
            if agent == "opencode" and "workdir" in upd:
                upd.pop("workdir")
            out["updatedInput"] = upd
        return json.dumps(out)
    if action.event == "prompt":
        return ""
    if action.event == "post_tool":
        if not context:
            return ""
        return json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": context}})
    assert d is not None
    if d.verdict == "allow" and d.meta.get("updated_input"):
        return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow",
                                                  "permissionDecisionReason": voice(d), "updatedInput": d.meta["updated_input"]}})
    if agent == "codex":
        if d.verdict == "allow":
            return ""  # Codex rejects permissionDecision:allow without updatedInput; empty output = no objection
        return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                  "permissionDecisionReason": voice(d)}})
    perm = {"allow": "allow", "ask": "ask", "block": "deny"}[d.verdict]
    return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": perm,
                                              "permissionDecisionReason": voice(d)}})
