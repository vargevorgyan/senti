"""The org's Ed25519 profile-signing key. Devices pin the public key at enrollment and reject tampered bundles."""
from __future__ import annotations

import base64
import json
import os
from functools import lru_cache

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat, load_pem_private_key

from .config import settings


@lru_cache
def private_key() -> Ed25519PrivateKey:
    path = os.path.join(settings.data_dir, "signing-key.pem")
    if os.path.exists(path):
        return load_pem_private_key(open(path, "rb").read(), password=None)  # type: ignore[return-value]
    os.makedirs(settings.data_dir, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    with open(path, "wb") as f:
        f.write(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
    os.chmod(path, 0o600)
    return key


def public_key_b64() -> str:
    return base64.b64encode(private_key().public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()


def sign(payload: dict) -> dict:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return {"payload": body, "signature": base64.b64encode(private_key().sign(body.encode())).decode(), "alg": "Ed25519"}
