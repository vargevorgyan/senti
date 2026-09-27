import os

from senti import identity
from senti.config import Settings
from senti.engine import Engine
from senti.models import Action
from senti.profiles import PERSONAL_PROFILE, ProfileSet


def chain(*names, cmd=None):
    return [{"pid": i + 10, "name": n, "exe": f"/usr/bin/{n}", "cmdline": (cmd or {}).get(n, [n])} for i, n in enumerate(names)]


def test_agents_in_chain():
    assert identity.agents_in(chain("senti-hook", "claude", "zsh")) == {"claude"}
    assert identity.agents_in(chain("senti-hook", "python3", "zsh")) == set()
    assert identity.agents_in(chain("senti-hook", "node", cmd={"node": ["node", "/opt/opencode/bin/opencode"]})) == {"opencode"}


def test_sandbox_detection(tmp_path):
    assert identity.sandboxed_chain(chain("sh", "sandbox-exec", "opencode"))
    assert identity.sandbox_status("codex", chain("senti-hook", "codex"), str(tmp_path)) is True
    c = chain("senti-hook", "codex", cmd={"codex": ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox"]})
    assert identity.sandbox_status("codex", c, str(tmp_path)) is False
    assert identity.sandbox_status("opencode", chain("senti-hook", "opencode"), str(tmp_path)) is False


def test_real_peer_pid_of_this_process():
    import socket
    a, b = socket.socketpair(socket.AF_UNIX)
    pid = identity.peer_pid(a)
    assert pid in (os.getpid(), None)
    info = identity.identify("claude", os.getpid(), "/tmp")
    # true when the test suite itself runs under Claude Code, false otherwise; the chain is always reported
    assert info["verified"] == ("claude" in info["agents_in_chain"]) and info["chain"]


def _engine(project):
    e = Engine(Settings(local_judge=False), use_llm=False)
    return e


async def test_unverified_agent_is_asked(project):
    e = _engine(project)
    a = Action("claude", "Bash", {"command": "ls"}, project, "s")
    a.identity = {"verified": False, "chain": ["senti-hook", "python3"], "sandboxed": None}
    r = await e.handle(a)
    assert r["decision"].verdict == "ask" and r["decision"].rule == "unverified_agent"
    a.identity = {"verified": True, "chain": ["senti-hook", "claude"], "sandboxed": True}
    assert (await e.handle(a))["decision"].verdict == "allow"


async def test_sandbox_required(project):
    e = _engine(project)
    e.profiles = ProfileSet(profiles={"personal": {**PERSONAL_PROFILE, "features": {**PERSONAL_PROFILE["features"], "sandbox": True}}})
    a = Action("opencode", "Bash", {"command": "ls"}, project, "s")
    a.identity = {"verified": True, "chain": ["senti-hook", "opencode"], "sandboxed": False}
    r = await e.handle(a)
    assert r["decision"].rule == "sandbox_required"
    a.identity["sandboxed"] = True
    assert (await e.handle(a))["decision"].verdict == "allow"
    # reading files is not affected by the sandbox requirement
    a2 = Action("opencode", "Read", {"file_path": "README.md"}, project, "s", identity={"verified": True, "sandboxed": False})
    assert (await e.handle(a2))["decision"].verdict == "allow"


def test_agent_cannot_stop_senti(project):
    from senti.rules import check_bash
    for cmd in ["senti stop", "uv run senti uninstall claude", "~/.venv/bin/senti unenroll"]:
        d, _ = check_bash(cmd, project, project)
        assert d and d.verdict == "block", cmd
