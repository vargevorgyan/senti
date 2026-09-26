"""Package supply-chain check: offline known-malicious list + typosquat detection against popular packages."""
from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources

from .models import Decision

ECOSYSTEM = {"npm": "npm", "pnpm": "npm", "yarn": "npm", "bun": "npm", "npx": "npm", "pip": "pypi", "pip3": "pypi",
             "uv": "pypi", "poetry": "pypi", "pipx": "pypi", "gem": "rubygems", "cargo": "crates", "brew": "brew"}


@lru_cache
def _data() -> dict:
    return json.loads(resources.files("senti.data").joinpath("packages.json").read_text())


def _norm(name: str, eco: str) -> str:
    n = name.strip().lower()
    if eco == "npm":
        if n.startswith("@"):
            n = "@" + n[1:].split("@")[0]
        else:
            n = n.split("@")[0]
    else:
        for sep in ("==", ">=", "<=", "~=", "!=", ">", "<", "[", ";"):
            n = n.split(sep)[0]
        n = n.replace("_", "-")
    return n


def _dist(a: str, b: str) -> int:
    if abs(len(a) - len(b)) > 2:
        return 3
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def check_package(manager: str, raw: str) -> Decision | None:
    eco = ECOSYSTEM.get(manager, "npm")
    name = _norm(raw, eco)
    d = _data()
    if name in d.get("malicious", {}).get(eco, []):
        return Decision("block", f"Installs '{name}', a package known to be malicious", "L2-supply-chain", "malicious_package",
                        severity="critical")
    popular = d.get("popular", {}).get(eco, [])
    if name in popular or not name:
        return Decision("allow", f"Installs a well-known package ({name})", "L2-supply-chain", "popular_package")
    for p in popular:
        if len(name) >= 4 and _dist(name, p) == 1 or name.replace("-", "") == p.replace("-", "") and name != p:
            return Decision("ask", f"Installs '{name}', which looks like a misspelling of the popular package '{p}' (typosquatting)",
                            "L2-supply-chain", "typosquat", severity="warning")
    return None  # unknown package → profile / judge
