"""Package supply-chain check: offline known-malicious list + typosquat detection against popular packages."""
from __future__ import annotations

import json
import re
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
    """Edit distance where swapping two neighbouring letters counts as one edit ("reqeusts" → "requests")."""
    if abs(len(a) - len(b)) > 2:
        return 3
    d = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        d[i][0] = i
    for j in range(len(b) + 1):
        d[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[-1][-1]


def _typosquat_of(name: str, eco: str, d: dict) -> tuple[str, str] | None:
    """The popular package `name` (or its leading part, e.g. "reqeusts" in "reqeusts-http-lib") imitates, in any ecosystem."""
    # agents mix up JavaScript and Python names ("requests" on npm), not names from unrelated ecosystems
    related = {"npm": ["pypi"], "pypi": ["npm"]}.get(eco, [])
    ecos = [eco] + [e for e in related if e in d.get("popular", {})]
    known = {p for e in ecos for p in d.get("popular", {}).get(e, [])}
    parts = {name}
    head = re.split(r"[-_.]", name.lstrip("@").split("/")[-1])[0]
    if len(head) >= 5 and head not in known:  # "react-query" builds on "react"; it doesn't imitate "preact"
        parts.add(head)
    for e in ecos:
        for p in d.get("popular", {}).get(e, []):
            for part in parts:
                if len(part) >= 4 and (_dist(part, p) == 1 or (part.replace("-", "") == p.replace("-", "") and part != p)):
                    return p, e
    return None


URL_SPEC = re.compile(r"(://|^git\+|^github:|^gitlab:|^bitbucket:|^file:|^link:|\.tgz$|\.tar\.gz$|\.whl$|\.zip$|^[\w.-]+/[\w.-]+$|\s*@\s*\w+://)")


def check_package(manager: str, raw: str) -> Decision | None:
    eco = ECOSYSTEM.get(manager, "npm")
    spec = raw.strip()
    if eco == "npm" and "@npm:" in spec:
        spec = spec.split("@npm:", 1)[1]  # alias: `lodash@npm:evil` really installs `evil`
        raw = spec
    if URL_SPEC.search(spec.split("@", 1)[-1] if eco == "npm" and not spec.startswith("@") else spec) or URL_SPEC.search(spec):
        return Decision("ask", f"Installs a package straight from a URL, git or a file ({spec[:80]}), skipping the registry's checks",
                        "L2-supply-chain", "url_package", severity="warning")
    name = _norm(raw, eco)
    d = _data()
    if name in d.get("malicious", {}).get(eco, []):
        return Decision("block", f"Installs '{name}', a package known to be malicious", "L2-supply-chain", "malicious_package",
                        severity="critical")
    if name in d.get("hallucinated", {}).get(eco, []):
        return Decision("ask", f"Installs '{name}', a package name AI models are known to invent (slopsquatting target)",
                        "L2-supply-chain", "hallucinated_package", severity="warning")
    popular = d.get("popular", {}).get(eco, [])
    if name in popular or not name:
        return Decision("allow", f"Installs a well-known package ({name})", "L2-supply-chain", "popular_package")
    hit = _typosquat_of(name, eco, d)
    if hit:
        p, e = hit
        where = "" if e == eco else f" ({e})"
        return Decision("ask", f"Installs '{name}', which looks like a misspelling of the popular package '{p}'{where} (typosquatting)",
                        "L2-supply-chain", "typosquat", severity="warning")
    return None  # unknown package → profile / judge
