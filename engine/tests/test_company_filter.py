"""Company Macs: no model on the Mac; unclear actions go to the organization's cloud AI filter through the hook."""
import asyncio

from senti.config import Settings
from senti.engine import Action, Engine
from senti.judge.base import JudgeResult
from senti.profiles import PERSONAL_PROFILE, ProfileSet


class Remote:
    last_error = ""

    def __init__(self, verdict="allow"):
        self.verdict, self.seen = verdict, []

    async def decide(self, profile_id, task, action, script, facts):
        self.seen.append({"profile": profile_id, "action": action, "script": script})
        return JudgeResult(self.verdict, "company AI says so", {self.verdict: 0.99}, "corporate", "company-model", 5)


def company_mac(mode: str, verdict: str = "allow", **judge) -> Engine:
    s = Settings(backend_url="https://senti.acme:8443", device_token="sdt_x", device_id="d1", backend_public_key="pk")
    e = Engine(s, use_llm=True)  # the model is installed, but a company Mac must not use it
    e.remote, e.backend_state = Remote(verdict), "online"
    prof = {**PERSONAL_PROFILE, "id": "dev", "judge": {"mode": mode, **judge}}
    e.profiles = ProfileSet(profiles={"dev": prof}, default="dev")
    return e


def act(tool, inp, cwd):
    return Action("claude", tool, inp, cwd, "s")


def test_company_mac_never_loads_a_local_model():
    e = company_mac("corporate")
    assert e.local.state == "unavailable" and "company" in e.local.error
    e.local.start_loading()
    assert e.local.state == "unavailable"


async def test_local_profiles_use_the_company_filter_on_company_macs(project):
    for mode in ("local", "local_then_corporate", "corporate"):
        e = company_mac(mode, "block")
        r = await e.handle(act("Bash", {"command": "python3 gen.py"}, project))
        assert r["decision"].layer == "L3-llm-corporate" and r["decision"].verdict == "block", mode


async def test_script_reaches_the_company_filter_with_secrets_redacted(project):
    import pathlib
    pathlib.Path(project, "gen.py").write_text("KEY='AKIAABCDEFGHIJKLMNOP'\nprint('hi')\n")
    e = company_mac("corporate")
    await e.handle(act("Bash", {"command": "python3 gen.py"}, project))
    script = e.remote.seen[-1]["script"]
    assert script and "print('hi')" in script and "AKIAABCDEFGHIJKLMNOP" not in script


async def test_obvious_actions_never_leave_the_mac(project):
    e = company_mac("corporate")
    assert (await e.handle(act("Bash", {"command": "git status"}, project)))["decision"].verdict == "allow"
    assert (await e.handle(act("Read", {"file_path": "~/.ssh/id_rsa"}, project)))["decision"].verdict == "block"
    assert e.remote.seen == [], "rules decide these on the Mac in milliseconds"


async def test_scripts_are_prechecked_by_the_company_filter_when_written(project):
    e = company_mac("corporate", "block")
    code = "import os\nprint(os.getcwd())\n"
    await e.handle(act("Write", {"file_path": f"{project}/tool.py", "content": code}, project))
    await asyncio.gather(*list(e.background))  # the pre-check runs in the background
    assert e.remote.seen and "print(os.getcwd())" in (e.remote.seen[-1]["script"] or "")
    import pathlib
    pathlib.Path(project, "tool.py").write_text(code)
    before = len(e.remote.seen)
    r = await e.handle(act("Bash", {"command": "python3 tool.py"}, project))
    assert r["decision"].layer == "L0-prefetch" and r["decision"].verdict == "block"
    assert len(e.remote.seen) == before, "the verdict from write time is reused, no second round trip"


async def test_filter_unreachable_still_fails_closed(project):
    e = company_mac("corporate")
    e.remote, e.backend_state = None, "unreachable"
    r = await e.handle(act("Bash", {"command": "python3 gen.py"}, project))
    assert r["decision"].verdict in {"ask", "block"}
