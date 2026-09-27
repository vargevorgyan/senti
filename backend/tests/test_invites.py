"""Personal invite keys (admin → person → one Mac), shared-code lockdown, and /judge hardening."""
import hashlib
import json
import time


def make_user(client, admin_headers, email="anna@acme.test", role="product"):
    r = client.post("/api/v1/admin/users", headers=admin_headers, json={"email": email, "role_id": role})
    assert r.status_code == 201, r.text
    return r.json()


def make_invite(client, admin_headers, uid, **body):
    body.setdefault("backend", "https://senti.acme.test:8443")
    r = client.post(f"/api/v1/admin/users/{uid}/invites", headers=admin_headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def enroll_key(client, key, hostname="annas-mac"):
    return client.post("/api/v1/devices/enroll", json={"invite": key, "hostname": hostname})


# ---------------------------------------------------------------- invites
def test_invite_enrolls_the_right_person_and_role(client, admin_headers):
    u = make_user(client, admin_headers)
    inv = make_invite(client, admin_headers, u["id"])
    assert inv["key"].startswith("sti_")
    assert inv["link"] == f"https://senti.acme.test:8443/join#s=senti.acme.test:8443&k={inv['key']}"
    assert inv["command"] == f"senti join '{inv['link']}'" and "--key" in inv["setup_command"]
    # no own CA here (publicly trusted certificate): the server serves its own installer
    assert inv["install_command"] == f"curl -fsSL https://senti.acme.test:8443/install.sh | sh -s -- '{inv['link']}'"
    r = enroll_key(client, inv["key"])
    assert r.status_code == 200, r.text
    assert r.json()["user"] == {"email": "anna@acme.test", "role": "product"}
    status = client.get(f"/api/v1/admin/users/{u['id']}/invites", headers=admin_headers).json()
    assert status[0]["status"] == "used" and status[0]["used_hostname"] == "annas-mac"
    assert "key" not in status[0], "the key is shown once, never listed again"


def test_invite_key_works_only_once(client, admin_headers):
    u = make_user(client, admin_headers)
    key = make_invite(client, admin_headers, u["id"])["key"]
    assert enroll_key(client, key).status_code == 200
    r = enroll_key(client, key, hostname="attacker")
    assert r.status_code == 403 and "already used" in r.text


def test_expired_invite_rejected(client, admin_headers):
    from app.db import SessionLocal
    from app.models import Invite
    u = make_user(client, admin_headers)
    key = make_invite(client, admin_headers, u["id"])["key"]
    with SessionLocal() as db:
        inv = db.query(Invite).one()
        inv.expires_at = time.time() - 1
        db.commit()
    assert enroll_key(client, key).status_code == 403


def test_revoked_invite_rejected(client, admin_headers):
    u = make_user(client, admin_headers)
    inv = make_invite(client, admin_headers, u["id"])
    assert client.delete(f"/api/v1/admin/invites/{inv['id']}", headers=admin_headers).status_code == 200
    assert enroll_key(client, inv["key"]).status_code == 403


def test_unknown_key_rejected(client):
    assert enroll_key(client, "sti_" + "x" * 43).status_code == 403


def test_key_is_stored_hashed(client, admin_headers):
    from app.db import SessionLocal
    from app.models import Invite
    u = make_user(client, admin_headers)
    key = make_invite(client, admin_headers, u["id"])["key"]
    with SessionLocal() as db:
        row = db.query(Invite).one()
        assert row.key_hash == hashlib.sha256(key.encode()).hexdigest()
        assert key not in str({c.name: getattr(row, c.name) for c in Invite.__table__.columns})


def test_new_invite_replaces_unused_ones(client, admin_headers):
    u = make_user(client, admin_headers)
    old = make_invite(client, admin_headers, u["id"])["key"]
    new = make_invite(client, admin_headers, u["id"])["key"]
    assert enroll_key(client, old).status_code == 403
    assert enroll_key(client, new).status_code == 200


def test_invite_for_unknown_user_404(client, admin_headers):
    assert client.post("/api/v1/admin/users/9999/invites", headers=admin_headers, json={}).status_code == 404


def test_invites_require_admin(client, admin_headers):
    u = make_user(client, admin_headers)
    # signed in, but a cross-site request can't add the X-Requested-With header (CSRF)
    assert client.post(f"/api/v1/admin/users/{u['id']}/invites", json={}).status_code == 403
    client.cookies.clear()
    assert client.post(f"/api/v1/admin/users/{u['id']}/invites", json={}).status_code == 401


# ---------------------------------------------------------------- shared codes are off by default
def test_shared_code_creation_refused_by_default(client, admin_headers):
    r = client.post("/api/v1/admin/enrollment-codes", headers=admin_headers, json={"role_id": "product", "uses": 5})
    assert r.status_code == 422 and "invite" in r.text.lower()


def test_existing_shared_code_cannot_enroll(client, admin_headers):
    from app.db import SessionLocal
    from app.models import EnrollmentCode
    with SessionLocal() as db:
        db.add(EnrollmentCode(code="SENTI-OLD-SHARED", role_id="engineering", uses_left=10))
        db.commit()
    r = client.post("/api/v1/devices/enroll", json={"code": "SENTI-OLD-SHARED", "user_email": "x@gmail.com"})
    assert r.status_code == 403


# ---------------------------------------------------------------- /judge hardening
def _fake_judge(monkeypatch, seen):
    from app import corporate

    async def fake(cfg, task, action, content, instructions, facts, timeout=25, allow_threshold=0.6):
        seen.append(instructions)
        return {"verdict": "ask", "reason": "r", "p": {"ask": 1.0}, "model": "m", "ms": 1}
    monkeypatch.setattr(corporate, "judge", fake)


def test_judge_refuses_profiles_outside_the_device_bundle(client, admin_headers, device, monkeypatch):
    seen = []
    _fake_judge(monkeypatch, seen)
    bundle = client.get("/api/v1/device/profiles", headers=device["headers"]).json()
    own = {p["id"] for p in json.loads(bundle["payload"])["profiles"]}
    others = [p["id"] for p in client.get("/api/v1/admin/profiles", headers=admin_headers).json() if p["id"] not in own]
    assert others, "seed data should have profiles for other roles"
    r = client.post("/api/v1/judge", headers=device["headers"], json={"profile_id": others[0], "action": {"tool": "Bash"}})
    assert r.status_code == 403
    assert seen == [], "another role's policy must never reach the model"
    ok = client.post("/api/v1/judge", headers=device["headers"], json={"profile_id": sorted(own)[0], "action": {"tool": "Bash"}})
    assert ok.status_code == 200


def test_judge_is_rate_limited_per_device(client, device, monkeypatch):
    from app import config
    _fake_judge(monkeypatch, [])
    monkeypatch.setattr(config.settings, "judge_rpm", 3)
    codes = [client.post("/api/v1/judge", headers=device["headers"], json={"action": {"tool": "Bash"}}).status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and codes[3:] == [429, 429]


def test_approvals_are_rate_limited_per_device(client, device, monkeypatch):
    from app import config
    monkeypatch.setattr(config.settings, "approvals_rpm", 2)
    body = {"agent": "claude", "tool": "Bash", "summary": "x"}
    codes = [client.post("/api/v1/approvals", headers=device["headers"], json=body).status_code for _ in range(4)]
    assert codes[:2] == [200, 200] and 429 in codes[2:]
