"""Plain-English server policy → role rules (CompiledPolicy) + example actions the admin can check before approving.

The model only proposes; the schema then drops anything unsafe (paths outside the root, shells, network tools), and
the examples are replayed through the real checker so the admin sees what would actually happen.
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import tempfile
from pathlib import Path

import httpx

from .gateway_policy import CompiledPolicy, check_command, check_path, run_sql

PROMPT = """You turn an administrator's plain-English access policy for AI agents on a server into JSON rules.
The agents can use five tools on the server: list_files, read_file, write_file, run_command (no shell), query_db (SQLite;
with several databases the agent names one).

SERVER CONTENTS (for reference):
{inventory}

ADMINISTRATOR'S POLICY:
<policy>
{policy}
</policy>

Reply with JSON only, in exactly this shape:
{{"roles": {{"<role-slug>": {{
    "description": "<one line>",
    "files": {{"read": ["<glob>"], "write": ["<glob>"], "deny": ["<glob>"]}},
    "commands": {{"allow": ["<program>"]}},
    "database": {{"read_tables": ["<table>"], "write_tables": ["<table>"], "deny_columns": ["<table>.<column>"]}},
    "notes": "<anything the rules above can't express, for the supervisor>"}}}},
 "examples": [{{"role": "<role-slug>", "tool": "read_file|write_file|list_files|run_command|query_db", "arg": "<path, command or SQL>", "database": "<database name for query_db, when there are several>",
               "expected": "allow|block", "why": "<short>"}}]}}

Rules:
- Globs are relative to the shared root, exactly as paths appear in SERVER CONTENTS (e.g. "northwind/support/**").
- With several databases, name tables as "<database>.<table>" and columns as "<database>.<table>.<column>".
- Use "folder/**" for a whole folder, "folder/*.md" for some files.
- When the policy grants a kind of data, grant every place it lives: the matching folders AND the matching database tables.
  If only part of it is allowed (e.g. "contact details but not card numbers"), grant the table and list the forbidden
  columns in "deny_columns"; for files that mix allowed and forbidden data, leave them out rather than deny them.
- "deny" is only for things the policy forbids for that role (deny beats read/write). Never deny what the policy grants.
- When the policy grants a folder ("reports", "tickets"), use "folder/**", not single files.
- Programs: only read-only tools such as ls, cat, head, tail, grep, wc, find, sort, uniq, diff, du, stat, file. Never shells,
  interpreters or network tools. Only give a role a program if the policy lets it look at files.
- Be strict: if the policy doesn't clearly grant something, leave it out (a supervisor decides unclear cases).
- Write 3-5 examples per role: both things the policy allows and things it forbids, using real paths and tables from SERVER CONTENTS.
"""


def _tables(db_path: str) -> list[tuple[str, list[str]]]:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return [(t, [r[0] for r in con.execute("select name from pragma_table_info(?)", (t,))])
                for (t,) in con.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name")]
    finally:
        con.close()


def inventory(src, db_path: str | None = None, max_entries: int = 80) -> str:
    """What the model sees: the exposed folders (paths relative to the shared root) and each database's tables.
    `src` is app.gateway_ops.Sources (or, in older callers, a root Path plus one database path)."""
    if isinstance(src, Path):
        root, scope, dbs = src, [], ({"server": db_path} if db_path else {})
    else:
        root, scope, dbs = src.root, [f for f in src.scope if f != "\x00none"], src.dbs
    lines = ["Files (shared folder):"]
    starts = [root] if not scope or "." in scope else [root / f for f in scope]
    n = 0
    for start in starts:
        if start != root and start.is_dir():
            lines.append(f"  {start.relative_to(root).as_posix()}/")
        for p in sorted(start.rglob("*")) if start.exists() else []:
            if n >= max_entries:
                lines.append("  …")
                break
            rel = p.relative_to(root).as_posix()
            if p.is_symlink() or rel.count("/") > 3 or any(part.startswith(".") for part in p.relative_to(root).parts[:-1]):
                continue
            if p.suffix.lower() in (".db", ".sqlite", ".sqlite3") or "-journal" in p.name or p.name.endswith("-wal"):
                continue  # databases are listed below, never as files
            lines.append(f"  {rel}{'/' if p.is_dir() else ''}")
            n += 1
    lines.append("Databases:" if len(dbs) > 1 else "Database tables:")
    if not dbs:
        lines.append("  (no database connected)")
    for name, path in dbs.items():
        try:
            for t, cols in _tables(path):
                lines.append(f"  {name + '.' if len(dbs) > 1 else ''}{t}({', '.join(cols)})")
        except sqlite3.Error:
            lines.append(f"  {name}: (can't open)")
    return "\n".join(lines)


async def call_model(cfg: dict, prompt: str, timeout: float = 120.0) -> str:
    url = cfg["url"].rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {cfg['api_key']}"} if cfg.get("api_key") else {}
    body = {"model": cfg["model"], "temperature": 0, "max_tokens": 2500, "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": prompt}]}
    async with httpx.AsyncClient(timeout=timeout) as c:
        r = await c.post(url, json=body, headers=headers)
        if r.status_code == 400:
            body.pop("response_format")
            r = await c.post(url, json=body, headers=headers)
        r.raise_for_status()
        return r.json()["choices"][0]["message"].get("content") or ""


def parse(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("the model did not return JSON")
    return json.loads(m.group(0))


def evaluate_examples(policy: CompiledPolicy, examples: list[dict], src, db_path: str | None = None) -> list[dict]:
    """Replay the model's examples through the real checker. Nothing is executed on the live data (SQL examples run
    against throwaway copies of the databases)."""
    from .gateway_ops import Sources, pick_db, scoped
    if isinstance(src, Path):
        src = Sources(src, [], {"server": db_path} if db_path else {})
    copies = {}
    for name, path in src.dbs.items():
        if Path(path).exists():
            copies[name] = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
            shutil.copy(path, copies[name])
    test_src = Sources(src.root, src.scope, copies)
    root = src.root
    out = []
    for ex in examples[:40]:
        role = policy.roles.get(str(ex.get("role", "")).strip().lower())
        role = scoped(role, src) if role is not None else None
        tool, arg = str(ex.get("tool", "")), str(ex.get("arg", ""))
        if role is None:
            got, reason = "block", "unknown role"
        elif tool in {"read_file", "list_files", "write_file"}:
            d = check_path(role, root, arg, {"read_file": "read", "list_files": "list", "write_file": "write"}[tool])
            got, reason = d.verdict, d.reason
        elif tool == "run_command":
            d, _ = check_command(role, root, arg)
            got, reason = d.verdict, d.reason
        elif tool == "query_db" and copies:
            picked = pick_db(test_src, str(ex.get("database", "") or ""))
            if isinstance(picked, tuple):
                d, _, _ = run_sql(role, picked[1], arg, db_name=picked[0] if len(copies) > 1 else "")
            else:
                d = picked
            got, reason = d.verdict, d.reason
        else:
            got, reason = "block", "unknown tool"
        expected = str(ex.get("expected", "")).lower()
        out.append({"role": ex.get("role", ""), "tool": tool, "arg": arg, "expected": expected, "why": ex.get("why", ""),
                    "got": got, "reason": reason,
                    # a supervisor case is fine for an expected block only if the supervisor blocks it; flag it for review
                    "ok": got == expected, "needs_supervisor": got == "supervisor"})
    for path in copies.values():
        Path(path).unlink(missing_ok=True)
    return out


def dropped_items(raw: dict, policy: CompiledPolicy) -> list[str]:
    """What the model proposed but the schema refused (unsafe programs, paths outside the root)."""
    warnings = []
    for name, r in (raw.get("roles") or {}).items():
        slug = re.sub(r"[^a-z0-9_-]+", "-", str(name).strip().lower()).strip("-")
        got = policy.roles.get(slug)
        if not got or not isinstance(r, dict):
            continue
        for prog in ((r.get("commands") or {}).get("allow") or []):
            if str(prog).split("/")[-1] not in got.commands.allow:
                warnings.append(f"{slug}: removed program '{prog}' (can run code, reach the network or change the system)")
        for kind in ("read", "write", "deny"):
            for pat in ((r.get("files") or {}).get(kind) or []):
                if str(pat).strip().removeprefix("./") not in getattr(got.files, kind):
                    warnings.append(f"{slug}: removed {kind} pattern '{pat}' (outside the shared folder)")
    return warnings


def db_schema(dbs) -> dict[str, set[str]]:
    """Tables → columns of the connected databases (with several: also "<database>.<table>")."""
    if isinstance(dbs, str):
        dbs = {"server": dbs} if dbs else {}
    out: dict[str, set[str]] = {}
    for name, path in dbs.items():
        try:
            for t, cols in _tables(path):
                c = {x.lower() for x in cols}
                out.setdefault(t.lower(), set()).update(c)
                if len(dbs) > 1:
                    out[f"{name}.{t.lower()}"] = c
        except sqlite3.Error:
            continue
    return out


def consistency_warnings(policy: CompiledPolicy, schema: dict[str, set[str]]) -> list[str]:
    """Mistakes a model makes that the admin should see before approving (the stricter reading still applies)."""
    warnings = []
    for name, r in policy.roles.items():
        for pat in sorted(set(r.files.deny) & set(r.files.read + r.files.write)):
            warnings.append(f"{name}: '{pat}' is both granted and denied; deny wins. Edit the policy if it should be allowed.")
        for t in r.database.read_tables + r.database.write_tables:
            if schema and t not in schema:
                warnings.append(f"{name}: table '{t}' does not exist in the database")
        for col in r.database.deny_columns:
            t, _, c = col.rpartition(".")
            if schema and (t not in schema or c not in schema[t]):
                warnings.append(f"{name}: hidden column '{col}' does not exist (ignored)")
            elif t in r.database.read_tables + r.database.write_tables:
                warnings.append(f"{name}: can't see column '{col}'; check this matches the policy")
    return warnings


async def compile_policy(cfg: dict, text: str, ops) -> dict:
    """`ops` reads the shared data (app.gateway_client.RunnerOps): the backend itself never opens agent-controlled files."""
    raw = parse(await call_model(cfg, PROMPT.format(inventory=await ops.inventory(), policy=text[:8000])))
    policy = CompiledPolicy.model_validate({"roles": raw.get("roles") or {}})
    if not policy.roles:
        raise ValueError("the model found no roles in the policy")
    examples = await ops.evaluate(policy.model_dump(), [e for e in raw.get("examples") or [] if isinstance(e, dict)])
    warnings = dropped_items(raw, policy) + consistency_warnings(policy, await ops.db_schema())
    return {"compiled": policy.model_dump(), "examples": examples, "warnings": warnings}
