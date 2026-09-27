"""Joining from an invite link (server-confirmed company, no silent switching), device keys and signed requests, trusting
the organization's CA, and protecting assistants installed after setup."""
import base64
import hashlib
import os
import shutil
import stat
import sys
import types

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import load_der_public_key

from senti import cli, devicekey, installers, sync
from senti.config import Settings, senti_home, tls_verify

KEY = "sti_" + "A" * 43
FP = "ab" * 32


# ---------------------------------------------------------------- invite links
def test_parse_invite_link():
    inv = cli.parse_invite(f"'https://senti.acme.com:8443/join#s=senti.acme.com:8443&k={KEY}&fp={FP}'")
    assert inv == {"backend": "https://senti.acme.com:8443", "key": KEY, "fingerprint": FP}
    assert cli.parse_invite(f"https://x/join#s=10.0.0.5&k={KEY}")["fingerprint"] == ""


@pytest.mark.parametrize("link", [
    f"https://x/join#s=evil.com/steal?&k={KEY}",   # a path smuggled into the server
    f"https://x/join#s=a.com@evil.com&k={KEY}",   # user-info trick
    "https://x/join#s=senti.acme.com",            # no key
    f"https://x/join#s=senti.acme.com&k={KEY}&fp=zz",
    f"https://x/join?s=senti.acme.com&k={KEY}",   # not in the fragment
])
def test_malformed_invite_links_are_refused(link):
    with pytest.raises(ValueError):
        cli.parse_invite(link)


def _fake_server(monkeypatch, info=None, fail=None):
    calls = []

    def trust(backend, fp, insecure=False):
        calls.append(("trust", backend, fp))
        return Settings.load()

    def invite_info(backend, key, s):
        calls.append(("info", backend, key))
        if fail:
            raise RuntimeError(fail)
        return info or {"org_name": "Acme Corp", "email": "anna@acme.test", "role": "product"}

    def enroll(backend, fingerprint="", insecure_http=False, invite=""):
        calls.append(("enroll", backend, invite))
        s = Settings.load()
        s.backend_url, s.device_token, s.org_name, s.user_email, s.device_key_type = backend, "sdt_x", "Acme Corp", "anna@acme.test", "software"
        s.save()
        return s
    monkeypatch.setattr(sync, "server_trust", trust)
    monkeypatch.setattr(sync, "invite_info", invite_info)
    monkeypatch.setattr(sync, "enroll", enroll)
    return calls


def test_join_shows_what_the_server_says_and_needs_a_yes(monkeypatch, capsys):
    calls = _fake_server(monkeypatch)
    monkeypatch.setattr(cli, "_ask_yes_no", lambda q: False)
    assert cli._join("https://senti.acme.com", KEY, FP, assume_yes=False) == 1
    out = capsys.readouterr()
    assert "Acme Corp" in out.out and "anna@acme.test" in out.out and "Not joined" in out.err
    assert [c[0] for c in calls] == ["trust", "info"], "nothing is enrolled without a yes"
    monkeypatch.setattr(cli, "_ask_yes_no", lambda q: True)
    assert cli._join("https://senti.acme.com", KEY, FP, assume_yes=False) == 0
    assert calls[-1] == ("enroll", "https://senti.acme.com", KEY)


def test_no_terminal_means_no(monkeypatch):
    monkeypatch.setattr("builtins.open", lambda *a, **k: (_ for _ in ()).throw(OSError("no tty")))
    assert cli._ask_yes_no("Join? ") is False


def test_a_mac_is_never_moved_to_another_company_silently(monkeypatch, capsys):
    calls = _fake_server(monkeypatch)
    s = Settings.load()
    s.backend_url, s.device_token, s.org_name = "https://senti.acme.com", "sdt_old", "Acme Corp"
    s.save()
    assert cli._join("https://senti.evil.example", KEY, "", assume_yes=True) == 1
    assert "never moves a Mac" in capsys.readouterr().err and calls == []


def test_refused_invite_is_a_clear_message(monkeypatch, capsys):
    _fake_server(monkeypatch, fail='the server refused the invite: 403 {"detail":"this invite key was already used"}')
    assert cli._join("https://senti.acme.com", KEY, "", assume_yes=True) == 1
    err = capsys.readouterr().err
    assert "this invite key was already used" in err and "Traceback" not in err


def test_join_command_rejects_a_broken_link(capsys):
    assert cli.cmd_join(types.SimpleNamespace(link="https://x/join#s=only", yes=True, no_service=True)) == 2
    assert "Copy the whole link" in capsys.readouterr().err


# ---------------------------------------------------------------- device keys
def test_enroll_sends_a_new_device_key_and_keeps_it_private(monkeypatch):
    sent = {}

    def fake_post(url, json=None, **kw):
        sent.update(json)
        return httpx.Response(200, json={"device_id": "d1", "device_token": "sdt_x", "public_key": "pk", "org_name": "Acme",
                                         "user": {"email": "anna@acme.test"}}, request=httpx.Request("POST", url))
    monkeypatch.setattr(sync.httpx, "post", fake_post)
    s = sync.enroll("http://localhost:8000", invite=KEY)
    assert sent["key_type"] == "software" and s.device_key_type == "software"
    load_der_public_key(base64.b64decode(sent["device_key"]))  # a real public key
    key_file = senti_home() / devicekey.SOFT_KEY
    assert stat.S_IMODE(os.stat(key_file).st_mode) == 0o600
    assert "PRIVATE KEY" not in str(sent), "the private key never leaves the Mac"


def test_device_auth_signs_what_the_server_checks():
    pub, _ = devicekey.create()
    req = httpx.Request("POST", "https://srv/api/v1/judge?x=1", json={"a": 1})
    flow = devicekey.DeviceAuth("sdt_tok").sync_auth_flow(req)
    signed = next(flow)
    h = signed.headers
    assert h["authorization"] == "Bearer sdt_tok"
    msg = "\n".join(["senti-device-v1", "POST", "/api/v1/judge?x=1", h["x-senti-ts"], h["x-senti-nonce"],
                     hashlib.sha256(req.content).hexdigest()]).encode()
    load_der_public_key(base64.b64decode(pub)).verify(base64.b64decode(h["x-senti-signature"]), msg, ec.ECDSA(hashes.SHA256()))


def test_no_device_key_means_no_request():
    with pytest.raises(RuntimeError, match="no device key"):
        devicekey.sign(b"x")


def test_agents_cannot_use_the_device_key(project):
    from senti.rules import check_bash
    home = str(senti_home())
    for cmd in [f"{home}/bin/senti-key sign {home}/device-key.se", f"cat {home}/device-key.pem",
                "~/.senti/bin/senti-key sign ~/.senti/device-key.se", f"cp {home}/device-key.se /tmp/k"]:
        d, _ = check_bash(cmd, project, project)
        assert d and d.verdict == "block", cmd


@pytest.mark.skipif(sys.platform != "darwin" or not shutil.which("swiftc"), reason="needs macOS and the Swift compiler")
def test_secure_enclave_helper(monkeypatch, senti_home):
    import importlib
    real = importlib.reload(importlib.import_module("senti.devicekey"))  # the real helper, not the fixture's stub
    monkeypatch.setattr(devicekey, "helper", real.helper)
    assert str(senti_home) in str(devicekey._home()), "never touch the real ~/.senti in tests"
    pub, kind = devicekey.create()
    if kind != "secure-enclave":
        pytest.skip("this Mac has no Secure Enclave")
    sig = devicekey.sign(b"hello")
    load_der_public_key(base64.b64decode(pub)).verify(base64.b64decode(sig), b"hello", ec.ECDSA(hashes.SHA256()))
    assert not (senti_home / devicekey.SOFT_KEY).exists() and (senti_home / "bin" / "senti-key").exists()


# ---------------------------------------------------------------- trusting the organization's CA
def test_ca_fingerprint_must_match(monkeypatch):
    pem = "-----BEGIN CERTIFICATE-----\nMIIBfake\n-----END CERTIFICATE-----\n"
    monkeypatch.setattr(sync, "fetch_ca", lambda url: pem)
    monkeypatch.setattr("ssl.PEM_cert_to_DER_cert", lambda p: b"der-bytes")
    good = hashlib.sha256(b"der-bytes").hexdigest()
    assert sync.trusted_ca_pem("https://srv", good) == pem
    with pytest.raises(RuntimeError, match="may not be your company"):
        sync.trusted_ca_pem("https://srv", FP)


def test_fetch_ca_rejects_bundles(monkeypatch):
    two = "-----BEGIN CERTIFICATE-----\nA\n-----END CERTIFICATE-----\n" * 2
    monkeypatch.setattr(sync.httpx, "get", lambda *a, **k: httpx.Response(200, text=two, request=httpx.Request("GET", "https://s")))
    with pytest.raises(RuntimeError):
        sync.fetch_ca("https://srv")


def test_ca_trust_checks_host_names(tmp_path):
    import ssl
    import subprocess
    subprocess.run(["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes", "-days", "1",
                    "-subj", "/CN=t", "-keyout", str(tmp_path / "k"), "-out", str(tmp_path / "ca.pem")], check=True, capture_output=True)
    s = Settings.load()
    s.backend_cert, s.backend_cert_kind = str(tmp_path / "ca.pem"), "ca"
    ctx = tls_verify(s)
    assert isinstance(ctx, ssl.SSLContext) and ctx.check_hostname and ctx.verify_mode == ssl.CERT_REQUIRED
    s.backend_cert_kind = "leaf"
    assert tls_verify(s).check_hostname is False  # older joins: the one pinned certificate is the identity


# ---------------------------------------------------------------- assistants installed later
def test_new_assistants_are_protected_only_after_setup(monkeypatch):
    done = []
    monkeypatch.setattr(installers, "detected_agents", lambda: ["claude", "codex"])
    monkeypatch.setattr(installers, "INSTALL", {"claude": lambda p: done.append("claude"), "codex": lambda p: done.append("codex")})
    monkeypatch.setattr(installers, "build_hook", lambda: None)
    assert installers.protect_new_assistants() == [] and done == [], "nobody gets hooks they didn't ask for"
    installers.mark_protected(["claude"])
    assert installers.protect_new_assistants() == ["codex"] and done == ["codex"]
    assert installers.protect_new_assistants() == [], "once is enough"
    assert set(installers.protected_agents()) == {"claude", "codex"}
