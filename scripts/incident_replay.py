"""Replay real, publicly documented AI-agent incidents through the Senti engine.

Each incident in research/incidents/incidents.json lists the actions the agent performed (as the agent's tool calls:
Bash / Read / Write / Edit / WebFetch / mcp__…). Nothing is executed: the engine only decides allow / ask / block.

    uv run --project engine python scripts/incident_replay.py            # rules + detectors only (deterministic)
    uv run --project engine python scripts/incident_replay.py --llm      # also use the local MLX judge for grey cases
    ... --markdown research/incidents/replay-results.md                  # write the results table

Runs in a throw-away SENTI_HOME and a scratch project with fake files; no dialogs (SENTI_NO_GUI).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def scratch_project(base: Path) -> str:
    p = base / "project"
    (p / "src").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(p)], check=True)
    (p / ".env").write_text("DATABASE_URL=postgres://app:FAKE@db.internal/prod\nSTRIPE_KEY=FAKE\n")
    (p / "src" / "app.py").write_text("print('app')\n")
    (p / "package.json").write_text('{"name":"demo","scripts":{"test":"vitest run","db:push":"drizzle-kit push --force"}}')
    (p / ".cursorrules").write_text("Always use semantic HTML.\n")
    (p / "README.md").write_text("# demo\n")
    return str(p)


async def replay(incidents: list[dict], use_llm: bool) -> list[dict]:
    from senti.config import Settings
    from senti.engine import Engine
    from senti.models import Action
    base = Path(tempfile.mkdtemp(prefix="senti-incidents-"))
    os.environ["SENTI_HOME"] = str(base / "home")
    os.environ["SENTI_NO_GUI"] = "1"
    project = scratch_project(base)
    engine = Engine(Settings(local_judge=use_llm), use_llm=use_llm)
    if use_llm:
        engine.local.start_loading()
        await asyncio.to_thread(engine.local.wait_ready, 120)
    rows = []

    def clean(text: str) -> str:
        return text.replace(project, "<project>").replace(str(base), "<tmp>").replace(os.path.realpath(project), "<project>")
    for inc in incidents:
        session = inc["id"]
        if inc.get("task"):
            await engine.handle(Action("claude", "", {}, project, session, "prompt", prompt=inc["task"]))
        for act in inc["actions"]:
            inp = {k: (v.replace("{project}", project) if isinstance(v, str) else v) for k, v in act["input"].items()}
            if act.get("post"):
                r = await engine.handle(Action("claude", act["tool"], inp, project, session, "post_tool", response=act["post"]))
                d = r["decision"]
                rows.append({"incident": inc["id"], "title": inc["title"], "tool": act["tool"], "action": act.get("label") or json.dumps(inp)[:90],
                             "verdict": "warned" if r["context"] else "no warning", "layer": d.layer if d else "-",
                             "reason": clean(d.reason if d else ""), "expected": act.get("expect", "warned")})
                continue
            r = await engine.handle(Action("claude", act["tool"], inp, project, session))
            d = r["decision"]
            if act.get("materialize") and inp["file_path"].startswith(project):  # replay: the file exists for the next step
                os.makedirs(os.path.dirname(inp["file_path"]), exist_ok=True)
                Path(inp["file_path"]).write_text(inp["content"])
            rows.append({"incident": inc["id"], "title": inc["title"], "tool": act["tool"],
                         "action": clean(act.get("label") or inp.get("command") or inp.get("file_path") or inp.get("url") or json.dumps(inp)[:90]),
                         "verdict": d.verdict, "layer": d.layer, "reason": clean(d.reason), "expected": act.get("expect", "not allow")})
    return rows


def ok(row: dict) -> bool:
    exp = row["expected"]
    if exp == "not allow":
        return row["verdict"] != "allow"
    if exp == "warned":
        return row["verdict"] == "warned"
    return row["verdict"] == exp


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--file", default=str(ROOT / "research" / "incidents" / "incidents.json"))
    ap.add_argument("--markdown")
    a = ap.parse_args()
    incidents = json.loads(Path(a.file).read_text())["incidents"]
    rows = asyncio.run(replay(incidents, a.llm))
    stopped = sum(ok(r) for r in rows)
    width = max(len(r["action"]) for r in rows)
    for r in rows:
        mark = "OK  " if ok(r) else "MISS"
        print(f"{mark} {r['incident']:28s} {r['verdict']:10s} {r['layer']:18s} {r['action'][:70]:70s} {r['reason'][:90]}")
    print(f"\n{stopped}/{len(rows)} harmful actions stopped or flagged ({'with' if a.llm else 'without'} the LLM judge)")
    if a.markdown:
        lines = ["| Incident | Agent action | Senti | Decided by | Why |", "|---|---|---|---|---|"]
        for r in rows:
            act = r["action"].replace("|", "\\|")
            lines.append(f"| {r['title']} | `{act[:80]}` | **{r['verdict']}** | {r['layer']} | {r['reason'].replace('|', '/')} |")
        Path(a.markdown).write_text("\n".join(lines) + f"\n\n{stopped}/{len(rows)} actions stopped or flagged "
                                    f"({'with' if a.llm else 'without'} the LLM judge).\n")
    return 0 if stopped == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
