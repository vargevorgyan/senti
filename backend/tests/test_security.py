"""Internet-facing hardening: two-factor sign-in, lockout, admin allowlist, cookie sessions + CSRF, signed device requests,
invite preview, the organization's TLS CA, and the isolated gateway runner (fail closed)."""
import asyncio
import base64
import hashlib
import importlib
import json
import sys
import threading
import time

import pytest
from conftest import make_client_class, new_device_key, sign_in, sign_request


def _fresh_app(tmp_path, monkeypatch, **env):
    monkeypatch.setenv("SENTI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SENTI_DEMO_ENROLL_CODE", "SENTI-DEMO")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    for m in [m for m in list(sys.modules) if m == "app" or m.startswith("app.")]:
        del sys.modules[m]
    return importlib.import_module("app.main").app


# ---------------------------------------------------------------- two-factor sign-in
def test_first_sign_in_requires_setting_up_two_factor(client):
    r = client.post("/api/v1/auth/login", json={"email": "admin@senti.local", "password": "senti-admin"})
    body = r.json()
    assert r.status_code == 200 and body["step"] == "setup" and body["qr"].startswith("data:image/svg+xml;base64,")
    assert "senti_session" not in client.cookies, "the password alone never gives a session"
    # the step token is not a session either
    assert client.get("/api/v1/admin/overview", headers={"Authorization": f"Bearer {body['token']}"}).status_code == 401
    assert client.post("/api/v1/auth/two-factor/setup", json={"token": body["token"], "code": "000000"}).status_code == 401


def test_every_later_sign_in_needs_a_fresh_code(client):
    from app.security import TOTP_STEP, totp_code
    sign_in(client)
    client.cookies.clear()
    r = client.post("/api/v1/auth/login", json={"email": "admin@senti.local", "password": "senti-admin"})
    assert r.json()["step"] == "code" and "secret" not in r.json()
    secret, last = client.totp["admin@senti.local"]
    used = totp_code(secret, last)
    assert client.post("/api/v1/auth/login/code", json={"token": r.json()["token"], "code": used}).status_code == 401, \
        "a code that was already used is refused"
    fresh = totp_code(secret, max(int(time.time() // TOTP_STEP), last + 1))
    assert client.post("/api/v1/auth/login/code", json={"token": r.json()["token"], "code": fresh}).status_code == 200
    assert client.get("/api/v1/auth/me").json()["two_factor"] is True


def test_session_cookie_flags(client):
    sign_in(client)
    r = client.post("/api/v1/auth/logout", headers={"X-Requested-With": "senti"})
    assert r.status_code == 200
    # set by the setup step earlier: check the header the browser receives
    client.cookies.clear()
    from app.security import TOTP_STEP, totp_code
    r = client.post("/api/v1/auth/login", json={"email": "admin@senti.local", "password": "senti-admin"})
    secret, last = client.totp["admin@senti.local"]
    r = client.post("/api/v1/auth/login/code", json={"token": r.json()["token"],
                                                    "code": totp_code(secret, max(int(time.time() // TOTP_STEP), last + 1))})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/api/" in cookie


def test_cookie_changes_need_the_csrf_header(client, admin_headers):
    assert client.post("/api/v1/admin/users", json={"email": "x@acme.test", "role_id": "product"}).status_code == 403
    assert client.post("/api/v1/admin/users", headers=admin_headers, json={"email": "x@acme.test", "role_id": "product"}).status_code == 201
    assert client.get("/api/v1/admin/users").status_code == 200  # reading needs no header


# ---------------------------------------------------------------- lockout
def test_repeated_wrong_passwords_lock_the_account(client):
    for _ in range(5):
        assert client.post("/api/v1/auth/login", json={"email": "admin@senti.local", "password": "nope"}).status_code == 401
    r = client.post("/api/v1/auth/login", json={"email": "admin@senti.local", "password": "senti-admin"})
    assert r.status_code == 429 and "Try again" in r.json()["detail"], "locked even with the right password"


def test_wrong_codes_count_towards_the_lock(client):
    sign_in(client)
    client.cookies.clear()
    for _ in range(5):
        tok = client.post("/api/v1/auth/login", json={"email": "admin@senti.local", "password": "senti-admin"}).json()["token"]
        assert client.post("/api/v1/auth/login/code", json={"token": tok, "code": "123456"}).status_code in (401, 429)
    assert client.post("/api/v1/auth/login", json={"email": "admin@senti.local", "password": "senti-admin"}).status_code == 429


def test_unknown_email_is_throttled_per_ip(client):
    for i in range(20):
        client.post("/api/v1/auth/login", json={"email": f"guess{i}@x.y", "password": "nope"})
    assert client.post("/api/v1/auth/login", json={"email": "admin@senti.local", "password": "senti-admin"}).status_code == 429


# ---------------------------------------------------------------- admin allowlist
def test_admin_side_is_closed_to_the_internet_but_macs_are_not(tmp_path, monkeypatch):
    app = _fresh_app(tmp_path, monkeypatch)
    with make_client_class()(app, client=("203.0.113.9", 40000)) as c:
        r = c.post("/api/v1/auth/login", json={"email": "admin@senti.local", "password": "senti-admin"})
        assert r.status_code == 403 and "company network" in r.json()["detail"]
        assert c.get("/api/v1/admin/overview").status_code == 403
        r = c.post("/api/v1/devices/enroll", json={"code": "SENTI-DEMO", "user_email": "remote@acme.test"})
        assert r.status_code == 200, "an employee joins from anywhere"
        assert c.get("/api/v1/device/profiles", headers={"Authorization": f"Bearer {r.json()['device_token']}"}).status_code == 200
        assert c.get("/api/v1/health").status_code == 200


def test_admin_allowlist_can_name_the_office(tmp_path, monkeypatch):
    app = _fresh_app(tmp_path / "a", monkeypatch, SENTI_ADMIN_ALLOW="203.0.113.0/24")
    with make_client_class()(app, client=("203.0.113.9", 40000)) as c:
        assert c.post("/api/v1/auth/login", json={"email": "admin@senti.local", "password": "senti-admin"}).status_code == 200
    app = _fresh_app(tmp_path / "b", monkeypatch, SENTI_ADMIN_ALLOW="203.0.113.0/24")  # one app instance per lifespan
    with make_client_class()(app, client=("198.51.100.1", 40000)) as c:
        assert c.post("/api/v1/auth/login", json={"email": "admin@senti.local", "password": "senti-admin"}).status_code == 403


def test_no_api_docs_exposed(client):
    for p in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(p).status_code == 404


# ---------------------------------------------------------------- signed device requests
def test_unsigned_or_forged_device_requests_are_refused(client, device):
    tok = device["headers"]["Authorization"]
    target = "/api/v1/device/profiles"
    client.device_keys.pop(device["device_token"])  # stop the automatic signing: craft requests by hand
    assert client.get(target, headers={"Authorization": tok}).status_code == 401, "a copied token alone is useless"
    other, _ = new_device_key()
    assert client.get(target, headers={"Authorization": tok, **sign_request(other, "GET", target, b"")}).status_code == 401
    good = sign_request(device["key"], "GET", target, b"")
    assert client.get(target, headers={"Authorization": tok, **good}).status_code == 200
    assert client.get(target, headers={"Authorization": tok, **good}).status_code == 401, "replayed request"
    old = sign_request(device["key"], "GET", target, b"", ts=time.time() - 3600)
    r = client.get(target, headers={"Authorization": tok, **old})
    assert r.status_code == 401 and "clock" in r.json()["detail"]
    # the signature covers the body: changing it after signing fails
    h = sign_request(device["key"], "POST", "/api/v1/device/heartbeat", json.dumps({"status": {}}).encode())
    r = client.post("/api/v1/device/heartbeat", headers={"Authorization": tok, **h, "content-type": "application/json"},
                    content=json.dumps({"status": {"version": "evil"}}))
    assert r.status_code == 401
    # and the path: a signature for one endpoint doesn't work on another
    h = sign_request(device["key"], "GET", "/api/v1/device/profiles", b"")
    assert client.post("/api/v1/device/heartbeat", headers={"Authorization": tok, **h}, json={"status": {}}).status_code == 401


def test_enrollment_requires_a_p256_device_key(client):
    from app.security import load_device_key
    r = client.post("/api/v1/devices/enroll", json={"code": "SENTI-DEMO", "user_email": "a@acme.test", "device_key": ""})
    assert r.status_code == 422
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519
    ed = ed25519.Ed25519PrivateKey.generate().public_key().public_bytes(serialization.Encoding.DER,
                                                                         serialization.PublicFormat.SubjectPublicKeyInfo)
    r = client.post("/api/v1/devices/enroll", json={"code": "SENTI-DEMO", "user_email": "a@acme.test",
                                                    "device_key": base64.b64encode(ed).decode()})
    assert r.status_code == 422 and "P-256" in r.json()["detail"]
    with pytest.raises(ValueError):
        load_device_key("not base64!")


def test_device_without_key_must_join_again(client, device):
    from app.db import SessionLocal
    from app.models import Device
    with SessionLocal() as db:
        db.get(Device, device["device_id"]).public_key = ""
        db.commit()
    r = client.get("/api/v1/device/profiles", headers=device["headers"])
    assert r.status_code == 401 and "join again" in r.json()["detail"]


def test_mac_mcp_requests_must_be_signed(client, admin_headers, device):
    users = client.get("/api/v1/admin/users", headers=admin_headers).json()
    u = next(x for x in users if x["email"] == "dev@acme.test")
    client.put(f"/api/v1/admin/users/{u['id']}", headers=admin_headers,
               json={"email": u["email"], "name": "Dev", "role_id": u["role_id"], "agent_profiles": {}, "gateway_role": "support"})
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}).encode()
    base = {"Authorization": device["headers"]["Authorization"], "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"}
    key = client.device_keys.pop(device["device_token"])
    r = client.post("/api/v1/mcp/", headers=base, content=body)
    assert r.status_code == 401 and "not signed" in r.json()["detail"]
    r = client.post("/api/v1/mcp/", headers={**base, **sign_request(key, "POST", "/api/v1/mcp/", body)}, content=body)
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------- invite preview
def test_invite_preview_shows_the_server_view_without_using_the_key(client, admin_headers):
    u = client.post("/api/v1/admin/users", headers=admin_headers, json={"email": "anna@acme.test", "role_id": "product"}).json()
    key = client.post(f"/api/v1/admin/users/{u['id']}/invites", headers=admin_headers,
                      json={"backend": "https://senti.acme.test:8443"}).json()["key"]
    r = client.post("/api/v1/devices/invite-info", json={"invite": key})
    assert r.status_code == 200 and r.json()["email"] == "anna@acme.test" and r.json()["org_name"]
    assert client.post("/api/v1/devices/enroll", json={"invite": key, "hostname": "m"}).status_code == 200, "still usable"
    assert client.post("/api/v1/devices/invite-info", json={"invite": key}).status_code == 403, "used now"
    assert client.post("/api/v1/devices/invite-info", json={"invite": "sti_wrong"}).status_code == 403


def test_join_attempts_are_limited_per_ip(client):
    codes = [client.post("/api/v1/devices/invite-info", json={"invite": f"sti_guess{i}"}).status_code for i in range(12)]
    assert codes[:10] == [403] * 10 and codes[-1] == 429


def test_invites_need_an_https_address(client, admin_headers):
    u = client.post("/api/v1/admin/users", headers=admin_headers, json={"email": "b@acme.test", "role_id": "product"}).json()
    r = client.post(f"/api/v1/admin/users/{u['id']}/invites", headers=admin_headers, json={"backend": "http://1.2.3.4:8000"})
    assert r.status_code == 422


# ---------------------------------------------------------------- the organization's TLS CA
def _make_ca_and_leaf(tmp_path):
    import datetime

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    now = datetime.datetime.now(datetime.timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Senti CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
          .serial_number(1).not_valid_before(now).not_valid_after(now + datetime.timedelta(days=10))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True).sign(ca_key, hashes.SHA256()))
    leaf_key = ec.generate_private_key(ec.SECP256R1())
    leaf = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "srv")]))
            .issuer_name(ca_name).public_key(leaf_key.public_key()).serial_number(2).not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=5)).sign(ca_key, hashes.SHA256()))
    (tmp_path / "ca.pem").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    (tmp_path / "cert.pem").write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    return hashlib.sha256(ca.public_bytes(serialization.Encoding.DER)).hexdigest()


def test_ca_endpoint_and_invite_fingerprint(client, admin_headers, tmp_path, monkeypatch):
    from app import config
    assert client.get("/api/v1/tls/ca").status_code == 404
    fp = _make_ca_and_leaf(tmp_path)
    monkeypatch.setattr(config.settings, "tls_ca", str(tmp_path / "ca.pem"))
    monkeypatch.setattr(config.settings, "tls_cert", str(tmp_path / "cert.pem"))
    r = client.get("/api/v1/tls/ca")
    assert r.status_code == 200 and "BEGIN CERTIFICATE" in r.text
    u = client.post("/api/v1/admin/users", headers=admin_headers, json={"email": "c@acme.test", "role_id": "product"}).json()
    inv = client.post(f"/api/v1/admin/users/{u['id']}/invites", headers=admin_headers, json={"backend": "https://srv:8443"}).json()
    assert inv["link"].endswith(f"&fp={fp}"), "Macs pin the CA, so the server certificate can be renewed"
    # own CA: the installer comes from a publicly trusted address and checks this server by the fingerprint
    assert inv["install_command"].startswith("curl -fsSL https://raw.githubusercontent.com/")
    assert client.get("/api/v1/installer").json()["url"].startswith("https://raw.githubusercontent.com/")


def test_public_certificate_needs_no_fingerprint(client, admin_headers, tmp_path, monkeypatch):
    from app import config
    _make_ca_and_leaf(tmp_path)  # cert.pem is issued by another CA: stands in for a publicly trusted certificate
    monkeypatch.setattr(config.settings, "tls_cert", str(tmp_path / "cert.pem"))
    u = client.post("/api/v1/admin/users", headers=admin_headers, json={"email": "d@acme.test", "role_id": "product"}).json()
    inv = client.post(f"/api/v1/admin/users/{u['id']}/invites", headers=admin_headers, json={"backend": "https://srv:8443"}).json()
    assert "&fp=" not in inv["link"]


def test_public_tls_behind_a_proxy_skips_the_own_ca(client, admin_headers, tmp_path, monkeypatch):
    # Senti has its own CA, but Macs reach it through a reverse proxy with a public certificate (SENTI_PUBLIC_TLS)
    from app import config
    _make_ca_and_leaf(tmp_path)
    monkeypatch.setattr(config.settings, "tls_ca", str(tmp_path / "ca.pem"))
    monkeypatch.setattr(config.settings, "tls_cert", str(tmp_path / "cert.pem"))
    monkeypatch.setattr(config.settings, "public_url", "https://senti.acme.test")
    monkeypatch.setattr(config.settings, "public_tls", True)
    u = client.post("/api/v1/admin/users", headers=admin_headers, json={"email": "e@acme.test", "role_id": "product"}).json()
    inv = client.post(f"/api/v1/admin/users/{u['id']}/invites", headers=admin_headers, json={"backend": "https://srv:8443"}).json()
    assert inv["link"] == f"https://senti.acme.test/join#s=senti.acme.test&k={inv['key']}"
    assert inv["install_command"] == f"curl -fsSL https://senti.acme.test/install.sh | sh -s -- '{inv['link']}'"
    assert "--fingerprint" not in inv["setup_command"]


# ---------------------------------------------------------------- the gateway runner
def test_gateway_fails_closed_without_the_runner(client, admin_headers, monkeypatch):
    from app import config, gateway_client
    monkeypatch.setattr(config.settings, "gateway_in_process", False)
    monkeypatch.setattr(config.settings, "gateway_runner", "")
    with pytest.raises(gateway_client.RunnerUnavailable):
        asyncio.run(gateway_client.call({"op": "inventory"}))
    monkeypatch.setattr(config.settings, "gateway_runner", "/nonexistent/runner.sock")
    with pytest.raises(gateway_client.RunnerUnavailable):
        asyncio.run(gateway_client.call({"op": "inventory"}))


def test_runner_never_executes_a_blocked_call(tmp_path, monkeypatch):
    from app import config, gateway_ops
    monkeypatch.setattr(config.settings, "gateway_root", str(tmp_path / "srv"))
    role = {"commands": {"allow": ["ls"]}, "files": {"read": ["**"]}}
    for cmd in ("cat /etc/passwd", "python3 -c 'print(1)'", "sh -c id", "cat ../../data/signing-key.pem"):
        out = gateway_ops.handle({"op": "exec", "tool": "run_command", "arg": cmd, "role": role})
        assert out["decision"]["verdict"] == "block" and "output" not in out, cmd
    assert gateway_ops.handle({"op": "exec", "tool": "sh", "arg": "id", "role": role}) == {"error": "bad request"}


def test_gateway_through_a_real_runner_socket(client, admin_headers, tmp_path, monkeypatch):
    """The backend talks to the runner over its Unix socket, as in Docker."""
    import os
    import tempfile

    from app import config, runner
    srv = tmp_path / "srv"
    (srv / "tickets").mkdir(parents=True)
    (srv / "tickets" / "1.md").write_text("printer broken")
    monkeypatch.setattr(config.settings, "gateway_root", str(srv))
    sock = os.path.join(tempfile.mkdtemp(dir="/tmp"), "r.sock")  # short path: Unix sockets have a length limit
    monkeypatch.setattr(runner, "SOCKET", sock)
    loop = asyncio.new_event_loop()
    threading.Thread(target=lambda: loop.run_until_complete(runner.main()), daemon=True).start()
    for _ in range(50):
        if os.path.exists(sock):
            break
        time.sleep(0.05)
    assert oct(os.stat(sock).st_mode & 0o777) == "0o700" or (os.stat(sock).st_mode & 0o077) == 0
    monkeypatch.setattr(config.settings, "gateway_in_process", False)
    monkeypatch.setattr(config.settings, "gateway_runner", sock)
    from app import gateway_client
    assert "tickets/" in asyncio.run(gateway_client.call({"op": "inventory"}))["text"]
    role = {"files": {"read": ["tickets"]}, "commands": {"allow": ["ls"]}}
    out = asyncio.run(gateway_client.call({"op": "exec", "tool": "read_file", "arg": "tickets/1.md", "role": role}))
    assert out["output"] == "printer broken"
    with pytest.raises(gateway_client.RunnerUnavailable):
        asyncio.run(gateway_client.call({"op": "exec", "tool": "rm", "arg": "-rf .", "role": role}))


# ---------------------------------------------------------------- server console and settings
def test_reset_admin_resets_two_factor(client):
    from app import manage
    from app.db import SessionLocal
    from app.models import Admin
    sign_in(client)
    assert manage.main(["reset-admin", "admin@senti.local", "a-brand-new-pass"]) == 0
    with SessionLocal() as db:
        a = db.query(Admin).first()
        assert not a.totp_enabled and not a.totp_secret
    assert client.get("/api/v1/auth/me").status_code == 401, "every session ended"
    r = client.post("/api/v1/auth/login", json={"email": "admin@senti.local", "password": "a-brand-new-pass"})
    assert r.json()["step"] == "setup"


def test_corporate_model_defaults_come_from_the_installer(tmp_path, monkeypatch):
    _fresh_app(tmp_path, monkeypatch, SENTI_CORP_MODEL_API_KEY="sk-test", SENTI_CORP_MODEL_ENABLED="false")
    from app.db import Base, SessionLocal, engine
    from app.routers.device import corp_config
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        cfg = corp_config(db)
    assert cfg["api_key"] == "sk-test" and cfg["enabled"] is False
