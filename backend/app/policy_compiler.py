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
The agents can use five tools on the server: list_files, read_file, write_file, run_command (no shell), query_db (SQLite).

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
 "examples": [{{"role": "<role-slug>", "tool": "read_file|write_file|list_files|run_command|query_db", "arg": "<path, command or SQL>",
               "expected": "allow|block", "why": "<short>"}}]}}

Rules:
- Globs are relative to the shared folder. Use "folder/**" for a whole folder, "folder/*.md" for some files.
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


def inventory(root: Path, db_path: str, max_entries: int = 60) -> str:
    lines = ["Files (shared folder):"]
    n = 0
    for p in sorted(root.rglob("*")) if root.exists() else []:
        if n >= max_entries:
            lines.append("  …")
            break
        rel = p.relative_to(root).as_posix()
        if p.is_symlink() or rel.count("/") > 2:
            continue
        lines.append(f"  {rel}{'/' if p.is_dir() else ''}")
        n += 1
    lines.append("Database tables:")
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        for (t,) in con.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name"):
            cols = [r[0] for r in con.execute("select name from pragma_table_info(?)", (t,))]
            lines.append(f"  {t}({', '.join(cols)})")
        con.close()
    except sqlite3.Error:
        lines.append("  (no database)")
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


def evaluate_examples(policy: CompiledPolicy, examples: list[dict], root: Path, db_path: str) -> list[dict]:
    """Replay the model's examples through the real checker. Nothing is executed on the live data."""
    out = []
    tmp_db = None
    if Path(db_path).exists():
        tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
        shutil.copy(db_path, tmp_db)  # SQL examples run against a throwaway copy
    for ex in examples[:40]:
        role = policy.roles.get(str(ex.get("role", "")).strip().lower())
        tool, arg = str(ex.get("tool", "")), str(ex.get("arg", ""))
        if role is None:
            got, reason = "block", "unknown role"
        elif tool in {"read_file", "list_files", "write_file"}:
            d = check_path(role, root, arg, {"read_file": "read", "list_files": "list", "write_file": "write"}[tool])
            got, reason = d.verdict, d.reason
        elif tool == "run_command":
            d, _ = check_command(role, root, arg)
            got, reason = d.verdict, d.reason
        elif tool == "query_db" and tmp_db:
            d, _, _ = run_sql(role, tmp_db, arg)
            got, reason = d.verdict, d.reason
        else:
            got, reason = "block", "unknown tool"
        expected = str(ex.get("expected", "")).lower()
        out.append({"role": ex.get("role", ""), "tool": tool, "arg": arg, "expected": expected, "why": ex.get("why", ""),
                    "got": got, "reason": reason,
                    # a supervisor case is fine for an expected block only if the supervisor blocks it; flag it for review
                    "ok": got == expected, "needs_supervisor": got == "supervisor"})
    if tmp_db:
        Path(tmp_db).unlink(missing_ok=True)
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


def db_schema(db_path: str) -> dict[str, set[str]]:
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        tables = [t for (t,) in con.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")]
        out = {t.lower(): {c.lower() for (c,) in con.execute("select name from pragma_table_info(?)", (t,))} for t in tables}
        con.close()
        return out
    except sqlite3.Error:
        return {}


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
            t, _, c = col.partition(".")
            if schema and (t not in schema or c not in schema[t]):
                warnings.append(f"{name}: hidden column '{col}' does not exist (ignored)")
            elif t in r.database.read_tables + r.database.write_tables:
                warnings.append(f"{name}: can't see column '{col}'; check this matches the policy")
    return warnings


async def compile_policy(cfg: dict, text: str, root: Path, db_path: str) -> dict:
    raw = parse(await call_model(cfg, PROMPT.format(inventory=inventory(root, db_path), policy=text[:8000])))
    policy = CompiledPolicy.model_validate({"roles": raw.get("roles") or {}})
    if not policy.roles:
        raise ValueError("the model found no roles in the policy")
    examples = evaluate_examples(policy, [e for e in raw.get("examples") or [] if isinstance(e, dict)], root, db_path)
    warnings = dropped_items(raw, policy) + consistency_warnings(policy, db_schema(db_path))
    return {"compiled": policy.model_dump(), "examples": examples, "warnings": warnings}
