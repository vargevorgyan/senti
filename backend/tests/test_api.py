import base64
import json
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def verify(signed, pub):
    Ed25519PublicKey.from_public_bytes(base64.b64decode(pub)).verify(base64.b64decode(signed["signature"]), signed["payload"].encode())
    return json.loads(signed["payload"])


def test_login_rejects_bad_password(client):
    assert client.post("/api/v1/auth/login", json={"email": "admin@senti.local", "password": "x"}).status_code == 401
    assert client.get("/api/v1/admin/overview").status_code == 401


def test_seeded_profiles(client, admin_headers):
    ps = client.get("/api/v1/admin/profiles", headers=admin_headers).json()
    assert {p["id"] for p in ps} >= {"developer", "pm", "autonomous-agent"}


def test_enroll_and_signed_bundle(client, device):
    signed = client.get("/api/v1/device/profiles", headers=device["headers"]).json()
    data = verify(signed, device["public_key"])
    assert data["user"]["email"] == "dev@acme.test" and data["default"] == "developer"
    assert data["assignments"]["claude"] == "developer"
    assert client.post("/api/v1/devices/enroll", json={"code": "WRONG", "user_email": "a@b.c"}).status_code == 403


def test_profile_update_bumps_version_and_changes_bundle(client, admin_headers, device):
    v1 = verify(client.get("/api/v1/device/profiles", headers=device["headers"]).json(), device["public_key"])["version"]
    p = client.get("/api/v1/admin/profiles/developer", headers=admin_headers).json()
    p["data"]["judge"]["mode"] = "corporate"
    p["data"]["agent_overrides"] = {"opencode": {"rules": {"network": {"otherwise": "block"}}}}
    r = client.put("/api/v1/admin/profiles/developer", headers=admin_headers, json=p)
    assert r.status_code == 200 and r.json()["version"] == 2
    b = verify(client.get("/api/v1/device/profiles", headers=device["headers"]).json(), device["public_key"])
    assert b["version"] > v1
    dev = next(x for x in b["profiles"] if x["id"] == "developer")
    assert dev["judge"]["mode"] == "corporate" and dev["agent_overrides"]["opencode"]


def test_profile_validation(client, admin_headers):
    r = client.post("/api/v1/admin/profiles", headers=admin_headers, json={"name": "Bad", "data": {"judge": {"mode": "yolo"}}})
    assert r.status_code == 422
    r = client.post("/api/v1/admin/profiles", headers=admin_headers, json={"name": "Contractors"})
    assert r.status_code == 201 and r.json()["id"] == "contractors"


def test_user_override_assignment(client, admin_headers, device):
    users = client.get("/api/v1/admin/users", headers=admin_headers).json()
    u = next(x for x in users if x["email"] == "dev@acme.test")
    r = client.put(f"/api/v1/admin/users/{u['id']}", headers=admin_headers,
                   json={"email": u["email"], "name": "Dev", "role_id": "engineering", "agent_profiles": {"codex": "autonomous-agent"}})
    assert r.status_code == 200
    b = verify(client.get("/api/v1/device/profiles", headers=device["headers"]).json(), device["public_key"])
    assert b["assignments"]["codex"] == "autonomous-agent"
    eff = client.get(f"/api/v1/admin/users/{u['id']}/effective", headers=admin_headers).json()
    assert eff["assignments"]["codex"] == "autonomous-agent"


def test_events_ingest_and_overview(client, admin_headers, device):
    evs = [{"id": f"e{i}", "ts": time.time(), "agent": "claude", "tool": "Bash", "verdict": v, "layer": "L1-rules", "rule": "r",
            "reason": "x", "input": {"command": "ls"}} for i, v in enumerate(["allow", "allow", "block", "ask"])]
    assert client.post("/api/v1/events", headers=device["headers"], json={"events": evs}).json()["stored"] == 4
    assert client.post("/api/v1/events", headers=device["headers"], json={"events": evs}).json()["stored"] == 0  # idempotent
    ov = client.get("/api/v1/admin/overview", headers=admin_headers).json()
    assert ov["by_verdict"] == {"allow": 2, "ask": 1, "block": 1} and ov["devices"]["total"] == 1
    lst = client.get("/api/v1/admin/events?verdict=block", headers=admin_headers).json()
    assert lst["total"] == 1
    assert client.get("/api/v1/admin/events.csv", headers=admin_headers).status_code == 200


def test_approval_flow(client, admin_headers, device):
    r = client.post("/api/v1/approvals", headers=device["headers"], json={"agent": "codex", "tool": "Bash", "summary": "push to prod",
                                                                          "input": {"command": "git push"}})
    aid = r.json()["id"]
    assert client.get(f"/api/v1/approvals/{aid}", headers=device["headers"]).json()["status"] == "pending"
    pend = client.get("/api/v1/admin/approvals?status=pending", headers=admin_headers).json()
    assert pend and pend[0]["id"] == aid
    r = client.post(f"/api/v1/admin/approvals/{aid}/decide", headers=admin_headers, json={"decision": "approve"})
    assert r.json()["status"] == "approved"
    assert client.get(f"/api/v1/approvals/{aid}", headers=device["headers"]).json()["decided_by"] == "admin@senti.local"


def test_judge_gateway(client, device, monkeypatch):
    from app import corporate
    seen = {}

    async def fake(cfg, task, action, content, instructions, facts, timeout=25, allow_threshold=0.6):
        seen.update(instructions=instructions, action=action)
        return {"verdict": "ask", "reason": "prod db", "p": {"ask": 1.0}, "model": cfg["model"], "ms": 1}
    monkeypatch.setattr(corporate, "judge", fake)
    r = client.post("/api/v1/judge", headers=device["headers"], json={"profile_id": "developer", "task": "t", "action": {"tool": "Bash"}})
    assert r.status_code == 200 and r.json()["verdict"] == "ask"
    assert "prod.corp.internal" in seen["instructions"]


def test_judge_gateway_down_is_502(client, device, admin_headers):
    client.put("/api/v1/admin/settings/corporate-model", headers=admin_headers,
               json={"url": "http://127.0.0.1:9/v1", "model": "none", "enabled": True})
    r = client.post("/api/v1/judge", headers=device["headers"], json={"action": {"tool": "Bash"}})
    assert r.status_code == 502


def test_revoked_device_rejected(client, admin_headers, device):
    client.post(f"/api/v1/admin/devices/{device['device_id']}/revoke", headers=admin_headers)
    assert client.get("/api/v1/device/profiles", headers=device["headers"]).status_code == 401


def test_enrollment_codes_and_roles(client, admin_headers):
    r = client.post("/api/v1/admin/enrollment-codes", headers=admin_headers, json={"role_id": "product", "uses": 2})
    code = r.json()["code"]
    r = client.post("/api/v1/devices/enroll", json={"code": code, "user_email": "pm@acme.test"})
    assert r.status_code == 200
    users = client.get("/api/v1/admin/users", headers=admin_headers).json()
    assert next(u for u in users if u["email"] == "pm@acme.test")["role_id"] == "product"
    assert client.delete("/api/v1/admin/roles/product", headers=admin_headers).status_code == 400
    assert client.get("/api/v1/admin/changelog", headers=admin_headers).json()


def test_logprob_parsing():
    from app.corporate import _probs_from_logprobs
    lp = {"content": [{"token": '{"', "logprob": 0}, {"token": "verdict", "logprob": 0}, {"token": '":', "logprob": 0},
                      {"token": ' "', "logprob": 0},
                      {"token": "block", "logprob": -0.1, "top_logprobs": [{"token": "block", "logprob": -0.1},
                                                                           {"token": "ask", "logprob": -2.5},
                                                                           {"token": "allow", "logprob": -5}]}]}
    p = _probs_from_logprobs(lp)
    assert p and p["block"] > 0.8
