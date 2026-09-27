"""Secret brokering: agents only ever see placeholders like {{senti:STRIPE_KEY}}.

- Values live in the macOS Keychain (service "am.tumo.senti.secret"), or a 0600 file when SENTI_SECRET_STORE=file.
- Each secret lists the hosts it may be sent to; a command using it may contact only those hosts.
- When such a command is allowed, the engine rewrites it (hook `updatedInput`) to run through `senti.secret_exec` with a
  one-time grant bound to the exact command; the wrapper fetches the values, runs the command and masks the values in
  its output. The real value never appears in the agent's context.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets as _secrets
import subprocess
import sys
import time

from .config import senti_home

PLACEHOLDER = re.compile(r"\{\{\s*senti:([A-Za-z_][A-Za-z0-9_]{0,63})\s*\}\}")
SERVICE = "am.tumo.senti.secret"
GRANT_TTL_S = 120


def _meta_path():
    return senti_home() / "secrets.json"


def _use_file() -> bool:
    return os.environ.get("SENTI_SECRET_STORE") == "file" or sys.platform != "darwin"


def _load_meta() -> dict:
    try:
        return json.loads(_meta_path().read_text())
    except (OSError, ValueError):
        return {}


def _save_meta(meta: dict) -> None:
    p = _meta_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(meta, indent=1))
    os.chmod(p, 0o600)


def add(name: str, value: str, hosts: list[str]) -> None:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name):
        raise ValueError("secret names use letters, digits and _")
    meta = _load_meta()
    entry = {"hosts": [h.strip().lower() for h in hosts if h.strip()], "created": time.time()}
    if _use_file():
        entry["value"] = value
    else:
        subprocess.run(["security", "add-generic-password", "-U", "-s", SERVICE, "-a", name, "-w", value],
                       check=True, capture_output=True)
    meta[name] = entry
    _save_meta(meta)


def remove(name: str) -> bool:
    meta = _load_meta()
    if name not in meta:
        return False
    if not _use_file():
        subprocess.run(["security", "delete-generic-password", "-s", SERVICE, "-a", name], capture_output=True)
    del meta[name]
    _save_meta(meta)
    return True


def listing() -> dict:
    return {k: {"hosts": v.get("hosts", []), "created": v.get("created")} for k, v in _load_meta().items()}


def value(name: str) -> str | None:
    meta = _load_meta()
    if name not in meta:
        return None
    if "value" in meta[name]:
        return meta[name]["value"]
    r = subprocess.run(["security", "find-generic-password", "-s", SERVICE, "-a", name, "-w"], capture_output=True, text=True)
    return r.stdout.rstrip("\n") if r.returncode == 0 else None


def names_in(text: str) -> list[str]:
    return list(dict.fromkeys(PLACEHOLDER.findall(text or "")))


def neutral(text: str) -> str:
    """The command as the rules and the judge see it (no secret values, a recognisable marker)."""
    return PLACEHOLDER.sub(lambda m: f"SENTI_SECRET_{m.group(1)}", text)


class Grants:
    """One-time, short-lived permissions for secret_exec to fetch values for one exact command."""

    def __init__(self):
        self.grants: dict[str, dict] = {}

    def issue(self, names: list[str], command: str) -> str:
        now = time.time()
        for k in [k for k, g in self.grants.items() if g["exp"] < now]:
            self.grants.pop(k, None)
        gid = _secrets.token_urlsafe(24)
        self.grants[gid] = {"names": names, "cmd": hashlib.sha256(command.encode()).hexdigest(), "exp": now + GRANT_TTL_S}
        return gid

    def redeem(self, gid: str, command: str) -> dict[str, str] | None:
        g = self.grants.pop(gid, None)  # single use
        if not g or g["exp"] < time.time() or g["cmd"] != hashlib.sha256(command.encode()).hexdigest():
            return None
        out = {}
        for n in g["names"]:
            v = value(n)
            if v is None:
                return None
            out[n] = v
        return out


def wrap(command: str, grant: str) -> str:
    """The command the agent will actually run: the wrapper with the original (placeholder) command."""
    import shlex
    return f"{shlex.quote(sys.executable)} -m senti.secret_exec {grant} -- {shlex.quote(command)}"
