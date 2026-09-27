"""Everything the server gateway does with the shared files, commands and database.

This runs in the isolated runner container (`python -m app.runner`): it has the shared folder and nothing else — no signing
key, no admin database, no secrets, no network, not root. The backend decides *who* may call *what* (tokens, role, rate
limits, the supervisor model) and sends each call here over a Unix socket. So a command that slips past the rules still
can't reach the organization's keys.

Two phases per call: "check" answers what the rules say (allow / block / supervisor); "exec" re-checks at run time (a
block is never executed, whatever the backend says) and performs the call. SQL is decided while it runs (SQLite's
authorizer), so query_db is checked and executed in one step.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import settings
from .gateway_policy import (CompiledPolicy, GatewayDecision, RolePolicy, check_command, check_path, resolve_path, run_sql,
                             visible)
from .gateway_policy import run_command as execute_command

TOOLS = {"list_files", "read_file", "write_file", "run_command", "query_db"}
MAX_WRITE = 1_000_000
DB_SUFFIXES = (".db", ".sqlite", ".sqlite3")
BROWSE_DEPTH, BROWSE_MAX = 4, 400


def share() -> Path | None:
    return Path(settings.gateway_share).resolve() if settings.gateway_share else None


def inside_share(rel: str) -> Path:
    """A path the admin picked, relative to the shared host folder. Anything that resolves outside it is refused."""
    base = share()
    if base is None:
        raise ValueError("no shared folder is mounted (SENTI_GATEWAY_SHARE)")
    rel = (rel or ".").strip()
    if not isinstance(rel, str) or rel.startswith(("/", "~")) or "\x00" in rel or len(rel) > 500:
        raise ValueError("a path inside the shared folder, like tickets or data/app.db")
    p = (base / rel).resolve()
    if p != base and base not in p.parents:
        raise ValueError("outside the shared folder")
    return p


def root(req: dict | None = None) -> Path:
    """The folder agents work in: the admin's choice (sent with each call), or the install default."""
    if req is not None and "folder" in req:
        p = inside_share(str(req["folder"]))
        if not p.is_dir():
            raise ValueError("the chosen folder doesn't exist any more")
        return p
    p = Path(settings.gateway_root_path)
    p.mkdir(parents=True, exist_ok=True)
    return p.resolve()


def db_path(req: dict | None = None) -> str:
    """The SQLite file agents may query ("" = no database), chosen the same way."""
    if req is not None and "database" in req:
        if not req["database"]:
            return ""
        p = inside_share(str(req["database"]))
        if not (p.is_file() and p.suffix.lower() in DB_SUFFIXES):
            raise ValueError("the chosen database file doesn't exist any more")
        return str(p)
    return settings.gateway_db_path


def browse() -> dict:
    """Folders and SQLite files inside the shared host folder, for the admin's picker (hidden entries and links skipped)."""
    base = share()
    if base is None:
        return {"error": "no shared folder is mounted"}
    folders, dbs = ["."], []
    stack = [(base, 0)]
    while stack and len(folders) + len(dbs) < BROWSE_MAX:
        d, depth = stack.pop()
        try:
            entries = sorted(d.iterdir(), reverse=True)
        except OSError:
            continue
        for p in entries:
            if p.name.startswith(".") or p.is_symlink():
                continue
            rel = p.relative_to(base).as_posix()
            if p.is_dir() and depth < BROWSE_DEPTH:
                folders.append(rel)
                stack.append((p, depth + 1))
            elif p.is_file() and p.suffix.lower() in DB_SUFFIXES:
                dbs.append(rel)
    return {"folders": sorted(folders), "databases": sorted(dbs)}


def guard_db_file(role: RolePolicy, r: Path, dbp: str) -> RolePolicy:
    """The database file itself is never readable as a file (that would skip the column rules): deny it outright."""
    if not dbp:
        return role
    p = Path(dbp).resolve()
    if r not in p.parents:
        return role
    rel = p.relative_to(r).as_posix()
    role = role.model_copy(deep=True)
    role.files.deny = [*role.files.deny, rel, f"{rel}-*"]  # plus SQLite's -wal / -journal files
    return role


def decision_json(d: GatewayDecision) -> dict:
    return {"verdict": d.verdict, "reason": d.reason, "layer": d.layer}


def decide(role: RolePolicy, tool: str, arg: str, r: Path, dbp: str) -> tuple[GatewayDecision, dict]:
    if tool == "query_db" and not dbp:
        return GatewayDecision("block", "No database is connected to this server gateway", "hard-rule"), {}
    role = guard_db_file(role, r, dbp)
    if tool == "list_files":
        return check_path(role, r, arg or ".", "list"), {}
    if tool == "read_file":
        return check_path(role, r, arg, "read"), {}
    if tool == "write_file":
        return check_path(role, r, arg, "write"), {}
    if tool == "run_command":
        return check_command(role, r, arg)[0], {}
    d, cols, rows = run_sql(role, dbp, arg)
    return d, ({"columns": cols, "rows": rows} if d.verdict == "allow" else {})


def execute(role: RolePolicy, tool: str, arg: str, content: str, r: Path, dbp: str) -> str:
    role = guard_db_file(role, r, dbp)
    if tool == "list_files":
        real, _ = resolve_path(r, arg or ".")
        if real is None or not real.is_dir():
            return f"'{arg}' is not a folder"
        out = []
        for p in sorted(real.iterdir()):
            rel = p.relative_to(r).as_posix()
            if p.is_symlink() or not visible(role, rel):
                continue
            out.append(f"{rel}{'/' if p.is_dir() else ''}\t{p.stat().st_size if p.is_file() else ''}")
        return "\n".join(out) or "(empty)"
    if tool == "read_file":
        real, _ = resolve_path(r, arg)
        if real is None or not real.is_file():
            return f"'{arg}' is not a file"
        return real.read_bytes()[:200_000].decode("utf-8", errors="replace")
    if tool == "write_file":
        real, rel = resolve_path(r, arg)
        if real is None or real.is_dir():
            return f"'{arg}' can't be written"
        real.parent.mkdir(parents=True, exist_ok=True)
        real.write_text(content[:MAX_WRITE])
        return f"Wrote {min(len(content), MAX_WRITE)} characters to {rel}"
    d, argv = check_command(role, r, arg)
    return execute_command(r, argv, settings.gateway_cmd_timeout_s)


def handle(req: dict[str, Any]) -> dict[str, Any]:
    """One request from the backend → one JSON-serialisable answer. Anything unexpected is an error (the backend then
    blocks the call)."""
    from . import policy_compiler
    op = req.get("op")
    if op == "browse":
        return browse()
    try:
        r, dbp = root(req), db_path(req)
    except ValueError as e:
        return {"error": str(e)}
    if op == "inventory":
        return {"text": policy_compiler.inventory(r, dbp)}
    if op == "db_schema":
        return {"schema": {t: sorted(c) for t, c in policy_compiler.db_schema(dbp).items()}}
    if op == "evaluate":
        policy = CompiledPolicy.model_validate(req.get("policy") or {})
        return {"results": policy_compiler.evaluate_examples(policy, list(req.get("examples") or []), r, dbp)}
    tool, arg = req.get("tool"), req.get("arg", "")
    if op not in {"check", "exec"} or tool not in TOOLS or not isinstance(arg, str):
        return {"error": "bad request"}
    role = RolePolicy.model_validate(req.get("role") or {})
    d, extra = decide(role, tool, arg, r, dbp)
    if op == "check" or d.verdict == "block":
        return {"decision": decision_json(d), **extra}
    if tool == "query_db":
        return {"error": "query_db runs in the check step"}
    content = req.get("content") or ""
    if not isinstance(content, str):
        return {"error": "bad request"}
    return {"decision": decision_json(d), "output": execute(role, tool, arg, content, r, dbp)}
