import importlib
import os
import sys

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SENTI_DEMO_ENROLL_CODE", "SENTI-DEMO")
    for m in [m for m in list(sys.modules) if m == "app" or m.startswith("app.")]:
        del sys.modules[m]
    from fastapi.testclient import TestClient
    main = importlib.import_module("app.main")
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def admin_headers(client):
    r = client.post("/api/v1/auth/login", json={"email": "admin@senti.local", "password": "senti-admin"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def device(client):
    r = client.post("/api/v1/devices/enroll", json={"code": "SENTI-DEMO", "user_email": "dev@acme.test", "hostname": "mac-1"})
    assert r.status_code == 200, r.text
    d = r.json()
    d["headers"] = {"Authorization": f"Bearer {d['device_token']}"}
    return d
