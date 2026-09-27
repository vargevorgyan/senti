import base64
import importlib
import json
import secrets
import sys
import time

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec


def new_device_key():
    k = ec.generate_private_key(ec.SECP256R1())
    pub = k.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return k, base64.b64encode(pub).decode()


def sign_request(key, method: str, target: str, body: bytes, ts: float | None = None, nonce: str | None = None) -> dict:
    """The headers a Mac adds to every device request (see app.security.verify_device_signature)."""
    import hashlib
    ts_s, nonce = f"{ts or time.time():.3f}", nonce or secrets.token_urlsafe(12)
    msg = "\n".join(["senti-device-v1", method.upper(), target, ts_s, nonce, hashlib.sha256(body or b"").hexdigest()]).encode()
    sig = key.sign(msg, ec.ECDSA(hashes.SHA256()))
    return {"X-Senti-Ts": ts_s, "X-Senti-Nonce": nonce, "X-Senti-Signature": base64.b64encode(sig).decode()}


def make_client_class():
    from fastapi.testclient import TestClient

    class SentiTestClient(TestClient):
        """Acts like real Macs: enrollment sends a fresh device key, and every request with a device token is signed."""

        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.device_keys: dict[str, object] = {}
            self.totp: dict[str, tuple[str, int]] = {}
            self.event_hooks = {"request": [self._sign], "response": []}

        def request(self, method, url, **kw):
            key = None
            if str(url).endswith("/api/v1/devices/enroll") and isinstance(kw.get("json"), dict) and "device_key" not in kw["json"]:
                key, pub = new_device_key()
                kw["json"] = {**kw["json"], "device_key": pub, "key_type": "software"}
            r = super().request(method, url, **kw)
            if key is not None and r.status_code == 200:
                self.device_keys[r.json()["device_token"]] = key
            return r

        def _sign(self, request):
            auth = request.headers.get("authorization", "")
            key = self.device_keys.get(auth.removeprefix("Bearer ").strip())
            if key is not None and "x-senti-signature" not in request.headers:
                request.headers.update(sign_request(key, request.method, request.url.raw_path.decode(), request.read()))

    return SentiTestClient


def sign_in(client, email="admin@senti.local", password="senti-admin") -> dict:
    """Password + authenticator code, like the admin panel. Sets the session cookie; returns the CSRF header."""
    from app.security import TOTP_STEP, totp_code
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    step1 = r.json()
    if step1["step"] == "setup":
        client.totp[email] = (step1["secret"], 0)
    secret, last = client.totp[email]
    step = max(int(time.time() // TOTP_STEP), last + 1)  # a code can't be reused: take the next one (valid ±1 step)
    path = "/api/v1/auth/two-factor/setup" if step1["step"] == "setup" else "/api/v1/auth/login/code"
    r = client.post(path, json={"token": step1["token"], "code": totp_code(secret, step)})
    assert r.status_code == 200, r.text
    client.totp[email] = (secret, step)
    return {"X-Requested-With": "senti"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SENTI_DEMO_ENROLL_CODE", "SENTI-DEMO")
    monkeypatch.setenv("SENTI_GATEWAY_IN_PROCESS", "true")  # no runner container in unit tests
    for m in [m for m in list(sys.modules) if m == "app" or m.startswith("app.")]:
        del sys.modules[m]
    main = importlib.import_module("app.main")
    # 127.0.0.1: inside the default admin allowlist, like a request from the server itself
    with make_client_class()(main.app, client=("127.0.0.1", 50000)) as c:
        yield c


@pytest.fixture
def admin_headers(client):
    return sign_in(client)


@pytest.fixture
def device(client):
    r = client.post("/api/v1/devices/enroll", json={"code": "SENTI-DEMO", "user_email": "dev@acme.test", "hostname": "mac-1"})
    assert r.status_code == 200, r.text
    d = r.json()
    d["headers"] = {"Authorization": f"Bearer {d['device_token']}"}
    d["key"] = client.device_keys[d["device_token"]]
    return d


__all__ = ["json", "new_device_key", "sign_request", "sign_in"]
