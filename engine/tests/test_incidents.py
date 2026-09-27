"""Every harmful action from real, documented AI-agent incidents must be stopped or flagged — by rules, without the LLM.
Incident catalog and sources: research/incidents/incidents.json, .okf/research/agent-incidents.md."""
import json
import os
import subprocess
from pathlib import Path

import pytest

from senti.config import Settings
from senti.engine import Engine
from senti.models import Action

INCIDENTS = json.loads((Path(__file__).resolve().parents[2] / "research" / "incidents" / "incidents.json").read_text())["incidents"]
CASES = [(inc, i, act) for inc in INCIDENTS for i, act in enumerate(inc["actions"])]


@pytest.fixture
def incident_project(tmp_path):
    p = tmp_path / "project"
    (p / "src").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(p)], check=True)
    (p / ".env").write_text("DATABASE_URL=postgres://app:FAKE@db.internal/prod\n")
    (p / "package.json").write_text('{"name":"demo","scripts":{"test":"vitest run","db:push":"drizzle-kit push --force"}}')
    (p / ".cursorrules").write_text("Always use semantic HTML.\n")
    return str(p)


@pytest.mark.parametrize("inc,i,act", CASES, ids=[f"{c[0]['id']}-{c[1]}" for c in CASES])
async def test_incident_action_not_silently_allowed(inc, i, act, incident_project):
    e = Engine(Settings(local_judge=False), use_llm=False)
    if inc.get("task"):
        await e.handle(Action("claude", "", {}, incident_project, inc["id"], "prompt", prompt=inc["task"]))
    for prev in inc["actions"][:i]:  # earlier steps of the same incident (e.g. the injected content that was read)
        inp = {k: (v.replace("{project}", incident_project) if isinstance(v, str) else v) for k, v in prev["input"].items()}
        await e.handle(Action("claude", prev["tool"], inp, incident_project, inc["id"], "post_tool" if prev.get("post") else "pre_tool",
                              response=prev.get("post")))
        if prev.get("materialize"):  # the agent wrote this file anyway (e.g. through another tool): only inside the temp project
            path = inp["file_path"]
            assert path.startswith(incident_project)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "w").write(inp["content"])
    inp = {k: (v.replace("{project}", incident_project) if isinstance(v, str) else v) for k, v in act["input"].items()}
    if act.get("post"):
        r = await e.handle(Action("claude", act["tool"], inp, incident_project, inc["id"], "post_tool", response=act["post"]))
        assert r["context"], f"{inc['id']}: injected content was not flagged"
        return
    r = await e.handle(Action("claude", act["tool"], inp, incident_project, inc["id"]))
    d = r["decision"]
    assert d.verdict != "allow", f"{inc['id']}: {act.get('label') or inp} was allowed ({d.reason})"
    assert d.layer != "fallback", f"{inc['id']}: only caught because no judge was available — needs a rule ({act.get('label') or inp})"
