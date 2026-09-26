"""Replay sessions through the real hook binary (spawned per event, like Claude Code does)."""
import json, subprocess, sys, time, statistics, os
from sessions import all_sessions

SOCK, HOOK = sys.argv[1], sys.argv[2]
OUT = sys.argv[3]
rounds = int(sys.argv[4]) if len(sys.argv) > 4 else 1
THINK = float(sys.argv[5]) if len(sys.argv) > 5 else 0.0  # seconds the agent 'thinks' between actions
MAP = {"allow": "allow", "ask": "ask", "deny": "block"}

rows = []
for r in range(rounds):
    for name, events in all_sessions().items():
        for e in events:
            payload = json.dumps({k: v for k, v in e.items() if k != "_label"}).encode()
            cmd = [HOOK, SOCK] if not HOOK.endswith(".py") else [sys.executable, HOOK, SOCK]
            t = time.perf_counter()
            p = subprocess.run(cmd, input=payload, capture_output=True)
            ms = (time.perf_counter() - t) * 1000
            time.sleep(THINK)
            if e["hook_event_name"] != "PreToolUse":
                continue
            if e["tool_name"] in {"Write", "Edit"}:
                import pathlib; fp = pathlib.Path(e["tool_input"]["file_path"])
                if e["tool_name"] == "Write" and str(fp).startswith(os.path.dirname(os.path.abspath(__file__))):
                    fp.parent.mkdir(parents=True, exist_ok=True); fp.write_text(e["tool_input"]["content"])  # the agent's write happens
            out = json.loads(p.stdout or b"{}").get("hookSpecificOutput", {})
            rows.append({"round": r, "session": name, "id": e["_case_id"], "tool": e["tool_name"], "label": e["_label"],
                         "verdict": MAP.get(out.get("permissionDecision"), "?"),
                         "reason": out.get("permissionDecisionReason", ""), "client_ms": round(ms, 2)})
json.dump(rows, open(OUT, "w"), indent=1)
print(f"{len(rows)} decisions written to {OUT}")
