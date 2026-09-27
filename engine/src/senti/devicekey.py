"""This Mac's device key: every request to the company server is signed with it.

The key lives in the Secure Enclave when the Mac has one (`senti-key`, hook/senti-key.swift): the private key can't be read
or copied, so a stolen device token is useless on any other computer. Macs without a Secure Enclave (or without the helper)
use a software P-256 key in ~/.senti (readable only by this user; agents are blocked from ~/.senti by the rules). The server
sees which kind each Mac has.

Signature (checked by the backend, app.security.verify_device_signature):
    ECDSA-P256-SHA256 over "senti-device-v1\\n{METHOD}\\n{path?query}\\n{ts}\\n{nonce}\\n{sha256(body)}"
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import secrets
import subprocess
import time
from pathlib import Path

import httpx

from .config import senti_home

SE_KEY = "device-key.se"
SOFT_KEY = "device-key.pem"


def _home() -> Path:
    return senti_home()


def helper() -> Path | None:
    """The Secure Enclave helper, compiled on first use if the Swift compiler is there (packaged builds ship it)."""
    from . import installers
    p = installers.key_helper_binary()
    if not p.exists():
        try:
            installers.build_key_helper()
        except (OSError, subprocess.CalledProcessError):
            return None
    return p if p.exists() else None


def create() -> tuple[str, str]:
    """A new device key (replaces any old one). Returns (public key base64 DER, "secure-enclave" | "software")."""
    home = _home()
    home.mkdir(parents=True, exist_ok=True)
    for name in (SE_KEY, SOFT_KEY):
        (home / name).unlink(missing_ok=True)
    h = helper()
    if h is not None:
        r = subprocess.run([str(h), "create", str(home / SE_KEY)], capture_output=True, text=True, timeout=20)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip(), "secure-enclave"
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    fd = os.open(home / SOFT_KEY, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(pem)
    pub = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return base64.b64encode(pub).decode(), "software"


def sign(message: bytes) -> str:
    home = _home()
    if (home / SE_KEY).exists():
        h = helper()
        if h is None:
            raise RuntimeError("the Secure Enclave helper is missing; reinstall Senti")
        r = subprocess.run([str(h), "sign", str(home / SE_KEY)], input=message, capture_output=True, timeout=10)
        if r.returncode != 0:
            raise RuntimeError(f"device key: {r.stderr.decode(errors='replace').strip()[:200]}")
        return r.stdout.decode().strip()
    if (home / SOFT_KEY).exists():
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        key = serialization.load_pem_private_key((home / SOFT_KEY).read_bytes(), password=None)
        return base64.b64encode(key.sign(message, ec.ECDSA(hashes.SHA256()))).decode()
    raise RuntimeError("this Mac has no device key; join the organization again")


def signed_headers(method: str, target: str, body: bytes) -> dict[str, str]:
    ts, nonce = f"{time.time():.3f}", secrets.token_urlsafe(12)
    msg = "\n".join(["senti-device-v1", method.upper(), target, ts, nonce, hashlib.sha256(body or b"").hexdigest()]).encode()
    return {"X-Senti-Ts": ts, "X-Senti-Nonce": nonce, "X-Senti-Signature": sign(msg)}


class DeviceAuth(httpx.Auth):
    """httpx auth for every request to the company server: the device token plus a fresh signature."""
    requires_request_body = True

    def __init__(self, token: str):
        self.token = token

    def _headers(self, request: httpx.Request) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}",
                **signed_headers(request.method, request.url.raw_path.decode("latin-1"), request.content)}

    def auth_flow(self, request: httpx.Request):
        request.headers.update(self._headers(request))
        yield request

    async def async_auth_flow(self, request: httpx.Request):
        await request.aread()
        request.headers.update(await asyncio.to_thread(self._headers, request))  # the helper runs outside the event loop
        yield request
