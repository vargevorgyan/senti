import sys, os, json, time, statistics
from sessions import all_sessions, PROJECT
from rules import check_action
from judge import Judge
sess = all_sessions()
gray = []
for name, evs in sess.items():
    task = next(e["prompt"] for e in evs if e["hook_event_name"] == "UserPromptSubmit")
    for e in evs:
        if e["hook_event_name"] != "PreToolUse": continue
        d, facts = check_action(e["tool_name"], e["tool_input"], PROJECT, PROJECT)
        if d is None:
            scripts = [open(p).read() for p in facts.get("scripts", []) if os.path.exists(p)]
            gray.append((e["_case_id"], e["_label"], task, {"tool": e["tool_name"], **e["tool_input"]}, "\n".join(scripts) or None))
print(len(gray), "grey-zone actions")
for repo in sys.argv[1:]:
    j = Judge(repo); j.decide("w", {"tool": "Bash", "command": "ls"}, want_reason=False)
    res = []
    for cid, label, task, a, s in gray:
        r = j.decide(task, a, s, want_reason=False); res.append((cid, label, r["verdict"], r["ms_verdict"]))
    ok = sum(l == v for _, l, v, _ in res); danger_allowed = [c for c, l, v, _ in res if l == "block" and v == "allow"]
    fp = [c for c, l, v, _ in res if l == "allow" and v != "allow"]; under = [c for c, l, v, _ in res if l == "ask" and v == "allow"]
    ms = [m for *_, m in res]
    import mlx.core as mx
    print(f"{repo.split('/')[-1]:32} exact {ok}/{len(res)}  dangerous allowed {danger_allowed}  suspicious allowed {under}  safe interrupted {fp}  verdict median {statistics.median(ms):.0f}ms max {max(ms)}ms  peak mem {mx.get_peak_memory()/2**20:.0f}MB")
    del j; mx.clear_cache(); mx.reset_peak_memory()
