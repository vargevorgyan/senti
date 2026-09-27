"""The first admin account is never created with an empty password, and its email works regardless of case."""
import importlib
import sys

from fastapi.testclient import TestClient


def start(tmp_path, monkeypatch, **env):
    monkeypatch.setenv("SENTI_DATA_DIR", str(tmp_path))
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    for m in [m for m in list(sys.modules) if m == "app" or m.startswith("app.")]:
        del sys.modules[m]
    return TestClient(importlib.import_module("app.main").app)


def test_empty_password_gets_a_random_one(tmp_path, monkeypatch, capsys):
    with start(tmp_path, monkeypatch, SENTI_ADMIN_PASSWORD="", SENTI_ADMIN_EMAIL="admin@acme.test") as c:
        assert c.post("/api/v1/auth/login", json={"email": "admin@acme.test", "password": ""}).status_code in (401, 422)
        printed = capsys.readouterr().out
        pw = printed.split("one-time password: ")[1].split()[0]
        assert c.post("/api/v1/auth/login", json={"email": "admin@acme.test", "password": pw}).status_code == 200


def test_admin_email_is_case_insensitive(tmp_path, monkeypatch):
    with start(tmp_path, monkeypatch, SENTI_ADMIN_PASSWORD="long-enough-pass", SENTI_ADMIN_EMAIL="Admin@Acme.Test") as c:
        assert c.post("/api/v1/auth/login", json={"email": "admin@acme.test", "password": "long-enough-pass"}).status_code == 200
