"""Choosing where the company AI runs: the private model on this server, or a cloud / company API."""
from app import config, local_model


def put(client, headers, **body):
    return client.put("/api/v1/admin/settings/corporate-model", headers=headers, json=body)


def test_cloud_api_keeps_its_key_and_reports_kind(client, admin_headers):
    r = put(client, admin_headers, kind="api", url="https://openrouter.ai/api/v1", model="qwen/qwen3-235b-a22b-2507",
            api_key="sk-or-test", enabled=True)
    assert r.status_code == 200, r.text
    assert r.json()["kind"] == "api" and r.json()["api_key_set"] is True and "api_key" not in r.json()
    got = client.get("/api/v1/admin/settings/corporate-model", headers=admin_headers).json()
    assert got["kind"] == "api" and got["url"] == "https://openrouter.ai/api/v1"
    # saving again without a key keeps the saved one
    put(client, admin_headers, kind="api", url="https://openrouter.ai/api/v1", model="mistralai/mistral-small", enabled=True)
    assert client.get("/api/v1/admin/settings/corporate-model", headers=admin_headers).json()["api_key_set"] is True


def test_local_model_uses_the_fixed_address_and_drops_the_cloud_key(client, admin_headers):
    put(client, admin_headers, kind="api", url="https://openrouter.ai/api/v1", model="x", api_key="sk-or-test")
    r = put(client, admin_headers, kind="local", url="https://evil.example/v1", model="qwen2.5:3b")
    assert r.status_code == 200, r.text
    assert r.json()["url"] == config.settings.local_model_url and r.json()["kind"] == "local"
    assert r.json()["api_key_set"] is False, "a cloud key is never sent to the local model"


def test_older_clients_without_kind_still_work(client, admin_headers):
    r = put(client, admin_headers, url=config.settings.local_model_url, model="qwen2.5:3b")
    assert r.json()["kind"] == "local"
    r = put(client, admin_headers, url="https://api.openai.com/v1", model="gpt-4o-mini")
    assert r.json()["kind"] == "api"


def test_api_address_and_model_are_checked(client, admin_headers):
    assert put(client, admin_headers, kind="api", url="file:///etc/passwd", model="m").status_code == 422
    assert put(client, admin_headers, kind="api", url="https://api.openai.com/v1", model="  ").status_code == 422


def test_local_status_when_the_service_is_not_running(client, admin_headers, monkeypatch):
    monkeypatch.setattr(config.settings, "local_model_url", "http://127.0.0.1:9/v1")
    st = client.get("/api/v1/admin/corporate-model/local", headers=admin_headers).json()
    assert st["running"] is False and st["models"] == [] and st["recommended"]
    assert st["memory"].get("total_gb", 1) > 0
    r = client.post("/api/v1/admin/corporate-model/local/pull", headers=admin_headers, json={"model": "qwen2.5:3b"})
    assert r.status_code == 409 and "./senti-server install --ai local" in r.json()["detail"]


def test_model_names_are_checked_before_reaching_ollama():
    for bad in ["../etc", "Qwen", "a b", "x" * 200, "http://x"]:
        assert not local_model.MODEL_NAME.fullmatch(bad), bad
    for ok in ["qwen2.5:3b", "qwen3:4b-instruct", "library/llama3.1:8b"]:
        assert local_model.MODEL_NAME.fullmatch(ok), ok


def test_model_settings_need_an_admin(client):
    assert client.get("/api/v1/admin/corporate-model/local").status_code == 401
    assert client.post("/api/v1/admin/corporate-model/local/pull", json={"model": "qwen2.5:3b"}).status_code == 401
