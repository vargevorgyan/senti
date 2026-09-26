"""Admin passwords (scrypt), admin JWTs, device tokens (random, stored as sha256)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

import jwt
from fastapi import Depends, Header, HTTPException, Query, Request
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import Admin, Device


from functools import lru_cache


@lru_cache
def jwt_secret() -> str:
    """Use SENTI_SECRET_KEY if set; otherwise a random secret persisted in the data dir (never the weak default)."""
    import os
    if settings.secret_key and settings.secret_key != "change-me-in-production":
        return settings.secret_key
    path = os.path.join(settings.data_dir, "jwt-secret")
    if os.path.exists(path):
        return open(path).read().strip()
    os.makedirs(settings.data_dir, exist_ok=True)
    val = secrets.token_urlsafe(48)
    with open(path, "w") as f:
        f.write(val)
    os.chmod(path, 0o600)
    return val


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(h).decode()


def check_password(pw: str, stored: str) -> bool:
    try:
        _, s, h = stored.split("$")
        calc = hashlib.scrypt(pw.encode(), salt=base64.b64decode(s), n=2**14, r=8, p=1)
        return hmac.compare_digest(calc, base64.b64decode(h))
    except Exception:
        return False


def make_admin_token(admin: Admin) -> str:
    now = int(time.time())
    return jwt.encode({"sub": str(admin.id), "email": admin.email, "iat": now, "exp": now + settings.token_ttl_hours * 3600,
                       "typ": "admin"}, jwt_secret(), algorithm="HS256")


def _decode(token: str) -> dict:
    try:
        return jwt.decode(token, jwt_secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "invalid or expired token")


def current_admin(request: Request, authorization: str = Header(default=""), token: str = Query(default=""),
                  db: Session = Depends(get_db)) -> Admin:
    raw = authorization.removeprefix("Bearer ").strip()
    if not raw and token and request.url.path.endswith("/admin/stream"):
        raw = token  # EventSource cannot set headers; the query token is accepted for the SSE stream only
    if not raw:
        raise HTTPException(401, "not signed in")
    claims = _decode(raw)
    if claims.get("typ") != "admin":
        raise HTTPException(401, "not an admin token")
    admin = db.get(Admin, int(claims["sub"]))
    if admin is None:
        raise HTTPException(401, "admin not found")
    return admin


def new_device_token() -> tuple[str, str]:
    tok = "sdt_" + secrets.token_urlsafe(32)
    return tok, hashlib.sha256(tok.encode()).hexdigest()


def current_device(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> Device:
    raw = authorization.removeprefix("Bearer ").strip()
    if not raw.startswith("sdt_"):
        raise HTTPException(401, "device token required")
    dev = db.query(Device).filter_by(token_hash=hashlib.sha256(raw.encode()).hexdigest()).first()
    if dev is None or dev.revoked:
        raise HTTPException(401, "device unknown or revoked")
    dev.last_seen = time.time()
    db.commit()
    return dev
