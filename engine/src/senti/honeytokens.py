"""Honeytokens: fake credentials planted where an attacker (or a hijacked agent) would look.

Nobody legitimate ever reads or sends them, so any touch is a near-certain alarm - no LLM needed.
Values and decoy file paths live in ~/.senti/honeytokens.json (a guard path).
"""
from __future__ import annotations

import json
import os
import random
import secrets
import string
import time
from pathlib import Path

from .config import senti_home


def _store() -> Path:
    return senti_home() / "honeytokens.json"


def load() -> dict:
    p = _store()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {"values": [], "files": []}


def save(data: dict) -> None:
    p = _store()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))
    os.chmod(p, 0o600)


def _fake_values() -> dict[str, str]:
    up = string.ascii_uppercase + string.digits
    return {
        "AWS_ACCESS_KEY_ID": "AKIA" + "".join(random.choice(up) for _ in range(16)),
        "AWS_SECRET_ACCESS_KEY": secrets.token_urlsafe(30)[:40],
        "STRIPE_SECRET_KEY": "sk_live_" + secrets.token_hex(12),
        "OPENAI_API_KEY": "sk-proj-" + secrets.token_urlsafe(24),
        "DATABASE_URL": f"postgres://admin:{secrets.token_urlsafe(12)}@prod-db.internal:5432/app",
    }


def plant(directory: str, filename: str = ".env.production.bak") -> str:
    """Create a decoy env file in ``directory`` (never overwrites an existing file)."""
    d = Path(directory).expanduser().resolve()
    target = d / filename
    if target.exists():
        raise FileExistsError(f"{target} already exists; not overwriting")
    vals = _fake_values()
    target.write_text("# production secrets backup - do not commit\n" + "".join(f"{k}={v}\n" for k, v in vals.items()))
    data = load()
    data["files"].append({"path": str(target), "planted_at": time.time()})
    data["values"] += [v for k, v in vals.items() if k != "DATABASE_URL"] + [vals["DATABASE_URL"].split(":")[2].split("@")[0]]
    save(data)
    return str(target)


def remove(path: str) -> bool:
    data = load()
    before = len(data["files"])
    data["files"] = [f for f in data["files"] if f["path"] != path]
    if len(data["files"]) != before:
        try:
            os.remove(path)
        except OSError:
            pass
        save(data)
        return True
    return False


class HoneytokenIndex:
    def __init__(self):
        self.reload()

    def reload(self) -> None:
        data = load()
        self.values = [v for v in data.get("values", []) if len(v) >= 8]
        self.files = [f["path"] for f in data.get("files", [])]
        self.names = {os.path.basename(p) for p in self.files}

    def hit(self, text: str, paths: list[str]) -> str | None:
        for p in paths:
            if p in self.files:
                return p
        for v in self.values:
            if v in text:
                return "a planted fake key"
        for n in self.names:
            if n and n in text:
                return n
        return None
