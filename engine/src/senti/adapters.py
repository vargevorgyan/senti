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
import re
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


# ---------------------------------------------------------------- agents added 2026-09-27
def _multi(agent: str, subs: list[tuple[str, dict]], cwd: str, session: str, raw: str) -> Action:
    """Several actions in one tool call (read 3 files, run 2 commands): checked separately, strictest wins."""
    if len(subs) == 1:
        t, i = subs[0]
        return Action(agent, t, i, cwd, session, "pre_tool", raw)
    return Action(agent, "__multi__", {"actions": [[t, i] for t, i in subs]}, cwd, session, "pre_tool", raw)


def _jsonish(v: Any) -> Any:
    if isinstance(v, str) and v[:1] in "[{":
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


def _mcp(server: str, tool: str) -> str:
    return f"mcp__{server or 'mcp'}__{tool}"


def parse_cursor(ev: dict) -> Action:
    name = ev.get("hook_event_name", "")
    cwd = ev.get("cwd") or (ev.get("workspace_roots") or [os.getcwd()])[0]
    session = ev.get("conversation_id", "")
    if name == "beforeSubmitPrompt":
        return Action("cursor", "", {}, cwd, session, "prompt", name, ev.get("prompt", ""))
    if name in {"postToolUse", "afterShellExecution", "afterFileEdit", "afterMCPExecution"}:
        tool = {"afterShellExecution": "Bash", "afterFileEdit": "Edit"}.get(name, ev.get("tool_name", ""))
        inp = {"command": ev.get("command", "")} if name == "afterShellExecution" else {"file_path": ev.get("file_path", "")}
        return Action("cursor", tool, inp, cwd, session, "post_tool", name,
                      response=ev.get("tool_output") or ev.get("output") or "", native_ask=True)
    if name == "beforeShellExecution":
        return Action("cursor", "Bash", {"command": ev.get("command", "")}, ev.get("cwd") or cwd, session, "pre_tool", name, native_ask=True)
    if name == "beforeMCPExecution":
        args = _jsonish(ev.get("tool_input") or {})
        return Action("cursor", _mcp(ev.get("mcp_server_name", ""), ev.get("tool_name", "")), args if isinstance(args, dict) else {"input": args},
                      cwd, session, "pre_tool", name, native_ask=True)
    if name == "beforeReadFile":
        return Action("cursor", "Read", {"file_path": ev.get("file_path", "")}, cwd, session, "pre_tool", name, native_ask=False)
    # preToolUse: shell, reads and MCP have dedicated hooks above; everything else (writes, deletes, edits, tasks) is checked here
    tool = ev.get("tool_name", "")
    inp = dict(ev.get("tool_input") or {})
    path = inp.get("file_path") or inp.get("path") or inp.get("target_file") or ""
    if tool in {"Shell", "Read"} or tool.startswith("MCP"):
        a = Action("cursor", "", {}, cwd, session, "pre_tool", name, native_ask=False)
        a.input = {"__covered__": tool}
        return a
    if tool in {"Write", "Create"}:
        return Action("cursor", "Write", {"file_path": path, "content": inp.get("content") or inp.get("contents") or ""}, cwd, session,
                      "pre_tool", name, native_ask=False)
    if tool in {"Edit", "StrReplace", "MultiEdit"}:
        return Action("cursor", "Edit", {"file_path": path, "old_string": inp.get("old_string", ""), "new_string": inp.get("new_string", "")},
                      cwd, session, "pre_tool", name, native_ask=False)
    if tool == "Delete":
        import shlex
        return Action("cursor", "Bash", {"command": f"rm {shlex.quote(path)}"}, cwd, session, "pre_tool", name, native_ask=False)
    if tool == "Grep":
        return Action("cursor", "Grep", {"pattern": inp.get("pattern", ""), "path": path or cwd}, cwd, session, "pre_tool", name,
                      native_ask=False)
    return Action("cursor", {"Task": "Task", "WebFetch": "WebFetch", "WebSearch": "WebSearch"}.get(tool, tool), inp, cwd, session,
                  "pre_tool", name, native_ask=False)


CLINE_TOOLS = {"read_file": "Read", "write_to_file": "Write", "search_files": "Grep", "list_files": "LS",
               "list_code_definition_names": "LS", "search_codebase": "Grep", "ask_followup_question": "AskUserQuestion",
               "ask_question": "AskUserQuestion", "attempt_completion": "TodoWrite", "new_task": "Task", "spawn_agent": "Task",
               "plan_mode_respond": "TodoWrite", "skills": "Skill"}


def _cline_actions(tool: str, p: dict) -> list[tuple[str, dict]]:
    p = {k: _jsonish(v) for k, v in (p or {}).items()}
    if tool in {"execute_command", "run_commands"}:
        cmds = p.get("commands") or p.get("command") or p.get("cmd") or []
        if isinstance(cmds, str):
            cmds = [cmds]
        out = []
        for c in cmds:
            if isinstance(c, dict):
                import shlex
                c = " ".join([c.get("command", "")] + [shlex.quote(str(x)) for x in c.get("args", [])])
            out.append(("Bash", {"command": str(c)}))
        return out or [("Bash", {"command": ""})]
    if tool in {"read_files"}:
        files = p.get("files") or p.get("file_paths") or p.get("paths") or []
        return [("Read", {"file_path": f.get("path") if isinstance(f, dict) else str(f)}) for f in files] or [("Read", {"file_path": ""})]
    if tool == "write_to_file":
        return [("Write", {"file_path": p.get("path", ""), "content": p.get("content", "")})]
    if tool == "replace_in_file":
        diff = str(p.get("diff", ""))
        new = "\n".join(re.findall(r"=======\n(.*?)\n>>>>>>> REPLACE", diff, re.S)) or diff
        return [("Edit", {"file_path": p.get("path", ""), "old_string": "", "new_string": new})]
    if tool == "editor":
        if p.get("old_text") in (None, "") and p.get("insert_line") is None:
            return [("Write", {"file_path": p.get("path", ""), "content": p.get("new_text", "")})]
        return [("Edit", {"file_path": p.get("path", ""), "old_string": p.get("old_text", ""), "new_string": p.get("new_text", "")})]
    if tool == "apply_patch":
        return [("apply_patch", {"command": p.get("input") or p.get("patch", "")})]
    if tool in {"fetch_web_content", "web_fetch"}:
        reqs = p.get("requests") or [{"url": p.get("url", "")}]
        return [("WebFetch", {"url": r.get("url", "") if isinstance(r, dict) else str(r)}) for r in reqs]
    if tool == "browser_action":
        return [("WebFetch", {"url": p.get("url", "")})] if p.get("url") else [("mcp__cline__browser_action", p)]
    if tool in {"use_mcp_tool", "access_mcp_resource"}:
        return [(_mcp(p.get("server_name", ""), p.get("tool_name") or p.get("uri", "resource")), _jsonish(p.get("arguments")) or {})]
    if "__" in tool:
        server, _, name = tool.partition("__")
        return [(_mcp(server, name), p)]
    t = CLINE_TOOLS.get(tool, tool)
    if t == "Read":
        return [("Read", {"file_path": p.get("path", "")})]
    if t in {"Grep", "LS"}:
        return [(t, {"path": p.get("path", ""), "pattern": p.get("regex") or p.get("pattern", "")})]
    return [(t, p)]


def parse_cline(ev: dict) -> Action:
    hook = ev.get("hookName", "")
    cwd = (ev.get("workspaceRoots") or [os.getcwd()])[0]
    session = ev.get("taskId", "")
    if hook in {"UserPromptSubmit", "prompt_submit"}:
        ups = ev.get("userPromptSubmit") or {}
        return Action("cline", "", {}, cwd, session, "prompt", hook, ups.get("prompt", "") or ev.get("prompt", ""))
    if hook in {"PostToolUse", "tool_result"}:
        post = ev.get("postToolUse") or ev.get("tool_result") or {}
        return Action("cline", post.get("toolName") or post.get("name", ""), {}, cwd, session, "post_tool", hook,
                      response=post.get("result") or post.get("output") or "")
    call = ev.get("preToolUse") or {}
    if call:
        tool, params = call.get("toolName", ""), call.get("parameters") or {}
    else:
        tc = ev.get("tool_call") or {}
        tool, params = tc.get("name", ""), tc.get("input") or {}
    return _multi("cline", _cline_actions(tool, params), cwd, session, tool)


ANTIGRAVITY_TOOLS = {"view_file": "Read", "view_file_outline": "Read", "view_code_item": "Read", "list_dir": "LS", "find_by_name": "Glob",
                     "grep_search": "Grep", "codebase_search": "Grep", "search_web": "WebSearch", "read_url_content": "WebFetch",
                     "task_boundary": "TodoWrite", "notify_user": "TodoWrite"}


def parse_antigravity(ev: dict) -> Action:
    cwd = (ev.get("workspacePaths") or [os.getcwd()])[0]
    session = ev.get("conversationId", "")
    call = ev.get("toolCall") or {}
    name, args = call.get("name", ""), dict(call.get("args") or {})
    post = "error" in ev or ev.get("hookEventName") == "PostToolUse" or ev.get("__event") == "post"
    event = "post_tool" if post else "pre_tool"
    path = args.get("AbsolutePath") or args.get("TargetFile") or args.get("DirectoryPath") or args.get("SearchPath") or args.get("File") or ""
    if name == "run_command":
        return Action("antigravity", "Bash", {"command": args.get("CommandLine", "")}, args.get("Cwd") or cwd, session, event, name)
    if name == "write_to_file":
        return Action("antigravity", "Write", {"file_path": path, "content": args.get("CodeContent", "")}, cwd, session, event, name)
    if name in {"replace_file_content", "multi_replace_file_content"}:
        new = args.get("ReplacementContent") or "\n".join(str(c.get("ReplacementContent", "")) for c in args.get("ReplacementChunks") or []
                                                         if isinstance(c, dict))
        return Action("antigravity", "Edit", {"file_path": path, "old_string": args.get("TargetContent", ""), "new_string": new},
                      cwd, session, event, name)
    t = ANTIGRAVITY_TOOLS.get(name)
    if t == "WebFetch":
        return Action("antigravity", t, {"url": args.get("Url") or args.get("url", "")}, cwd, session, event, name)
    if t == "WebSearch":
        return Action("antigravity", t, {"query": args.get("query") or args.get("Query", "")}, cwd, session, event, name)
    if t in {"Read", "LS", "Glob", "Grep"}:
        return Action("antigravity", t, {"file_path": path, "path": path, "pattern": args.get("Query") or args.get("Pattern", "")},
                      cwd, session, event, name)
    if name.startswith("browser_") and args.get("Url"):
        return Action("antigravity", "WebFetch", {"url": args["Url"]}, cwd, session, event, name)
    if t:
        return Action("antigravity", t, args, cwd, session, event, name)
    return Action("antigravity", _mcp("antigravity", name) if name else "", args, cwd, session, event, name)


HERMES_TOOLS = {"search_files": "Grep", "web_search": "WebSearch", "delegate_task": "Task", "memory": "TodoWrite",
                "todo": "TodoWrite", "clarify": "AskUserQuestion"}


def parse_hermes(ev: dict) -> Action:
    name = ev.get("tool_name", "")
    inp = dict(ev.get("tool_input") or {})
    cwd = inp.get("workdir") or ev.get("cwd") or os.getcwd()
    session = ev.get("session_id", "")
    event = "post_tool" if ev.get("hook_event_name") == "post_tool_call" else "pre_tool"
    resp = ev.get("tool_output") or ev.get("result")
    if name == "terminal":
        return Action("hermes", "Bash", {"command": inp.get("command", "")}, cwd, session, event, name, response=resp)
    if name == "execute_code":
        import shlex
        return Action("hermes", "Bash", {"command": f"python3 -c {shlex.quote(str(inp.get('code', '')))}"}, cwd, session, event, name,
                      response=resp)
    if name == "read_file":
        return Action("hermes", "Read", {"file_path": inp.get("path", "")}, cwd, session, event, name, response=resp)
    if name == "write_file":
        return Action("hermes", "Write", {"file_path": inp.get("path", ""), "content": inp.get("content", "")}, cwd, session, event, name)
    if name == "patch":
        if inp.get("mode") == "patch" or (inp.get("patch") and not inp.get("old_string")):
            return Action("hermes", "apply_patch", {"command": inp.get("patch", "")}, cwd, session, event, name)
        return Action("hermes", "Edit", {"file_path": inp.get("path", ""), "old_string": inp.get("old_string", ""),
                                         "new_string": inp.get("new_string", "")}, cwd, session, event, name)
    if name == "web_extract":
        urls = inp.get("urls") or []
        return _multi("hermes", [("WebFetch", {"url": u}) for u in urls] or [("WebFetch", {"url": ""})], cwd, session, name)
    if name == "browser_navigate":
        return Action("hermes", "WebFetch", {"url": inp.get("url", "")}, cwd, session, event, name)
    if name == "search_files":
        return Action("hermes", "Grep", {"pattern": inp.get("pattern", ""), "path": inp.get("path") or cwd, "glob": inp.get("file_glob", "")},
                      cwd, session, event, name)
    if name in HERMES_TOOLS:
        return Action("hermes", HERMES_TOOLS[name], inp, cwd, session, event, name)
    return Action("hermes", _mcp("hermes", name) if name else "", inp, cwd, session, event, name, response=resp)


OPENCLAW_TOOLS = {"read": "Read", "write": "Write", "web_fetch": "WebFetch", "web_search": "WebSearch", "spawn_agent": "Task",
                  "message": "AskUserQuestion"}


def parse_openclaw(ev: dict) -> Action:
    name = ev.get("tool", "")
    a = dict(ev.get("args") or {})
    cwd = a.get("workdir") or ev.get("cwd") or os.getcwd()
    session = ev.get("sessionID", "")
    event = EVENT_MAP.get(ev.get("event", "pre"), "pre_tool")
    if event == "prompt":
        return Action("openclaw", "", {}, cwd, session, "prompt", name, ev.get("prompt", ""))
    if event == "post_tool":
        return Action("openclaw", name, {}, cwd, session, "post_tool", name, response=ev.get("output"))
    if name in {"exec", "bash"}:
        return Action("openclaw", "Bash", {"command": a.get("command", "")}, cwd, session, event, name)
    if name == "read":
        return Action("openclaw", "Read", {"file_path": a.get("path", "")}, cwd, session, event, name)
    if name == "write":
        return Action("openclaw", "Write", {"file_path": a.get("path", ""), "content": a.get("content", "")}, cwd, session, event, name)
    if name == "edit":
        edits = a.get("edits") or [{"oldText": a.get("oldText", ""), "newText": a.get("newText", "")}]
        return Action("openclaw", "Edit", {"file_path": a.get("path", ""), "old_string": "\n".join(str(e.get("oldText", "")) for e in edits),
                                           "new_string": "\n".join(str(e.get("newText", "")) for e in edits)}, cwd, session, event, name)
    if name == "apply_patch":
        return Action("openclaw", "apply_patch", {"command": a.get("input", "")}, cwd, session, event, name)
    if name == "browser" and a.get("url"):
        return Action("openclaw", "WebFetch", {"url": a["url"]}, cwd, session, event, name)
    if name == "web_fetch":
        return Action("openclaw", "WebFetch", {"url": a.get("url", "")}, cwd, session, event, name)
    if name in OPENCLAW_TOOLS:
        return Action("openclaw", OPENCLAW_TOOLS[name], a, cwd, session, event, name)
    return Action("openclaw", _mcp("openclaw", name) if name else "", a, cwd, session, event, name)


def parse(agent: str, ev: dict) -> Action:
    special = {"cursor": parse_cursor, "cline": parse_cline, "antigravity": parse_antigravity, "hermes": parse_hermes,
               "openclaw": parse_openclaw}
    if agent in special:
        return special[agent](ev)
    if agent == "zcode":  # ZCode speaks Claude Code's hook protocol
        a = parse("claude", ev)
        a.agent = "zcode"
        return a
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
        if tool == "Grep":
            inp.setdefault("output_mode", "content")  # OpenCode's grep returns matching lines
            if inp.get("include"):
                inp.setdefault("glob", inp["include"])
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
    special = {"cursor": render_cursor, "cline": render_cline, "antigravity": render_antigravity, "hermes": render_hermes}
    if agent in special:
        return special[agent](action, d, context)
    if agent == "openclaw":
        agent = "opencode"  # the Senti plugin for OpenClaw uses the same compact {verdict, reason, updatedInput} reply
    if agent == "zcode":
        agent = "claude"
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


def render_cursor(action: Action, d: Decision | None, context: str | None) -> str:
    if action.event == "prompt":
        return json.dumps({"continue": True})
    if action.event == "post_tool":
        return json.dumps({"additional_context": context}) if context else json.dumps({})
    assert d is not None
    perm = {"allow": "allow", "ask": "ask", "block": "deny"}[d.verdict]
    out = {"permission": perm, "user_message": voice(d), "agent_message": voice(d)}
    if d.verdict == "allow" and d.meta.get("updated_input"):
        out["updated_input"] = d.meta["updated_input"]
    return json.dumps(out)


def render_cline(action: Action, d: Decision | None, context: str | None) -> str:
    if action.event != "pre_tool":
        out: dict = {"cancel": False}
        if context:
            out["contextModification"] = out["context"] = context
        return json.dumps(out)
    assert d is not None
    if d.verdict == "allow":
        out = {"cancel": False}
        if d.meta.get("updated_input"):
            out["overrideInput"] = d.meta["updated_input"]
        return json.dumps(out)
    return json.dumps({"cancel": True, "errorMessage": voice(d)})


def render_antigravity(action: Action, d: Decision | None, context: str | None) -> str:
    if action.event != "pre_tool":
        return json.dumps({})
    assert d is not None
    out = {"decision": {"allow": "allow", "ask": "ask", "block": "deny"}[d.verdict], "reason": voice(d)}
    return json.dumps(out)


def render_hermes(action: Action, d: Decision | None, context: str | None) -> str:
    if action.event != "pre_tool":
        return json.dumps({})
    assert d is not None
    if d.verdict == "block":
        return json.dumps({"decision": "block", "reason": voice(d)})
    if d.verdict == "ask":  # Hermes' own human-approval gate; denial or timeout there counts as a block
        return json.dumps({"action": "approve", "message": voice(d), "rule_key": f"senti:{d.rule or 'ask'}"})
    if d.meta.get("updated_input"):
        return json.dumps({"action": "modify", "args": {**(action.input or {}), **d.meta["updated_input"]}})
    return json.dumps({})
