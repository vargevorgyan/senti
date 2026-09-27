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

import re
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


class Sources:
    """What one call may reach: the root paths are relative to, the exposed folders (scope) and the databases by name."""

    def __init__(self, root: Path, scope: list[str], dbs: dict[str, str]):
        self.root, self.scope, self.dbs = root, scope, dbs


def _db_names(rels: list[str]) -> dict[str, str]:
    """Short names agents use in query_db: the file name without .db (the whole path when two files share a name)."""
    stems = [Path(r).stem.lower() for r in rels]
    return {(st if stems.count(st) == 1 else re.sub(r"[^a-z0-9_]+", "_", r.lower().rsplit(".", 1)[0])): r
            for st, r in zip(stems, rels)}


def sources(req: dict | None = None) -> Sources:
    """The admin's choice, sent with each call ("folders" + "databases", inside the shared host folder), or the install
    default. Chosen folders or files that no longer exist are dropped: less access, never more."""
    req = req or {}
    if "folder" in req or "database" in req:  # older single-choice form
        req = {"folders": [req.get("folder", ".")], "databases": [req["database"]] if req.get("database") else []}
    if "folders" not in req and "databases" not in req:
        p = Path(settings.gateway_root_path)
        p.mkdir(parents=True, exist_ok=True)
        return Sources(p.resolve(), [], {"server": settings.gateway_db_path})
    base = share()
    if base is None:
        raise ValueError("no shared folder is mounted (SENTI_GATEWAY_SHARE)")
    scope = []
    for f in req.get("folders") or []:
        p = inside_share(str(f))
        if p.is_dir():
            scope.append("." if p == base else p.relative_to(base).as_posix())
    dbs = {}
    for name, rel in _db_names([str(d) for d in req.get("databases") or []]).items():
        p = inside_share(rel)
        if p.is_file() and p.suffix.lower() in DB_SUFFIXES:
            dbs[name] = str(p)
    if not scope and not dbs:
        raise ValueError("none of the chosen folders or databases exist any more")
    # nothing exposed = nothing reachable (an empty scope would otherwise mean "no restriction")
    return Sources(base, scope or ["\x00none"], dbs)


def pick_db(src: Sources, name: str) -> tuple[str, str] | GatewayDecision:
    """The database a query_db call means: the named one, or the only one."""
    if not src.dbs:
        return GatewayDecision("block", "No database is connected to this server gateway", "hard-rule")
    if name:
        key = name.strip().lower().removesuffix(".db").removesuffix(".sqlite3").removesuffix(".sqlite")
        if key == "main" and len(src.dbs) == 1:  # SQLite's own name for "the database"
            return next(iter(src.dbs.items()))
        if key not in src.dbs:
            return GatewayDecision("block", f"Unknown database '{name}'. Available: {', '.join(sorted(src.dbs))}", "hard-rule")
        return key, src.dbs[key]
    if len(src.dbs) > 1:
        return GatewayDecision("block", f"Several databases are connected; name one: {', '.join(sorted(src.dbs))}", "hard-rule")
    return next(iter(src.dbs.items()))


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


def scoped(role: RolePolicy, src: Sources) -> RolePolicy:
    """The role as it applies to this call: limited to the exposed folders, and database files are never readable as
    files (that would skip the column rules)."""
    role = role.model_copy(deep=True)
    role.scope = list(src.scope)
    for path in src.dbs.values():
        p = Path(path).resolve()
        if src.root in p.parents:
            rel = p.relative_to(src.root).as_posix()
            role.files.deny = [*role.files.deny, rel, f"{rel}-*"]  # plus SQLite's -wal / -journal files
    return role


def decision_json(d: GatewayDecision) -> dict:
    return {"verdict": d.verdict, "reason": d.reason, "layer": d.layer}


def decide(role: RolePolicy, tool: str, arg: str, src: Sources, db: str = "") -> tuple[GatewayDecision, dict]:
    role = scoped(role, src)
    r = src.root
    if tool == "list_files":
        return check_path(role, r, arg or ".", "list"), {}
    if tool == "read_file":
        return check_path(role, r, arg, "read"), {}
    if tool == "write_file":
        return check_path(role, r, arg, "write"), {}
    if tool == "run_command":
        return check_command(role, r, arg)[0], {}
    picked = pick_db(src, db)
    if isinstance(picked, GatewayDecision):
        return picked, {}
    name, path = picked
    d, cols, rows = run_sql(role, path, arg, db_name=name if len(src.dbs) > 1 else "")
    return d, ({"columns": cols, "rows": rows} if d.verdict == "allow" else {})


def execute(role: RolePolicy, tool: str, arg: str, content: str, src: Sources) -> str:
    role = scoped(role, src)
    r = src.root
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
        src = sources(req)
    except ValueError as e:
        return {"error": str(e)}
    if op == "inventory":
        return {"text": policy_compiler.inventory(src)}
    if op == "db_schema":
        return {"schema": {t: sorted(c) for t, c in policy_compiler.db_schema(src.dbs).items()}}
    if op == "evaluate":
        policy = CompiledPolicy.model_validate(req.get("policy") or {})
        return {"results": policy_compiler.evaluate_examples(policy, list(req.get("examples") or []), src)}
    tool, arg = req.get("tool"), req.get("arg", "")
    if op not in {"check", "exec"} or tool not in TOOLS or not isinstance(arg, str):
        return {"error": "bad request"}
    role = RolePolicy.model_validate(req.get("role") or {})
    db = req.get("db") or ""
    if not isinstance(db, str):
        return {"error": "bad request"}
    d, extra = decide(role, tool, arg, src, db)
    if op == "check" or d.verdict == "block":
        return {"decision": decision_json(d), **extra}
    if tool == "query_db":
        return {"error": "query_db runs in the check step"}
    content = req.get("content") or ""
    if not isinstance(content, str):
        return {"error": "bad request"}
    return {"decision": decision_json(d), "output": execute(role, tool, arg, content, src)}
