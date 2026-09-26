"""Undo / time machine: snapshot files before an agent changes or deletes them.

Uses APFS clones (``cp -c``) so snapshots are instant and take no extra space until files diverge.
``senti undo list`` / ``senti undo restore <id>``.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from .config import senti_home

MAX_FILES = 20000


def _root() -> Path:
    return senti_home() / "snapshots"


def _count(path: Path, cap: int) -> int:
    if path.is_file():
        return 1
    n = 0
    for _, _, files in os.walk(path):
        n += len(files)
        if n > cap:
            break
    return n


def snapshot(paths: list[str], meta: dict) -> dict | None:
    """Clone existing paths into a new snapshot. Returns the manifest, or None if nothing to save."""
    existing = [Path(p) for p in dict.fromkeys(paths) if p and os.path.lexists(p)]
    existing = [p for p in existing if not str(p).startswith(str(senti_home()))]
    if not existing:
        return None
    if sum(_count(p, MAX_FILES) for p in existing) > MAX_FILES:
        return {"skipped": True, "reason": f"more than {MAX_FILES} files"}
    sid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    dest = _root() / sid
    dest.mkdir(parents=True)
    items = []
    for i, p in enumerate(existing):
        target = dest / f"{i}"
        try:
            flag = ["-c"] if os.uname().sysname == "Darwin" else []
            r = subprocess.run(["cp", *flag, "-Rp", str(p), str(target)], capture_output=True, timeout=60)
            if r.returncode != 0:  # fall back to a normal copy (non-APFS volume)
                (shutil.copytree if p.is_dir() else shutil.copy2)(p, target)
            items.append({"original": str(p), "stored": str(target), "is_dir": p.is_dir()})
        except Exception as e:
            items.append({"original": str(p), "error": str(e)})
    manifest = {"id": sid, "created": time.time(), "items": items, **meta}
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def list_snapshots(limit: int = 50) -> list[dict]:
    out = []
    root = _root()
    if not root.exists():
        return out
    for d in sorted(root.iterdir(), reverse=True)[:limit]:
        m = d / "manifest.json"
        if m.exists():
            try:
                out.append(json.loads(m.read_text()))
            except Exception:
                pass
    return out


def restore(sid: str) -> list[str]:
    d = _root() / sid
    manifest = json.loads((d / "manifest.json").read_text())
    restored = []
    for it in manifest["items"]:
        if "stored" not in it:
            continue
        orig, stored = Path(it["original"]), Path(it["stored"])
        if orig.exists() or orig.is_symlink():
            aside = orig.with_name(orig.name + f".senti-replaced-{int(time.time())}")
            orig.rename(aside)
        orig.parent.mkdir(parents=True, exist_ok=True)
        flag = ["-c"] if os.uname().sysname == "Darwin" else []
        subprocess.run(["cp", *flag, "-Rp", str(stored), str(orig)], check=True, timeout=120)
        restored.append(str(orig))
    manifest["restored_at"] = time.time()
    (d / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return restored
