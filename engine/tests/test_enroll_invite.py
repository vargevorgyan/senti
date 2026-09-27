"""Enrollment with a personal invite key, and Senti's own credentials counting as secrets."""
import types

import httpx

from senti import cli, sync
from senti.rules import find_secrets


def test_invite_key_and_device_token_are_secrets():
    assert "Senti invite key" in find_secrets("senti enroll --key sti_" + "A" * 43)
    assert "Senti device token" in find_secrets("Authorization: Bearer sdt_" + "b" * 43)


def test_enroll_sends_invite_not_email(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTI_HOME", str(tmp_path))
    sent = {}

    def fake_post(url, json=None, **kw):
        sent.update(json)
        return httpx.Response(200, json={"device_id": "d1", "device_token": "sdt_x", "public_key": "pk", "org_name": "Acme",
                                         "user": {"email": "anna@acme.test", "role": "product"}}, request=httpx.Request("POST", url))
    monkeypatch.setattr(sync.httpx, "post", fake_post)
    s = sync.enroll("http://localhost:8000", invite="sti_abc")
    assert sent["invite"] == "sti_abc" and "user_email" not in sent and "code" not in sent
    assert s.user_email == "anna@acme.test", "the person comes from the invite, not from what the employee typed"


def test_enroll_cli_requires_key_or_code_and_email(capsys):
    args = types.SimpleNamespace(backend="http://localhost:8000", key="", code="", email="", fingerprint="", insecure_http=False)
    assert cli.cmd_enroll(args) == 2
    assert "--key" in capsys.readouterr().err


def test_enroll_failure_is_a_clear_message_not_a_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SENTI_HOME", str(tmp_path))

    def fake_post(url, json=None, **kw):
        return httpx.Response(403, json={"detail": "this invite key was already used; if that wasn't you, tell your administrator"},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(sync.httpx, "post", fake_post)
    args = types.SimpleNamespace(backend="http://localhost:8000", key="sti_used", code="", email="", fingerprint="", insecure_http=False)
    assert cli.cmd_enroll(args) == 1
    err = capsys.readouterr().err
    assert err.startswith("Could not join the organization: this invite key was already used")
    assert "Traceback" not in err and "RuntimeError" not in err
