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
    # more shells, interpreters, package runners and compilers (any of them runs code)
    "rbash", "busybox", "toybox", "nawk", "pwsh", "powershell", "irb", "jshell", "java", "julia", "r", "rscript", "erl",
    "elixir", "iex", "ghci", "runghc", "wish", "uv", "uvx", "pip", "pip3", "pipx", "npm", "npx", "pnpm", "yarn", "corepack",
    "gem", "bundle", "cargo", "go", "gcc", "g++", "cc", "c++", "clang", "tcc", "ld", "as", "cmake", "ninja", "ldd", "openssl",
    # programs that run another program given as an argument
    "nice", "renice", "ionice", "stdbuf", "setsid", "chroot", "setarch", "linux32", "linux64", "taskset", "chrt", "prlimit",
    "runcon", "runuser", "setpriv", "unshare", "nsenter", "flock", "sg", "newgrp", "login", "start-stop-daemon", "run-parts",
    "scriptlive", "scriptreplay", "strace", "ltrace", "gdb", "valgrind", "time", "command", "exec", "eval", "builtin",
    "dpkg", "apt", "apt-get", "apt-config", "service", "invoke-rc.d", "update-alternatives", "gzexe", "zless", "zmore",
    "pager", "vipw", "vigr",
    # links: a hard link puts a denied file's content under a path the role can read
    "link", "hardlink", "mknod",
}
# versioned names of the same interpreters (perl5.40.1, python3.12, ld-linux-x86-64.so.2, …)
_VERSIONED = re.compile(r"^(?:python|perl|ruby|php|lua|node|tclsh|wish|pip)[\d.]+$|^ld(?:-linux[\w.-]*)?\.so(?:\.\d+)*$")


def hard_denied_program(argv0: str) -> bool:
    prog = os.path.basename(argv0).lower()
    return prog in HARD_DENY_PROGRAMS or bool(_VERSIONED.match(prog)) or prog.startswith("debconf")


# Flags that turn an otherwise harmless program into one that executes, deletes or reads files the checker never sees.
# "long": GNU long options (any unambiguous abbreviation counts, e.g. --to-com); "short": single-letter options, also
# inside clusters like -xvF; "words": single-dash word options (find).
HARD_DENY_FLAGS: dict[str, dict[str, set[str]]] = {
    "find": {"words": {"-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint", "-fprint0", "-fprintf", "-fls",
                       "-files0-from"}},
    "sort": {"long": {"--output", "--compress-program", "--files0-from"}, "short": {"o"}},
    "tar": {"long": {"--to-command", "--checkpoint-action", "--use-compress-program", "--info-script",
                     "--new-volume-script", "--rsh-command", "--rmt-command"}, "short": {"I", "F"}},
    "zip": {"long": {"--unzip-command"}, "short": {"T"}, "words": {"-TT"}},
    "split": {"long": {"--filter"}},
    "sdiff": {"long": {"--diff-program", "--output"}, "short": {"o"}},
    "diff3": {"long": {"--diff-program"}},
    "wc": {"long": {"--files0-from"}},
    "du": {"long": {"--files0-from"}},
}


def denied_flag(prog: str, args: list[str]) -> str | None:
    rules = HARD_DENY_FLAGS.get(prog)
    if not rules:
        return None
    for i, a in enumerate(args):
        if a == "--":
            break
        if a in rules.get("words", set()):
            return a
        if a.startswith("--") and len(a) > 2:
            name = a.split("=", 1)[0]
            hit = next((o for o in sorted(rules.get("long", set())) if o.startswith(name)), None)
            if hit:
                return hit
        elif a.startswith("-") or (prog == "tar" and i == 0):  # tar's first argument may be a dashless cluster (xvF)
            cluster = a.lstrip("-")
            hit = next((c for c in cluster if c in rules.get("short", set())), None)
            if hit:
                return f"-{hit}"
    return None


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
        return sorted({os.path.basename(p.strip()) for p in v if p.strip() and not hard_denied_program(p.strip())})


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
    # Folders (relative to the shared root) the admin exposed to agents; set by the runner at call time, never by the
    # compiled policy. Empty = no restriction (the root is already just the exposed folder).
    scope: list[str] = Field(default_factory=list, exclude=True)


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


def in_scope(role: RolePolicy, rel: str) -> bool:
    """Inside one of the folders the admin exposed."""
    if not role.scope or "." in role.scope:
        return True
    return any(rel == f or rel.startswith(f + "/") for f in role.scope)


def toward_scope(role: RolePolicy, rel: str) -> bool:
    """A parent folder of an exposed folder (listed only to show the way there)."""
    if not role.scope or "." in role.scope:
        return True
    return rel == "" or any(f.startswith(rel + "/") for f in role.scope)


def check_path(role: RolePolicy, root: Path, path: str, mode: str) -> GatewayDecision:
    """mode: read | write | list (non-recursive listing of a folder)."""
    real, rel = resolve_path(root, path)
    if real is None:
        return block(f"'{path}' is outside the files this server shares", "hard-rule")
    if not (in_scope(role, rel) or (mode == "list" and toward_scope(role, rel))):
        return block(f"'{rel or '/'}' is not in the folders shared with agents", "hard-rule")
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
    if not (in_scope(role, rel) or toward_scope(role, rel)) or _match(rel, role.files.deny):
        return False
    readable = role.files.read + role.files.write
    return _match(rel, readable) or any(_literal_prefix(p).startswith(rel + "/") or _literal_prefix(p) == rel for p in readable)


# ---------------------------------------------------------------- commands
RECURSIVE_PROGRAMS = {"grep", "egrep", "fgrep", "rgrep", "zgrep", "zegrep", "zfgrep", "rg", "ag", "find", "fd", "ls", "dir",
                      "vdir", "du", "tree", "tar", "zip", "unzip", "cp", "wc", "diff"}
WRITE_PROGRAMS = {"cp", "mv", "rm", "rmdir", "unlink", "shred", "touch", "mkdir", "mktemp", "tee", "truncate", "fallocate",
                  "install", "split", "csplit", "unzip", "tar", "zip", "gzip", "gunzip", "uncompress", "patch", "rename",
                  "rename.ul"}
# programs that only look at a folder itself (its name, metadata or emptiness), never at the files inside it
NAME_ONLY_PROGRAMS = {"stat", "file", "namei", "realpath", "readlink", "basename", "dirname", "test", "[", "mkdir", "rmdir",
                      "touch"}
# archives can hold any path, so extracting one may write anywhere: they need the whole shared folder
ARCHIVE_PROGRAMS = {"tar", "unzip"}


def check_command(role: RolePolicy, root: Path, command: str) -> tuple[GatewayDecision, list[str]]:
    if not isinstance(command, str) or not command.strip() or len(command) > 2000:
        return block("Empty or oversized command", "hard-rule"), []
    try:
        argv = shlex.split(command)
    except ValueError:
        return block("The command could not be parsed", "hard-rule"), []
    if not argv:
        return block("Empty or oversized command", "hard-rule"), []
    prog = os.path.basename(argv[0])
    if hard_denied_program(argv[0]) or "/" in argv[0]:
        return block(f"'{prog}' can run arbitrary code, reach the network or change the system; it is never allowed here",
                     "hard-rule"), argv
    bad = denied_flag(prog, argv[1:])
    if bad:
        return block(f"'{prog} {bad}' can run programs, delete things or read files unchecked; not allowed", "hard-rule"), argv
    mode = "write" if prog in WRITE_PROGRAMS else "read"
    paths = []
    for a in argv[1:]:
        if a.startswith("-"):
            if "=" in a:
                cands = [a.split("=", 1)[1]]
            elif not a.startswith("--") and len(a) > 2:
                # a value glued to a short option (-fFILE, -rfFILE): any tail that names a path is checked like one
                cands = [a[i:] for i in range(2, len(a)) if "/" in a[i:] or a[i:].startswith("~") or (root / a[i:]).exists()]
            else:
                continue
        else:
            cands = [a]
        for cand in cands:
            if cand.startswith(("/", "~")) and not cand.startswith(str(root) + "/"):
                # the program would receive the real absolute path (no remapping happens when it runs): never outside the root
                return block(f"'{cand}' is an absolute path; use paths relative to the shared folder", "hard-rule"), argv
            # a write program's arguments are all targets, existing or not (touch new.txt, cp a.txt b.txt)
            if mode == "write" or "/" in cand or cand in {".", ".."} or (root / cand).exists():
                paths.append(cand)
                if prog in {"gzip", "gunzip", "uncompress"} and cand.lower().endswith((".gz", ".z")):
                    paths.append(cand.rsplit(".", 1)[0])  # the file it writes next to the archive
    if prog in ARCHIVE_PROGRAMS or (not paths and prog in RECURSIVE_PROGRAMS):
        paths.append(".")  # these default to (or may write anywhere in) the current folder, i.e. the whole shared root
    unclear: GatewayDecision | None = None
    for cand in paths:
        real, rel = resolve_path(root, cand)
        if real is None:
            return block(f"'{cand}' is outside the files this server shares", "hard-rule"), argv
        if not in_scope(role, rel):
            return block(f"'{rel or '/'}' is not in the folders shared with agents; name a folder inside them", "hard-rule"), argv
        if real.is_dir() and prog not in NAME_ONLY_PROGRAMS:
            # a tool given a folder may reach everything inside it (grep -r, rgrep, diff -r, mv, rm -r): every file there
            # must be allowed for this kind of access, and nothing denied
            allowed = role.files.write if mode == "write" else role.files.read + role.files.write
            if dir_contains_denied(rel, role.files.deny) or not covers_whole_dir(rel, allowed):
                return block(f"'{prog}' on '{rel or '/'}' would reach files your role can't access; name a folder you fully "
                             f"have access to", rel=rel), argv
            continue
        d = check_path(role, root, cand, mode)
        if d.verdict == "block":
            return d, argv
        if d.verdict == "supervisor" and unclear is None:  # keep checking: a later path may be blocked outright
            unclear = supervisor(f"'{prog}' would {mode} '{d.facts.get('rel') or cand}', which no rule covers")
    if unclear is not None:
        return unclear, argv
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
            max_seconds: float = 5.0, db_name: str = "") -> tuple[GatewayDecision, list[str], list[list[Any]]]:
    """SQLite's own authorizer decides every table/column the statement touches, so string tricks can't smuggle access.
    With several databases, rules may name a table as `<db_name>.<table>` (only that database) or just `<table>` (any)."""
    rules = role.database
    q = f"{db_name.lower()}." if db_name else ""
    if not (rules.read_tables or rules.write_tables):
        return block("Your role has no database access"), [], []
    if not isinstance(sql, str) or not sql.strip() or len(sql) > 5000:
        return block("Empty or oversized query", "hard-rule"), [], []
    if ";" in sql.strip().rstrip(";"):
        return block("One statement at a time", "hard-rule"), [], []
    denied: list[str] = []
    readable = set(rules.read_tables) | set(rules.write_tables)
    # A WITH name can reach the authorizer as a table read (recursive ones do). Names are never taken from the query text
    # (`WITH secrets AS (…) SELECT * FROM main.secrets` reads the real table): a name the database itself has as a table
    # or view is always checked; any other name is query-local, and the real tables behind it are checked on their own.
    real_tables: set[str] = set()

    def authorizer(action, arg1, arg2, dbname, source):
        t = (arg1 or "").lower()
        if action == sqlite3.SQLITE_READ:
            if t.startswith("sqlite_"):
                # table names help an agent find its way; full definitions (the `sql` column) would reveal hidden columns
                if t in {"sqlite_master", "sqlite_schema", "sqlite_temp_master"} and (arg2 or "").lower() not in {"name", "type", "tbl_name"}:
                    denied.append("the database's full schema")
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            if t in real_tables and t not in readable and (not q or q + t not in readable):
                denied.append(f"table '{t}'")
                return sqlite3.SQLITE_DENY
            col = f"{t}.{(arg2 or '').lower()}"
            if col in rules.deny_columns or (q and q + col in rules.deny_columns):
                denied.append(f"column '{t}.{arg2}'")
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        if action in _WRITE_OPS:
            if t not in rules.write_tables and (not q or q + t not in rules.write_tables):
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
        real_tables = {r[0].lower() for r in con.execute("select name from sqlite_master where type in ('table', 'view')")}
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
