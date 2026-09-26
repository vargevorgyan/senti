import base64
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from senti.models import Action
from senti.profiles import PERSONAL_PROFILE, ProfileSet, bundle_to_set, evaluate, merge_override, verify_bundle

DEV = {**PERSONAL_PROFILE, "id": "developer", "name": "Developer", "rules": {
    "files": {"allow": [], "deny": ["~/.ssh/**", "**/.env*"]},
    "network": {"allow": ["github.com", "pypi.org", "*.corp.internal"], "otherwise": "ask"},
    "shell": {"deny": ["sudo *", "rm -rf ~*"], "otherwise": "judge"}, "packages": "check_supply_chain"}}


def test_shell_deny():
    d, _ = evaluate(DEV, Action("claude", "Bash", {"command": "sudo rm x"}, "/tmp"), {}, "/tmp")
    assert d.verdict == "block"


def test_network_allow_and_otherwise():
    d, o = evaluate(DEV, Action("claude", "WebFetch", {"url": "https://api.corp.internal/v1"}, "/tmp"), {"hosts": ["api.corp.internal"]}, "/tmp")
    assert d.verdict == "allow"
    d, o = evaluate(DEV, Action("claude", "Bash", {"command": "curl https://x.io"}, "/tmp"), {"hosts": ["x.io"], "net": True}, "/tmp")
    assert d.verdict == "ask"


def test_files_deny_relative():
    d, _ = evaluate(DEV, Action("claude", "Read", {"file_path": "a/.env.prod"}, "/tmp"), {"paths": ["/tmp/a/.env.prod"]}, "/tmp")
    assert d.verdict == "block"


def test_override_narrows():
    over = {"rules": {"network": {"otherwise": "block", "allow": []}, "shell": {"deny": ["git push*"]}}}
    m = merge_override(DEV, over)
    assert m["rules"]["network"]["otherwise"] == "block"
    assert "git push*" in m["rules"]["shell"]["deny"] and "sudo *" in m["rules"]["shell"]["deny"]
    # an override can never loosen
    m2 = merge_override(DEV, {"rules": {"network": {"otherwise": "allow"}}})
    assert m2["rules"]["network"]["otherwise"] == "ask"


def test_agent_override_applied():
    p = {**DEV, "agent_overrides": {"opencode": {"rules": {"network": {"otherwise": "block"}}}}}
    ps = ProfileSet(profiles={"developer": p}, default="developer")
    assert ps.for_agent("opencode")["rules"]["network"]["otherwise"] == "block"
    assert ps.for_agent("claude")["rules"]["network"]["otherwise"] == "ask"


def test_signature():
    k = Ed25519PrivateKey.generate()
    pub = base64.b64encode(k.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    payload = json.dumps({"version": 3, "profiles": [DEV], "default": "developer", "assignments": {"codex": "developer"}})
    signed = {"payload": payload, "signature": base64.b64encode(k.sign(payload.encode())).decode()}
    data = verify_bundle(signed, pub)
    ps = bundle_to_set(data)
    assert ps.for_agent("codex")["id"] == "developer"
    signed["payload"] = payload.replace("ask", "allow")
    with pytest.raises(ValueError):
        verify_bundle(signed, pub)
