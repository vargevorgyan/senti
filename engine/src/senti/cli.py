"""`senti` command line: run the engine, install hooks, enroll, inspect decisions, undo, honeytokens, sandbox."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

from .config import Settings, ensure_dirs, senti_home, socket_path


def _client() -> httpx.Client:
    from .config import hook_token
    return httpx.Client(transport=httpx.HTTPTransport(uds=socket_path()), base_url="http://senti", timeout=30,
                        headers={"X-Senti-Token": hook_token()})


def _running() -> bool:
    try:
        with _client() as c:
            return c.get("/v1/status", timeout=2).status_code == 200
    except Exception:
        return False


def cmd_start(a) -> int:
    if a.foreground:
        from .server import run
        run(use_llm=not a.no_llm)
        return 0
    if _running():
        print("Senti is already running.")
        return 0
    ensure_dirs()
    log = open(senti_home() / "engine.log", "a")
    argv = [sys.executable, "-m", "senti.cli", "start", "--foreground"] + (["--no-llm"] if a.no_llm else [])
    subprocess.Popen(argv, stdout=log, stderr=log, start_new_session=True, env=os.environ.copy())
    for _ in range(100):
        if _running():
            print(f"Senti started (socket {socket_path()}). The local judge loads in the background.")
            return 0
        time.sleep(0.1)
    print(f"Senti did not start; see {senti_home() / 'engine.log'}", file=sys.stderr)
    return 1


def cmd_stop(a) -> int:
    pidf = senti_home() / "senti.pid"
    if not pidf.exists():
        print("Senti is not running.")
        return 0
    try:
        os.kill(int(pidf.read_text()), signal.SIGTERM)
        print("Senti stopped. Note: agents with Senti hooks will now ask/deny every action (fail closed).")
    except ProcessLookupError:
        print("Senti was not running.")
    pidf.unlink(missing_ok=True)
    return 0


def cmd_status(a) -> int:
    if not _running():
        print("Senti engine: NOT RUNNING (agents with Senti hooks fail closed)")
        return 1
    with _client() as c:
        st = c.get("/v1/status").json()
    if a.json:
        print(json.dumps(st, indent=2))
        return 0
    b, lj, pr = st["backend"], st["local_judge"], st["profiles"]
    print(f"Senti {st['version']} · up {st['uptime_s']}s")
    print(f"  organization : {b['org'] or '-'} ({b['state']}{', ' + b['error'] if b['error'] else ''}) user={b['user'] or '-'}")
    print(f"  profiles     : {pr['source']} default={pr['default']} assignments={pr['assignments']}")
    print(f"  local judge  : {lj['state']} ({lj['model']}){' ' + lj['error'] if lj['error'] else ''}")
    print(f"  corporate    : {'configured' if st['corporate_judge']['configured'] else 'not configured'}")
    s = st["stats"]
    print(f"  decisions    : {s['decisions']} (allow {s['allow']} · ask {s['ask']} · block {s['block']} · judged by LLM {s['llm']})")
    print(f"  honeytokens  : {st['honeytokens']}")
    return 0


def cmd_install(a) -> int:
    from . import installers
    hb = installers.hook_binary()
    if not hb.exists() or a.rebuild:
        print("Building the hook client ...")
        installers.build_hook()
    from .agents import hook_agents
    agents = hook_agents() if a.agent == "all" else [a.agent]
    for ag in agents:
        if a.project and ag in {"hermes", "openclaw"}:
            print(f"  {ag:11s} skipped: it only reads user-level settings (install without --project)")
            continue
        if ag == "claude" and a.sandbox:
            from . import sandbox as sbx
            from .rules import project_root
            srt = sbx.srt_settings(_profile_for("claude"), "claude", project_root(a.project or os.getcwd()))
            p = installers.install_claude(a.project, sandbox=srt)
            print(f"  {ag:9s} → {p} (with Claude Code's built-in Bash sandbox from the active profile)")
            continue
        p = installers.INSTALL[ag](a.project)
        print(f"  {ag:11s} → {p}")
    if a.sandbox:
        print("  sandbox: Codex runs commands in its own sandbox (use -s workspace-write); for OpenCode add "
              '`eval "$(senti shell-init)"` to your shell profile so it starts inside Senti\'s sandbox.')
    if "codex" in agents:
        print("  note: Codex asks you to trust new hooks once (run `codex`, then /hooks). For `codex exec` use "
              "--dangerously-bypass-hook-trust in tests.")
    if not _running():
        print("Start the engine with `senti start` (or `senti service install` to run at login).")
    return 0


def cmd_uninstall(a) -> int:
    from . import installers
    from .agents import hook_agents
    agents = hook_agents() if a.agent == "all" else [a.agent]
    for ag in agents:
        if a.project and ag in {"hermes", "openclaw"}:
            continue
        print(f"  {ag:11s} ✕ {installers.UNINSTALL[ag](a.project)}")
    return 0


def cmd_service(a) -> int:
    from . import installers
    if a.action == "install":
        exe = str(Path(sys.executable).with_name("senti"))
        print(f"LaunchAgent written: {installers.install_service(exe)}")
    else:
        installers.uninstall_service()
        print("LaunchAgent removed.")
    return 0


def cmd_enroll(a) -> int:
    from .sync import enroll
    s = enroll(a.backend, a.code, a.email, a.fingerprint, a.insecure_http)
    print(f"Enrolled in {s.org_name or 'organization'} as {s.user_email} (device {s.device_id}).")
    if _running():
        print("Restart the engine to connect: senti stop && senti start")
    return 0


def cmd_unenroll(a) -> int:
    s = Settings.load()
    s.backend_url = s.device_token = s.device_id = s.backend_public_key = s.org_name = s.backend_cert = ""
    s.save()
    (senti_home() / "profiles.signed.json").unlink(missing_ok=True)
    print("Left the organization; back to the built-in personal profile. Restart the engine.")
    return 0


def _fmt(r: dict) -> str:
    t = time.strftime("%H:%M:%S", time.localtime(r.get("ts", 0)))
    v = r.get("verdict") or r.get("event", "")
    inp = r.get("input") or {}
    what = inp.get("command") or inp.get("file_path") or inp.get("url") or inp.get("filePath") or ""
    if str(what).startswith("*** Begin Patch"):
        import re as _re
        what = "patch: " + ", ".join(m.group(2) for m in _re.finditer(r"\*\*\* (Add|Update|Delete) File: (\S+)", what))
    return f"{t} {v:6s} {r.get('agent', ''):8s} {r.get('tool', ''):10s} {str(what)[:70]:70s} {r.get('layer', '')} · {r.get('reason', '')}"


def cmd_log(a) -> int:
    from .audit import AuditLog
    log = AuditLog()
    for r in log.recent[-a.n:]:
        print(_fmt(r))
    if a.follow:
        with open(log.path) as f:
            f.seek(0, 2)
            while True:
                ln = f.readline()
                if not ln:
                    time.sleep(0.3)
                    continue
                print(_fmt(json.loads(ln)), flush=True)
    return 0


def cmd_audit(a) -> int:
    from .audit import AuditLog
    ok, n, err = AuditLog().verify()
    print(f"audit log: {'OK' if ok else 'TAMPERED'} · {n} records {err}")
    return 0 if ok else 2


def cmd_undo(a) -> int:
    from . import undo
    if a.action == "list":
        for m in undo.list_snapshots(a.n):
            t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(m["created"]))
            files = ", ".join(i["original"].replace(str(Path.home()), "~") for i in m.get("items", [])[:3])
            print(f"{m['id']}  {t}  {m.get('agent', '')}/{m.get('tool', '')}  {files}{' (restored)' if m.get('restored_at') else ''}")
        return 0
    for p in undo.restore(a.id):
        print(f"restored {p}")
    return 0


def cmd_honeytoken(a) -> int:
    from . import honeytokens
    if a.action == "plant":
        print(f"planted decoy: {honeytokens.plant(a.path)}")
    elif a.action == "remove":
        print("removed" if honeytokens.remove(os.path.abspath(a.path)) else "not a Senti decoy")
    else:
        for f in honeytokens.load()["files"]:
            print(f["path"])
    if _running():
        with _client() as c:
            c.post("/v1/reload")
    return 0


def _profile_for(agent: str) -> dict:
    from .profiles import ProfileSet, load_cached
    s = Settings.load()
    if s.enrolled:
        from .profiles import STRICT_PROFILE
        ps = load_cached(s.backend_public_key, s.device_id) or ProfileSet(profiles={"strict-offline": STRICT_PROFILE},
                                                                           default="strict-offline")
    else:
        ps = ProfileSet()
    return ps.for_agent(agent)


def cmd_sandbox(a) -> int:
    from . import sandbox
    from .rules import project_root
    p = sandbox.write_settings(_profile_for(a.agent), a.agent, project_root(a.project or os.getcwd()))
    print(p)
    if a.show:
        print(p.read_text())
    return 0


def cmd_run(a) -> int:
    from . import sandbox
    from .rules import project_root
    argv = a.argv[1:] if a.argv and a.argv[0] == "--" else a.argv
    if not argv:
        print("usage: senti run --agent codex -- codex ...", file=sys.stderr)
        return 2
    p = sandbox.write_settings(_profile_for(a.agent), a.agent, project_root(os.getcwd()))
    return subprocess.call(sandbox.command(p, argv))


def cmd_shell_init(a) -> int:
    """Print shell functions that launch agents inside their Senti sandbox (eval "$(senti shell-init)")."""
    exe = str(Path(sys.executable).with_name("senti"))
    for agent in a.agents.split(","):
        agent = agent.strip()
        path = shutil.which(agent) if agent else None
        if path:
            print(f'{agent}() {{ "{exe}" run --agent {agent} -- "{path}" "$@"; }}')
        elif agent:
            print(f"# senti: {agent} not found on PATH, not wrapped")
    return 0


def cmd_secret(a) -> int:
    from . import secrets
    if a.action == "add":
        import getpass
        val = sys.stdin.read().strip() if not sys.stdin.isatty() else getpass.getpass(f"Value for {a.name} (hidden): ")
        if not val:
            print("empty value, nothing saved", file=sys.stderr)
            return 1
        secrets.add(a.name, val, a.hosts.split(",") if a.hosts else [])
        print(f"saved {a.name}; agents can use it as {{{{senti:{a.name}}}}} with: {a.hosts or '(no sites yet)'}")
    elif a.action == "remove":
        print("removed" if secrets.remove(a.name) else "no such secret")
    else:
        for n, m in secrets.listing().items():
            print(f"{n:24s} {{{{senti:{n}}}}}  → {', '.join(m['hosts']) or '(no sites)'}")
    return 0


def cmd_check(a) -> int:
    body = {"agent": a.agent, "tool": a.tool, "cwd": a.cwd or os.getcwd(), "session_id": "cli", "task": a.task or ""}
    if a.tool == "Bash":
        body["input"] = {"command": a.value}
    elif a.tool in {"Read", "Write", "Edit"}:
        body["input"] = {"file_path": a.value, "content": a.content or ""}
    elif a.tool == "WebFetch":
        body["input"] = {"url": a.value}
    else:
        body["input"] = json.loads(a.value or "{}")
    with _client() as c:
        print(json.dumps(c.post("/v1/check", json=body).json(), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="senti", description="Senti: a local guardrail for AI agents")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start", help="start the local engine")
    s.add_argument("--foreground", action="store_true")
    s.add_argument("--no-llm", action="store_true", help="rules only; unclear actions are asked about")
    s.set_defaults(fn=cmd_start)
    sub.add_parser("stop").set_defaults(fn=cmd_stop)
    s = sub.add_parser("status")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_status)
    for name, fn in (("install", cmd_install), ("uninstall", cmd_uninstall)):
        s = sub.add_parser(name, help=f"{name} hooks for an agent")
        s.add_argument("agent", choices=["claude", "codex", "opencode", "cursor", "cline", "hermes", "openclaw", "all"])
        s.add_argument("--project", help="install into a project instead of user-wide")
        if name == "install":
            s.add_argument("--rebuild", action="store_true", help="recompile the hook client")
            s.add_argument("--sandbox", action="store_true", help="also enable OS sandboxing (Claude Code built-in sandbox; hints for others)")
        s.set_defaults(fn=fn)
    s = sub.add_parser("service", help="run Senti at login (LaunchAgent)")
    s.add_argument("action", choices=["install", "uninstall"])
    s.set_defaults(fn=cmd_service)
    s = sub.add_parser("enroll", help="join an organization")
    s.add_argument("--backend", required=True)
    s.add_argument("--code", required=True)
    s.add_argument("--email", required=True)
    s.add_argument("--fingerprint", default="", help="SHA-256 fingerprint of the backend's TLS certificate (shown on the Devices page)")
    s.add_argument("--insecure-http", action="store_true", help="allow plain HTTP to a non-local backend (lab only)")
    s.set_defaults(fn=cmd_enroll)
    sub.add_parser("unenroll").set_defaults(fn=cmd_unenroll)
    s = sub.add_parser("log", help="recent decisions")
    s.add_argument("-n", type=int, default=30)
    s.add_argument("-f", "--follow", action="store_true")
    s.set_defaults(fn=cmd_log)
    s = sub.add_parser("audit", help="verify the tamper-evident audit log")
    s.add_argument("action", choices=["verify"])
    s.set_defaults(fn=cmd_audit)
    s = sub.add_parser("undo", help="list / restore snapshots taken before destructive actions")
    s.add_argument("action", choices=["list", "restore"])
    s.add_argument("id", nargs="?")
    s.add_argument("-n", type=int, default=20)
    s.set_defaults(fn=cmd_undo)
    s = sub.add_parser("honeytoken", help="plant / list / remove decoy secrets")
    s.add_argument("action", choices=["plant", "list", "remove"])
    s.add_argument("path", nargs="?", default=".")
    s.set_defaults(fn=cmd_honeytoken)
    s = sub.add_parser("sandbox", help="write the sandbox-runtime settings for an agent")
    s.add_argument("--agent", default="claude")
    s.add_argument("--project")
    s.add_argument("--show", action="store_true")
    s.set_defaults(fn=cmd_sandbox)
    s = sub.add_parser("run", help="run a command inside the agent's sandbox: senti run --agent codex -- codex")
    s.add_argument("--agent", default="generic")
    s.add_argument("argv", nargs=argparse.REMAINDER)
    s.set_defaults(fn=cmd_run)
    s = sub.add_parser("shell-init", help='print shell functions that sandbox agents: eval "$(senti shell-init)"')
    s.add_argument("--agents", default="opencode", help="comma-separated agent commands to wrap (default: opencode)")
    s.set_defaults(fn=cmd_shell_init)
    s = sub.add_parser("secret", help="broker secrets: agents use {{senti:NAME}}, the value is injected only when running")
    s.add_argument("action", choices=["add", "list", "remove"])
    s.add_argument("name", nargs="?")
    s.add_argument("--hosts", default="", help="comma-separated sites the secret may be sent to, e.g. api.stripe.com")
    s.set_defaults(fn=cmd_secret)
    s = sub.add_parser("check", help="ask the engine about one action")
    s.add_argument("tool")
    s.add_argument("value")
    s.add_argument("--agent", default="generic")
    s.add_argument("--cwd")
    s.add_argument("--task")
    s.add_argument("--content")
    s.set_defaults(fn=cmd_check)
    a = ap.parse_args(argv)
    return a.fn(a) or 0


if __name__ == "__main__":
    sys.exit(main())
