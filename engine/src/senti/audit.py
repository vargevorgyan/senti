"""Append-only, hash-chained decision log (~/.senti/audit/decisions.jsonl) + batched upload to the org backend.

Each record carries ``prev`` (hash of the previous record) and ``hash``; ``verify()`` detects edits or deletions.
The directory is a guard path, so agents cannot write there through Senti-checked tools.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from pathlib import Path

from .config import senti_home


class AuditLog:
    def __init__(self, path: Path | None = None):
        self.path = path or senti_home() / "audit" / "decisions.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.last_hash = self._tail_hash()
        self.recent: list[dict] = self._load_recent(300)

    def _tail_hash(self) -> str:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return "0" * 64
        with open(self.path, "rb") as f:
            f.seek(max(0, self.path.stat().st_size - 65536))
            lines = f.read().splitlines()
        for ln in reversed(lines):
            try:
                return json.loads(ln)["hash"]
            except Exception:
                continue
        return "0" * 64

    def _load_recent(self, n: int) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        with open(self.path, "r", errors="replace") as f:
            for ln in f.readlines()[-n:]:
                try:
                    out.append(json.loads(ln))
                except Exception:
                    pass
        return out

    def append(self, record: dict) -> dict:
        with self.lock:
            rec = {"id": str(uuid.uuid4()), "ts": time.time(), **record, "prev": self.last_hash}
            body = json.dumps(rec, sort_keys=True, default=str)
            rec["hash"] = hashlib.sha256(body.encode()).hexdigest()
            with open(self.path, "a") as f:
                f.write(json.dumps(rec, default=str) + "\n")
            os.chmod(self.path, 0o600)
            self.last_hash = rec["hash"]
            self.recent.append(rec)
            del self.recent[:-300]
            return rec

    def verify(self) -> tuple[bool, int, str]:
        prev, n = "0" * 64, 0
        if not self.path.exists():
            return True, 0, ""
        with open(self.path) as f:
            for ln in f:
                rec = json.loads(ln)
                h = rec.pop("hash")
                if rec.get("prev") != prev:
                    return False, n, f"chain broken at record {n} ({rec.get('id')})"
                if hashlib.sha256(json.dumps(rec, sort_keys=True, default=str).encode()).hexdigest() != h:
                    return False, n, f"record {n} was modified ({rec.get('id')})"
                prev, n = h, n + 1
        return True, n, ""

    # -------------------------------------------------------------- upload bookkeeping
    def _state_path(self) -> Path:
        return self.path.parent / "upload.state"

    def pending(self, limit: int = 200) -> tuple[list[dict], int]:
        off = int(self._state_path().read_text() or 0) if self._state_path().exists() else 0
        out: list[dict] = []
        if not self.path.exists():
            return out, off
        with open(self.path, "rb") as f:
            f.seek(off)
            while len(out) < limit:
                ln = f.readline()
                if not ln:
                    break
                if not ln.endswith(b"\n"):
                    break
                try:
                    out.append(json.loads(ln))
                except Exception:
                    pass
                off = f.tell()
        return out, off

    def mark_uploaded(self, offset: int) -> None:
        self._state_path().write_text(str(offset))
