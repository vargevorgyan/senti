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
    r = client.post("/api/v1/admin/enrollment-codes", headers=admin_headers, json={"role_id": "product", "email": "pm@acme.test"})
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


def test_event_user_cannot_be_spoofed(client, admin_headers, device):
    client.post("/api/v1/events", headers=device["headers"], json={"events": [
        {"id": "sp1", "user": "ceo@acme.test", "verdict": "totally-fine", "agent": "claude", "tool": "Bash"}]})
    e = client.get("/api/v1/admin/events", headers=admin_headers).json()["items"][0]
    assert e["user"] == "dev@acme.test" and e["verdict"] is None


def _session(client) -> str:
    return client.cookies.get("senti_session")


def test_query_token_only_for_stream(client, admin_headers):
    tok = _session(client)
    client.cookies.clear()
    assert client.get(f"/api/v1/admin/users?token={tok}").status_code == 401
    # the session JWT is not accepted as a stream ticket either
    assert client.get(f"/api/v1/admin/stream?token={tok}").status_code == 401


def test_stream_ticket_is_not_a_session(client, admin_headers):
    ticket = client.post("/api/v1/auth/stream-ticket", headers=admin_headers).json()["ticket"]
    client.cookies.clear()
    assert client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {ticket}"}).status_code == 401


def test_password_change_and_logout_all_revoke(client, admin_headers):
    old = _session(client)
    r = client.put("/api/v1/auth/password", headers=admin_headers, json={"current": "senti-admin", "new": "a-longer-pass"})
    assert r.status_code == 200 and "token" not in r.json(), "the session never appears in a response body"
    new = _session(client)
    assert new and new != old
    client.cookies.clear()
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old}"}).status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new}"}).status_code == 200
    client.post("/api/v1/auth/logout-all", headers={"Authorization": f"Bearer {new}"})
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new}"}).status_code == 401


def test_enroll_cannot_switch_role(client, admin_headers, device):
    r = client.post("/api/v1/admin/enrollment-codes", headers=admin_headers, json={"role_id": "automation", "email": "dev@acme.test"})
    assert client.post("/api/v1/devices/enroll", json={"code": r.json()["code"], "user_email": "dev@acme.test"}).status_code == 403


def test_default_password_flag(client, admin_headers):
    assert client.get("/api/v1/admin/overview", headers=admin_headers).json()["default_password"] is True


def test_second_mac_needs_personal_code(client, admin_headers, device):
    r = client.post("/api/v1/devices/enroll", json={"code": "SENTI-DEMO", "user_email": "dev@acme.test"})
    assert r.status_code == 403
    code = client.post("/api/v1/admin/enrollment-codes", headers=admin_headers, json={"role_id": "engineering", "email": "dev@acme.test"}).json()["code"]
    assert client.post("/api/v1/devices/enroll", json={"code": code, "user_email": "someone@acme.test"}).status_code == 403
    assert client.post("/api/v1/devices/enroll", json={"code": code, "user_email": "dev@acme.test"}).status_code == 200


def test_delete_user_with_devices(client, admin_headers, device):
    u = next(x for x in client.get("/api/v1/admin/users", headers=admin_headers).json() if x["email"] == "dev@acme.test")
    client.delete(f"/api/v1/admin/users/{u['id']}", headers=admin_headers)
    assert all(x["email"] != "dev@acme.test" for x in client.get("/api/v1/admin/users", headers=admin_headers).json())
    assert client.get("/api/v1/device/profiles", headers=device["headers"]).status_code == 401


def test_bad_event_does_not_poison_batch(client, admin_headers, device):
    r = client.post("/api/v1/events", headers=device["headers"], json={"events": [
        {"id": "bad1", "ts": "not-a-number", "input": "x"}, {"id": "good1", "verdict": "allow"}]})
    assert r.status_code == 200 and r.json()["stored"] == 2


def test_demo_code_off_by_default(tmp_path, monkeypatch):
    import importlib, sys
    monkeypatch.setenv("SENTI_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SENTI_DEMO_ENROLL_CODE", raising=False)
    for m in [m for m in list(sys.modules) if m == "app" or m.startswith("app.")]:
        del sys.modules[m]
    from fastapi.testclient import TestClient
    main = importlib.import_module("app.main")
    with TestClient(main.app) as c:
        assert c.post("/api/v1/devices/enroll", json={"code": "SENTI-DEMO", "user_email": "x@y.z"}).status_code == 403


def test_signed_judge_and_approval_responses(client, admin_headers, device, monkeypatch):
    from app import corporate
    async def fake(cfg, task, action, content, instructions, facts, timeout=25, allow_threshold=0.6):
        return {"verdict": "allow", "reason": "ok", "p": {"allow": 1.0}, "model": "m", "ms": 1}
    monkeypatch.setattr(corporate, "judge", fake)
    r = client.post("/api/v1/judge", headers=device["headers"], json={"action": {"tool": "Bash"}, "nonce": "n1"}).json()
    body = verify(r["signed"], device["public_key"])
    assert body["verdict"] == "allow" and body["nonce"] == "n1"
    aid = client.post("/api/v1/approvals", headers=device["headers"], json={"agent": "codex", "tool": "Bash", "summary": "x"}).json()["id"]
    client.post(f"/api/v1/admin/approvals/{aid}/decide", headers=admin_headers, json={"decision": "approve"})
    r = client.get(f"/api/v1/approvals/{aid}?nonce=n2", headers=device["headers"]).json()
    body = verify(r["signed"], device["public_key"])
    assert body["status"] == "approved" and body["id"] == aid and body["nonce"] == "n2"
