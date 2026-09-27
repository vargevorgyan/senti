"""Senti server gateway: the compiled role policy, the deterministic checker and the safe executors.

Agents never touch the server directly. Every MCP tool call is decided here first:
  1. hard rules   — path escapes, dangerous programs/flags, SQL outside the role's tables → block (no model can override)
  2. role rules   — compiled from the admin's plain-English policy: deny beats allow → allow / block
  3. supervisor   — anything the rules don't cover goes to the supervisor LLM (no human in the loop); "ask" counts as block
Only then does the gateway execute the action itself, confined to the gateway root.
"""
from __future__ import annotations

import os
import re
import shlex
import sqlite3
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------- compiled policy schema
# Programs that can run arbitrary code, reach the network or escalate privileges: never runnable through the gateway,
# whatever the policy says.
HARD_DENY_PROGRAMS = {
    "sh", "bash", "zsh", "dash", "ksh", "fish", "csh", "tcsh", "python", "python3", "python2", "node", "deno", "bun", "perl",
    "ruby", "php", "lua", "osascript", "env", "xargs", "sudo", "su", "doas", "ssh", "scp", "sftp", "rsync", "curl", "wget", "nc",
    "ncat", "socat", "telnet", "ftp", "awk", "gawk", "mawk", "sed", "vi", "vim", "nvim", "emacs", "less", "more", "man", "git",
    "make", "docker", "kubectl", "chmod", "chown", "ln", "dd", "mkfs", "mount", "crontab", "launchctl", "systemctl", "kill",
    "pkill", "killall", "nohup", "timeout", "watch", "script", "expect", "tclsh", "open", "security", "sqlite3", "psql", "mysql",
}
# Flags that turn an otherwise read-only program into one that executes or deletes things
HARD_DENY_FLAGS = {
    "find": {"-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint", "-fprintf", "-fls"},
    "sort": {"-o", "--output", "--compress-program"},
    "tar": {"--to-command", "--checkpoint-action", "--use-compress-program", "-I"},
    "zip": {"-T", "--unzip-command", "-TT"},
}


class FileRules(BaseModel):
    read: list[str] = Field(default_factory=list)   # glob patterns relative to the gateway root
    write: list[str] = Field(default_factory=list)
    deny: list[str] = Field(default_factory=list)   # beats read and write

    @field_validator("read", "write", "deny")
    @classmethod
    def _relative(cls, v: list[str]) -> list[str]:
        out = []
        for p in v:
            p = p.strip()
            p = p[2:] if p.startswith("./") else p
            if not p or p.startswith(("/", "~")) or ".." in Path(p).parts or "\x00" in p:
                continue  # patterns can only describe paths inside the gateway root
            out.append(p)
        return out


class CommandRules(BaseModel):
    allow: list[str] = Field(default_factory=list)  # program names, e.g. ["ls", "grep", "wc"]

    @field_validator("allow")
    @classmethod
    def _no_dangerous(cls, v: list[str]) -> list[str]:
        return sorted({os.path.basename(p.strip()) for p in v if p.strip() and os.path.basename(p.strip()) not in HARD_DENY_PROGRAMS})


class DatabaseRules(BaseModel):
    read_tables: list[str] = Field(default_factory=list)
    write_tables: list[str] = Field(default_factory=list)
    deny_columns: list[str] = Field(default_factory=list)  # "table.column"

    @field_validator("read_tables", "write_tables", "deny_columns")
    @classmethod
    def _lower(cls, v: list[str]) -> list[str]:
        return sorted({x.strip().lower() for x in v if x.strip()})


class RolePolicy(BaseModel):
    description: str = ""
    files: FileRules = Field(default_factory=FileRules)
    commands: CommandRules = Field(default_factory=CommandRules)
    database: DatabaseRules = Field(default_factory=DatabaseRules)
    notes: str = ""  # extra guidance for the supervisor for this role


class CompiledPolicy(BaseModel):
    roles: dict[str, RolePolicy] = Field(default_factory=dict)

    @field_validator("roles")
    @classmethod
    def _slugs(cls, v: dict[str, RolePolicy]) -> dict[str, RolePolicy]:
        return {re.sub(r"[^a-z0-9_-]+", "-", k.strip().lower()).strip("-") or "role": r for k, r in v.items()}


# ---------------------------------------------------------------- decisions
@dataclass
class GatewayDecision:
    verdict: str            # allow | block | supervisor
    reason: str
    layer: str              # hard-rule | role-rule | supervisor
    facts: dict[str, Any] = field(default_factory=dict)


def allow(reason: str, **facts) -> GatewayDecision:
    return GatewayDecision("allow", reason, "role-rule", facts)


def block(reason: str, layer: str = "role-rule", **facts) -> GatewayDecision:
    return GatewayDecision("block", reason, layer, facts)


def supervisor(reason: str, **facts) -> GatewayDecision:
    return GatewayDecision("supervisor", reason, "supervisor", facts)


# ---------------------------------------------------------------- paths
_WILD = re.compile(r"[*?\[]")


def _glob_re(pattern: str) -> re.Pattern:
    """Glob with `**` (any depth) and `*` / `?` (within one path segment)."""
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile("^" + out + "$")


def _match(rel: str, patterns: list[str]) -> bool:
    """A bare folder name ("tickets") or "folder/**" covers the folder and everything in it."""
    for p in patterns:
        base = p[:-3] if p.endswith("/**") else p.rstrip("/")
        if not _WILD.search(base) and (rel == base or rel.startswith(base + "/")):
            return True
        if _glob_re(p).match(rel):
            return True
    return False


def _literal_prefix(pattern: str) -> str:
    m = _WILD.search(pattern)
    return (pattern[:m.start()] if m else pattern).rstrip("/").rsplit("/", 1)[0] if m else pattern.rstrip("/")


def covers_whole_dir(rel: str, patterns: list[str]) -> bool:
    """True only if every possible file under `rel` matches one of the patterns (for recursive tools)."""
    for p in patterns:
        base = p[:-3] if p.endswith("/**") else p.rstrip("/")
        if p == "**" or (not _WILD.search(base) and (rel == base or rel.startswith(base + "/"))):
            return True
    return False


def dir_contains_denied(rel: str, deny: list[str]) -> bool:
    for d in deny:
        prefix = _literal_prefix(d)
        if rel == "" or prefix == rel or prefix.startswith(rel + "/") or rel.startswith(prefix + "/") or not prefix:
            return True
    return False


def resolve_path(root: Path, path: str) -> tuple[Path | None, str]:
    """Absolute, real path inside the root, and its root-relative form. None if it escapes (../, absolute elsewhere, symlink)."""
    if not isinstance(path, str) or "\x00" in path:
        return None, ""
    root = root.resolve()
    p = Path(path) if path.startswith(str(root)) else root / path.lstrip("/")
    try:
        real = p.resolve()  # follows symlinks: a link pointing outside the root is an escape
    except (OSError, RuntimeError):
        return None, ""
    if real != root and root not in real.parents:
        return None, ""
    rel = real.relative_to(root).as_posix()
    return real, "" if rel == "." else rel


def check_path(role: RolePolicy, root: Path, path: str, mode: str) -> GatewayDecision:
    """mode: read | write | list (non-recursive listing of a folder)."""
    real, rel = resolve_path(root, path)
    if real is None:
        return block(f"'{path}' is outside the files this server shares", "hard-rule")
    if rel and _match(rel, role.files.deny):
        return block(f"Your role may not access '{rel}'", rel=rel)
    if mode == "write":
        if _match(rel, role.files.write):
            return allow(f"Allowed to write '{rel}'", rel=rel)
        return supervisor(f"No rule lets this role write '{rel or '/'}'", rel=rel)
    readable = role.files.read + role.files.write
    if mode == "list" and (rel == "" or any(_literal_prefix(p) == rel or _literal_prefix(p).startswith(rel + "/") for p in readable)):
        return allow(f"Listing '{rel or '/'}' (entries you can't access are hidden)", rel=rel)
    if rel and _match(rel, readable):
        return allow(f"Allowed to read '{rel}'", rel=rel)
    return supervisor(f"No rule covers reading '{rel or '/'}'", rel=rel)


def visible(role: RolePolicy, rel: str) -> bool:
    """Entry shown in a listing: not denied, and readable or on the way to something readable."""
    if _match(rel, role.files.deny):
        return False
    readable = role.files.read + role.files.write
    return _match(rel, readable) or any(_literal_prefix(p).startswith(rel + "/") or _literal_prefix(p) == rel for p in readable)


# ---------------------------------------------------------------- commands
RECURSIVE_PROGRAMS = {"grep", "egrep", "fgrep", "rg", "ag", "find", "fd", "ls", "du", "tree", "tar", "zip", "cp", "wc"}
WRITE_PROGRAMS = {"cp", "mv", "rm", "rmdir", "touch", "mkdir", "tee", "truncate", "install", "split", "unzip", "tar", "zip",
                  "patch", "rename"}


def check_command(role: RolePolicy, root: Path, command: str) -> tuple[GatewayDecision, list[str]]:
    if not isinstance(command, str) or not command.strip() or len(command) > 2000:
        return block("Empty or oversized command", "hard-rule"), []
    try:
        argv = shlex.split(command)
    except ValueError:
        return block("The command could not be parsed", "hard-rule"), []
    prog = os.path.basename(argv[0])
    if prog in HARD_DENY_PROGRAMS or "/" in argv[0]:
        return block(f"'{prog}' can run arbitrary code, reach the network or change the system; it is never allowed here",
                     "hard-rule"), argv
    bad = HARD_DENY_FLAGS.get(prog, set()) & {a.split("=")[0] for a in argv[1:]}
    if bad:
        return block(f"'{prog} {sorted(bad)[0]}' can run or delete things; not allowed", "hard-rule"), argv
    mode = "write" if prog in WRITE_PROGRAMS else "read"
    paths = []
    for a in argv[1:]:
        if a.startswith("-") and "=" not in a:
            continue
        cand = a.split("=", 1)[1] if a.startswith("-") else a
        if cand.startswith(("/", "~")) and not cand.startswith(str(root) + "/"):
            # the program would receive the real absolute path (no remapping happens when it runs): never outside the root
            return block(f"'{cand}' is an absolute path; use paths relative to the shared folder", "hard-rule"), argv
        if "/" in cand or cand in {".", ".."} or (root / cand).exists():
            paths.append(cand)
    if not paths and prog in RECURSIVE_PROGRAMS:
        paths = ["."]  # these default to the current folder, i.e. the whole shared root
    for cand in paths:
        real, rel = resolve_path(root, cand)
        if real is None:
            return block(f"'{cand}' is outside the files this server shares", "hard-rule"), argv
        if real.is_dir() and prog in RECURSIVE_PROGRAMS:
            # a recursive tool on a folder reads everything inside it: every file there must be allowed, nothing denied
            if dir_contains_denied(rel, role.files.deny) or not covers_whole_dir(rel, role.files.read + role.files.write):
                return block(f"'{prog}' on '{rel or '/'}' would reach files your role can't access; name a folder you fully "
                             f"have access to", rel=rel), argv
            continue
        d = check_path(role, root, cand, mode)
        if d.verdict == "block":
            return d, argv
        if d.verdict == "supervisor":
            return supervisor(f"'{prog}' would {mode} '{d.facts.get('rel') or cand}', which no rule covers"), argv
    if prog in role.commands.allow:
        return allow(f"'{prog}' is allowed for this role"), argv
    return supervisor(f"'{prog}' is not in this role's command list"), argv


def run_command(root: Path, argv: list[str], timeout: float = 10.0) -> str:
    """No shell, confined working directory, minimal environment, bounded time and output."""
    try:
        p = subprocess.run(argv, cwd=root, capture_output=True, text=True, timeout=timeout, shell=False,
                           env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C.UTF-8", "HOME": str(root)})
    except subprocess.TimeoutExpired:
        return f"(stopped after {timeout:.0f} s)"
    except FileNotFoundError:
        return f"(program not found: {argv[0]})"
    out = (p.stdout or "") + (("\n[stderr]\n" + p.stderr) if p.stderr else "")
    return out[:20000] + ("\n…(truncated)" if len(out) > 20000 else "")


# ---------------------------------------------------------------- database
_READ_OPS = {sqlite3.SQLITE_READ, sqlite3.SQLITE_SELECT, sqlite3.SQLITE_FUNCTION,
             getattr(sqlite3, "SQLITE_RECURSIVE", 33)}  # recursive WITH is still only reading; the time limit stops runaways
_WRITE_OPS = {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE}


def run_sql(role: RolePolicy, db_path: str, sql: str, max_rows: int = 200,
            max_seconds: float = 5.0) -> tuple[GatewayDecision, list[str], list[list[Any]]]:
    """SQLite's own authorizer decides every table/column the statement touches, so string tricks can't smuggle access."""
    rules = role.database
    if not (rules.read_tables or rules.write_tables):
        return block("Your role has no database access"), [], []
    if not isinstance(sql, str) or not sql.strip() or len(sql) > 5000:
        return block("Empty or oversized query", "hard-rule"), [], []
    if ";" in sql.strip().rstrip(";"):
        return block("One statement at a time", "hard-rule"), [], []
    denied: list[str] = []
    readable = set(rules.read_tables) | set(rules.write_tables)
    # names defined by WITH are query-local; the tables their bodies read are still checked one by one
    ctes = {m.lower() for m in re.findall(r"(?:\bwith\s+(?:recursive\s+)?|,\s*)([A-Za-z_]\w*)\s*(?:\([^)]*\))?\s+as\s*\(", sql, re.I)}

    def authorizer(action, arg1, arg2, dbname, source):
        t = (arg1 or "").lower()
        if action == sqlite3.SQLITE_READ:
            if t.startswith("sqlite_"):
                # table names help an agent find its way; full definitions (the `sql` column) would reveal hidden columns
                if t in {"sqlite_master", "sqlite_schema", "sqlite_temp_master"} and (arg2 or "").lower() not in {"name", "type", "tbl_name"}:
                    denied.append("the database's full schema")
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            if t not in readable and t not in ctes:
                denied.append(f"table '{t}'")
                return sqlite3.SQLITE_DENY
            if f"{t}.{(arg2 or '').lower()}" in rules.deny_columns:
                denied.append(f"column '{t}.{arg2}'")
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        if action in _WRITE_OPS:
            if t not in rules.write_tables:
                denied.append(f"writing to '{t}'")
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        if action in _READ_OPS or action == sqlite3.SQLITE_TRANSACTION:
            return sqlite3.SQLITE_OK
        denied.append("schema changes, PRAGMA or ATTACH")
        return sqlite3.SQLITE_DENY

    mode = "rw" if rules.write_tables else "ro"
    try:
        con = sqlite3.connect(f"file:{db_path}?mode={mode}", uri=True, timeout=5)
    except sqlite3.Error as e:
        return block(f"Database unavailable: {e}", "hard-rule"), [], []
    import time as _time
    deadline = _time.monotonic() + max_seconds
    try:
        con.set_authorizer(authorizer)
        # a runaway query (e.g. an endless WITH RECURSIVE) is interrupted instead of hanging the server
        con.set_progress_handler(lambda: 1 if _time.monotonic() > deadline else 0, 10_000)
        cur = con.execute(sql)
        cols = [d[0] for d in (cur.description or [])]
        rows = [list(r) for r in cur.fetchmany(max_rows)]
        con.commit()
        return allow("Query uses only tables and columns your role may use"), cols, rows
    except sqlite3.DatabaseError as e:
        if denied:
            return block(f"Your role may not use {denied[0]}"), [], []
        if "interrupted" in str(e).lower():
            return block(f"The query took longer than {max_seconds:.0f} s and was stopped", "hard-rule"), [], []
        return block(f"The query failed: {str(e)[:200]}", "hard-rule"), [], []
    finally:
        con.close()
