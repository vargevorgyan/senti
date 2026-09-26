import sys; sys.path.insert(0, "../bench")
from judge import Judge
from cases import CASES
sel = [c for c in CASES if c[0] in ("rm_home","git_status","script_hidden_exfil","read_env","npm_test","script_stats_py")]
for pc in (True, False):
    j = Judge(prefix_cache=pc)
    print(f"--- prefix_cache={pc} load {j.load_s:.1f}s prefix {getattr(j,'prefix_s',0):.2f}s prefix_tokens {len(j.prefix_ids)}")
    j.decide("warmup", {"tool":"Bash","command":"ls"})
    for cid, label, a in sel * 2:
        a = dict(a); script = a.pop("script_content", None)
        r = j.decide("General development work on the webapp", a, script)
        print(f"{cid:20} {label:5} -> {r['verdict']:5} p={r['p']} in={r['tokens_in']:4} verdict {r['ms_verdict']:4}ms total {r['ms_total']:5}ms  {r['reason'][:70]}")
    del j
