"""Policy profiles: schema, signature verification, local cache and evaluation.

A profile is pushed by the org backend (signed with the org's Ed25519 key) or, in personal mode, the
built-in ``personal`` profile is used. Hooks never call the backend per action: the engine evaluates the
cached profile locally.

Evaluation returns the *strictest* of the role profile and the agent-specific override (delegation rule:
an agent never gets more than its user).
"""
from __future__ import annotations

import base64
import fnmatch
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .config import senti_home
from .models import Action, Decision, strictest
from .rules import HOME, expand, host_matches, short

JUDGE_MODES = ("local", "corporate", "local_then_corporate", "none")
OTHERWISE = ("allow", "ask", "block", "judge")

PERSONAL_PROFILE: dict[str, Any] = {
    "id": "personal",
    "name": "Personal (built-in)",
    "version": 1,
    "description": "Default local profile used when this Mac is not enrolled in an organization.",
    "applies_to": {"roles": [], "agents": []},
    "rules": {
        "files": {"allow": [], "deny": [], "ask": []},
        "network": {"allow": [], "deny": [], "ask": [], "otherwise": "judge"},
        "shell": {"allow": [], "deny": [], "ask": [], "otherwise": "judge"},
        "mcp": {"allow": [], "deny": [], "otherwise": "judge"},
        "packages": "check_supply_chain",
    },
    "judge": {"mode": "local", "instructions": "", "send_to_corporate": "metadata_only"},
    "on_backend_unreachable": "strict_local",
    "approvals": {"ask_goes_to": "user"},
    "features": {"undo": True, "honeytokens": True, "injection_scan": True, "scope_contract": False, "sandbox": False},
    "agent_overrides": {},
}


STRICT_PROFILE: dict[str, Any] = {
    **PERSONAL_PROFILE,
    "id": "strict-offline",
    "name": "Strict (no verified organization profile)",
    "description": "Used when this Mac is enrolled but has no valid signed profile yet: unknown sites and packages need a yes.",
    "rules": {**PERSONAL_PROFILE["rules"], "network": {"allow": [], "deny": [], "ask": [], "otherwise": "ask"}, "packages": "ask"},
}


def glob_to_regex(pat: str) -> re.Pattern:
    pat = pat.replace("\\", "/")
    out, i = "", 0
    while i < len(pat):
        c = pat[i]
        if pat.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
            continue
        if pat.startswith("**", i):
            out += ".*"
            i += 2
            continue
        out += {"*": "[^/]*", "?": "[^/]"}.get(c, re.escape(c))
        i += 1
    return re.compile("^" + out + "$")


def path_matches(path: str, patterns: list[str], cwd: str = "/") -> str | None:
    for p in patterns or []:
        pe = expand(p, cwd) if p.startswith(("~", "/", "$HOME")) else p
        if not pe.startswith("/"):
            # relative/unanchored pattern such as "**/.env*" matches anywhere
            if glob_to_regex("**/" + pe.lstrip("./")).match(path):
                return p
            continue
        rx = glob_to_regex(pe)
        if rx.match(path) or rx.match(path + "/") or (pe.endswith("/**") and path == pe[:-3]):
            return p
    return None


def _normalised_segments(cmd: str) -> list[str]:
    """Each command segment as '<program basename> <args>' with sudo/env/command wrappers and git globals removed."""
    from .rules import program, split_segments, substitutions
    out = []
    for c in [cmd, *substitutions(cmd)]:
        for seg in split_segments(c):
            prog, args, _ = program(seg)
            if not prog:
                continue
            if prog == "git":
                i = 0
                while i < len(args) and args[i].startswith("-"):
                    i += 2 if args[i] in {"-C", "-c", "--git-dir", "--work-tree"} else 1
                args = args[i:]
            out.append(" ".join([prog, *args]))
    return out


def cmd_matches(cmd: str, patterns: list[str]) -> str | None:
    norm = " ".join(cmd.split())
    segs = _normalised_segments(cmd)
    for p in patterns or []:
        if p.startswith("re:"):
            if re.search(p[3:], norm) or any(re.search(p[3:], sg) for sg in segs):
                return p
            continue
        stem = p.rstrip("*").strip()
        for cand in [norm, *segs]:
            if fnmatch.fnmatchcase(cand, p) or fnmatch.fnmatchcase(cand, p + " *") or cand == stem or \
                    (stem and (cand.startswith(stem + " ") or (p.endswith("*") and cand.startswith(stem)))):
                return p
    return None


NONE_ALLOWED = "__senti_nothing__"
_RANKS = {
    "otherwise": {"allow": 0, "judge": 1, "ask": 2, "block": 3},
    "outside_allow": {"allow": 0, "ask": 1, "block": 2},
    "write": {"allow": 0, "ask": 1, "block": 2},
    "packages": {"allow": 0, "check_supply_chain": 1, "ask": 2, "block": 3},
    "ask_goes_to": {"user": 0, "owner": 1, "admin": 2},
}


def _stricter(kind: str, a, b):
    r = _RANKS[kind]
    if a is None:
        return b
    if b is None:
        return a
    return b if r.get(b, 1) > r.get(a, 1) else a


def merge_override(base: dict, over: dict) -> dict:
    """An agent override can only *narrow* the role profile (delegation rule: an agent never gets more than its user).

    deny/ask lists are unioned; allow lists are intersected (an empty intersection allows nothing); every scalar takes
    the stricter value; protective features can be switched on but not off; the judge mode may be changed.
    """
    import copy
    out = copy.deepcopy(base)
    for sect, rules in (over.get("rules") or {}).items():
        if not isinstance(rules, dict):
            if sect == "packages":
                out["rules"]["packages"] = _stricter("packages", out["rules"].get("packages", "check_supply_chain"), rules)
            continue
        dst = out["rules"].setdefault(sect, {})
        for k, v in rules.items():
            if k in {"deny", "ask"}:
                dst[k] = list(dict.fromkeys((dst.get(k) or []) + list(v or [])))
            elif k == "allow":
                if dst.get(k):
                    inter = [x for x in dst[k] if x in (v or [])]
                    dst[k] = inter or [NONE_ALLOWED]
                elif sect == "files" and v:
                    dst[k] = list(v)
                elif sect != "files":
                    dst[k] = [x for x in (dst.get(k) or []) if x in (v or [])]
            elif k in _RANKS:
                dst[k] = _stricter(k, dst.get(k), v)
            # other keys are not overridable
    if "judge" in over and isinstance(over["judge"], dict) and over["judge"].get("mode"):
        out["judge"] = {**out.get("judge", {}), "mode": over["judge"]["mode"]}
    feats = dict(out.get("features") or {})
    for k, v in (over.get("features") or {}).items():
        feats[k] = bool(feats.get(k)) and bool(v) if k == "scope_contract" else bool(feats.get(k)) or bool(v)
    out["features"] = feats
    if isinstance(over.get("approvals"), dict) and over["approvals"].get("ask_goes_to"):
        cur = (out.get("approvals") or {}).get("ask_goes_to", "user")
        out["approvals"] = {**(out.get("approvals") or {}), "ask_goes_to": _stricter("ask_goes_to", cur, over["approvals"]["ask_goes_to"])}
    return out


@dataclass
class ProfileSet:
    """What the engine holds: the signed bundle for this device and which profile each agent uses."""

    profiles: dict[str, dict] = field(default_factory=lambda: {"personal": PERSONAL_PROFILE})
    default: str = "personal"
    assignments: dict[str, str] = field(default_factory=dict)  # agent -> profile id
    user: dict = field(default_factory=dict)
    fetched_at: float = 0.0
    bundle_version: int = 0
    source: str = "builtin"  # builtin | backend | cache

    def for_agent(self, agent: str) -> dict:
        pid = self.assignments.get(agent) or self.default
        prof = self.profiles.get(pid) or self.profiles.get(self.default) or PERSONAL_PROFILE
        over = (prof.get("agent_overrides") or {}).get(agent)
        return merge_override(prof, over) if over else prof


def verify_bundle(signed: dict, public_key_b64: str) -> dict:
    """signed = {payload: <json string>, signature: <b64>}; raises ValueError if tampered."""
    if not public_key_b64:
        raise ValueError("no pinned org key")
    key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
    try:
        key.verify(base64.b64decode(signed["signature"]), signed["payload"].encode())
    except (InvalidSignature, KeyError) as e:
        raise ValueError("profile signature is invalid") from e
    return json.loads(signed["payload"])


def cache_path() -> Path:
    return senti_home() / "profiles.signed.json"


def load_cached(public_key_b64: str, device_id: str = "") -> ProfileSet | None:
    p = cache_path()
    if not p.exists():
        return None
    try:
        payload = verify_bundle(json.loads(p.read_text()), public_key_b64)
    except Exception:
        return None  # tampered cache is ignored (never trusted)
    if device_id and payload.get("device_id") not in (None, device_id):
        return None  # a bundle signed for another device (possibly another role) is not accepted
    ps = bundle_to_set(payload)
    ps.source = "cache"
    return ps


def bundle_to_set(payload: dict) -> ProfileSet:
    profiles = {p["id"]: p for p in payload.get("profiles", [])}
    for p in profiles.values():
        for k, v in PERSONAL_PROFILE.items():
            p.setdefault(k, v)
        p["rules"] = {**PERSONAL_PROFILE["rules"], **(p.get("rules") or {})}
    profiles.setdefault("personal", PERSONAL_PROFILE)
    return ProfileSet(profiles=profiles, default=payload.get("default") or next(iter(profiles)),
                      assignments=payload.get("assignments", {}), user=payload.get("user", {}),
                      fetched_at=time.time(), bundle_version=payload.get("version", 0), source="backend")


def save_cache(signed: dict) -> None:
    p = cache_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(signed))
    os.chmod(tmp, 0o600)
    tmp.replace(p)


# ---------------------------------------------------------------- evaluation
def _d(verdict: str, reason: str, rule: str, severity: str = "info") -> Decision:
    return Decision(verdict, reason, "L1-profile", rule, severity=severity)  # type: ignore[arg-type]


def evaluate(profile: dict, action: Action, facts: dict, project: str) -> tuple[Decision | None, str | None]:
    """Returns (explicit decision or None, 'otherwise' policy for the grey zone: allow|ask|block|judge)."""
    rules = profile.get("rules") or {}
    name = profile.get("name", profile.get("id", "profile"))
    files, net, shell, mcp = (rules.get(k) or {} for k in ("files", "network", "shell", "mcp"))
    decisions: list[Decision | None] = []
    otherwise: str | None = None
    cwd = action.cwd or project

    paths = list(facts.get("paths") or [])
    for key in ("scripts", "deletes", "writes"):
        paths += facts.get(key) or []
    for p in paths:
        if m := path_matches(p, files.get("deny"), cwd):
            decisions.append(_d("block", f"Touches {short(p)}, which your organization's '{name}' profile forbids ({m})",
                                "files_deny", "critical"))
        elif m := path_matches(p, files.get("ask"), cwd):
            decisions.append(_d("ask", f"Touches {short(p)}; the '{name}' profile asks before that ({m})", "files_ask", "warning"))

    hosts = [h for h in (facts.get("hosts") or []) if h]
    if action.tool == "WebFetch" and not hosts:
        from urllib.parse import urlparse
        hosts = [urlparse(action.input.get("url", "")).hostname or ""]
    uses_net = bool(hosts) or facts.get("net")
    for h in hosts:
        if host_matches(h, net.get("deny") or []):
            decisions.append(_d("block", f"Connects to {h}, which the '{name}' profile blocks", "network_deny", "critical"))
        elif host_matches(h, net.get("ask") or []):
            decisions.append(_d("ask", f"Connects to {h}; the '{name}' profile needs your approval for that", "network_ask", "warning"))
    if uses_net:
        if hosts and all(host_matches(h, net.get("allow") or []) for h in hosts) and not facts.get("reads_sensitive") \
                and not any(host_matches(h, net.get("ask") or []) for h in hosts):
            decisions.append(_d("allow", f"Connects only to sites the '{name}' profile allows ({', '.join(sorted(set(hosts)))})",
                                "network_allow"))
        else:
            o = net.get("otherwise", "judge")
            if o in {"ask", "block"}:
                where = ", ".join(sorted(set(hosts))) or "the internet"
                decisions.append(_d(o, f"Connects to {where}; the '{name}' profile "
                                       f"{'does not allow this' if o == 'block' else 'asks before other sites'}",
                                    f"network_{o}", "warning" if o == "ask" else "critical"))
            otherwise = o

    if action.tool == "Bash":
        cmd = action.input.get("command", "")
        if m := cmd_matches(cmd, shell.get("deny")):
            decisions.append(_d("block", f"Runs `{m}`, which the '{name}' profile forbids", "shell_deny", "critical"))
        elif m := cmd_matches(cmd, shell.get("ask")):
            decisions.append(_d("ask", f"Runs `{m}`; the '{name}' profile asks before that", "shell_ask", "warning"))
        elif m := cmd_matches(cmd, shell.get("allow")):
            decisions.append(_d("allow", f"Allowed by the '{name}' profile ({m})", "shell_allow"))
        so = shell.get("otherwise", "judge")
        if so == "block" and not any(d and d.verdict == "allow" for d in decisions):
            decisions.append(_d("block", f"The '{name}' profile does not allow this agent to run shell commands", "shell_block",
                                "critical"))
        otherwise = _stricter_otherwise(otherwise, so)

    if action.tool.startswith("mcp__"):
        tool = action.tool
        if host_like := cmd_matches(tool, mcp.get("deny")):
            decisions.append(_d("block", f"Uses the tool {tool}, which the '{name}' profile blocks ({host_like})", "mcp_deny",
                                "critical"))
        elif cmd_matches(tool, mcp.get("allow")):
            decisions.append(_d("allow", f"Uses an allowed tool ({tool})", "mcp_allow"))
        otherwise = _stricter_otherwise(otherwise, mcp.get("otherwise", "judge"))

    if action.tool in {"Write", "Edit", "MultiEdit"} and files.get("write") in {"ask", "block"}:
        v = files["write"]
        decisions.append(_d(v, f"The '{name}' profile {'does not allow' if v == 'block' else 'asks before'} changing files",
                            f"files_write_{v}", "warning"))
    for p in paths:
        if files.get("allow") and not path_matches(p, [x for x in files.get("allow") if x != NONE_ALLOWED], cwd) \
                and not p.startswith(("/tmp", "/private/tmp")):
            if files.get("outside_allow", "ask") in {"ask", "block"}:
                v = files.get("outside_allow", "ask")
                decisions.append(_d(v, f"Touches {short(p)}, outside the folders the '{name}' profile allows", "files_outside",
                                    "warning"))
    return strictest(*decisions), otherwise


def _stricter_otherwise(a: str | None, b: str | None) -> str | None:
    rank = {None: -1, "allow": 0, "judge": 1, "ask": 2, "block": 3}
    return a if rank.get(a, 1) >= rank.get(b, 1) else b
