"""Admin passwords (scrypt), two-factor codes (TOTP), admin sessions (JWT in an HttpOnly cookie), sign-in lockout, the admin
IP allowlist, device tokens (random, stored as sha256) and device request signatures (P-256 device keys)."""
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
                       "typ": "admin", "tv": admin.token_version or 0}, jwt_secret(), algorithm="HS256")


def make_stream_ticket(admin: Admin) -> str:
    """Short-lived, single-purpose token for EventSource (which cannot send headers)."""
    now = int(time.time())
    return jwt.encode({"sub": str(admin.id), "iat": now, "exp": now + 60, "typ": "stream", "tv": admin.token_version or 0},
                      jwt_secret(), algorithm="HS256")


def _decode(token: str) -> dict:
    try:
        return jwt.decode(token, jwt_secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "invalid or expired token")


SESSION_COOKIE = "senti_session"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def make_step_token(admin: Admin, typ: str, minutes: int = 5) -> str:
    """Short-lived token between the sign-in steps: "mfa" (password correct, code still needed) or "setup" (password
    correct, two-factor sign-in not set up yet). It never grants access to the admin API."""
    now = int(time.time())
    return jwt.encode({"sub": str(admin.id), "iat": now, "exp": now + minutes * 60, "typ": typ, "tv": admin.token_version or 0},
                      jwt_secret(), algorithm="HS256")


def admin_from_step_token(db: Session, token: str, typ: str) -> Admin:
    claims = _decode(token)
    if claims.get("typ") != typ:
        raise HTTPException(401, "wrong token type")
    admin = db.get(Admin, int(claims["sub"]))
    if admin is None or int(claims.get("tv", -1)) != int(admin.token_version or 0):
        raise HTTPException(401, "sign in again")
    return admin


def set_session_cookie(response, request: Request, token: str) -> None:
    # HttpOnly: page scripts (and so any injected script) can't read it. SameSite=Strict: other sites can't send it.
    response.set_cookie(SESSION_COOKIE, token, max_age=settings.token_ttl_hours * 3600, httponly=True, samesite="strict",
                        secure=request.url.scheme == "https", path="/api/")


def clear_session_cookie(response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/api/")


def current_admin(request: Request, authorization: str = Header(default=""), token: str = Query(default=""),
                  db: Session = Depends(get_db)) -> Admin:
    raw = authorization.removeprefix("Bearer ").strip()
    expected = "admin"
    if not raw and request.cookies.get(SESSION_COOKIE):
        raw = request.cookies[SESSION_COOKIE]
        # a cookie is sent by the browser automatically: changes also need a header other sites can't add (CSRF)
        if request.method not in SAFE_METHODS and request.headers.get("x-requested-with") != "senti":
            raise HTTPException(403, "missing X-Requested-With header")
    if not raw and token and request.url.path.endswith("/admin/stream"):
        raw, expected = token, "stream"  # EventSource cannot set headers: a 60-second stream ticket, never the session JWT
    if not raw:
        raise HTTPException(401, "not signed in")
    claims = _decode(raw)
    if claims.get("typ") != expected:
        raise HTTPException(401, "wrong token type")
    admin = db.get(Admin, int(claims["sub"]))
    if admin is None:
        raise HTTPException(401, "admin not found")
    if int(claims.get("tv", -1)) != int(admin.token_version or 0):
        raise HTTPException(401, "this session was signed out")
    return admin


def new_invite_key() -> tuple[str, str]:
    """One-time personal enrollment key. Prefix `sti_` so secret scanners (including Senti's own) can recognise a leaked one."""
    key = "sti_" + secrets.token_urlsafe(32)
    return key, hash_key(key)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.strip().encode()).hexdigest()


class RateLimiter:
    """Sliding one-minute window per key (device). In-memory: one backend process; resets on restart."""

    def __init__(self) -> None:
        import collections
        import threading
        self._hits: dict[str, collections.deque] = collections.defaultdict(collections.deque)
        self._lock = threading.Lock()

    def allow(self, key: str, per_minute: int) -> bool:
        if per_minute <= 0:
            return True
        now = time.time()
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - 60:
                q.popleft()
            if len(q) >= per_minute:
                return False
            q.append(now)
            return True


limiter = RateLimiter()


def new_device_token() -> tuple[str, str]:
    tok = "sdt_" + secrets.token_urlsafe(32)
    return tok, hashlib.sha256(tok.encode()).hexdigest()


def device_for_token(db: Session, authorization: str) -> Device | None:
    raw = (authorization or "").removeprefix("Bearer ").strip()
    if not raw.startswith("sdt_"):
        return None
    dev = db.query(Device).filter_by(token_hash=hashlib.sha256(raw.encode()).hexdigest()).first()
    return None if dev is None or dev.revoked else dev


async def current_device(request: Request, db: Session = Depends(get_db)) -> Device:
    dev = device_for_token(db, request.headers.get("authorization", ""))
    if dev is None:
        raise HTTPException(401, "device unknown or revoked")
    verify_device_signature(dev, request.method, request_target(request.scope), request.headers, await request.body())
    dev.last_seen = time.time()
    db.commit()
    return dev


# ---------------------------------------------------------------- device request signatures
def load_device_key(b64: str):
    """The Mac's public key: P-256 only (what the Secure Enclave makes). Raises ValueError otherwise."""
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import load_der_public_key
    try:
        key = load_der_public_key(base64.b64decode(b64, validate=True))
    except Exception as e:
        raise ValueError("device key is not a valid public key") from e
    if not isinstance(key, ec.EllipticCurvePublicKey) or key.curve.name != "secp256r1":
        raise ValueError("device key must be a P-256 key")
    return key


def request_target(scope) -> str:
    """Path and query exactly as the client sent them (what the Mac signed)."""
    path = (scope.get("raw_path") or scope.get("path", "").encode()).decode("latin-1")
    qs = (scope.get("query_string") or b"").decode("latin-1")
    return path + ("?" + qs if qs else "")


def signed_message(method: str, target: str, ts: str, nonce: str, body: bytes) -> bytes:
    return "\n".join(["senti-device-v1", method.upper(), target, ts, nonce, hashlib.sha256(body or b"").hexdigest()]).encode()


class NonceCache:
    """Each signed request can be used once: a copied request can't be replayed within the time window."""

    def __init__(self) -> None:
        import threading
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()

    def use(self, key: str, window: float) -> bool:
        now = time.time()
        with self._lock:
            if len(self._seen) > 100_000 or (self._seen and len(self._seen) % 1000 == 0):
                for k in [k for k, t in self._seen.items() if t < now - 2 * window]:
                    del self._seen[k]
            if key in self._seen:
                return False
            self._seen[key] = now
            return True


nonces = NonceCache()


def verify_device_signature(dev: Device, method: str, target: str, headers, body: bytes) -> None:
    """401 unless the request carries a fresh, unused signature by this Mac's device key."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    if not dev.public_key:
        raise HTTPException(401, "this Mac joined before device keys were required; join again with a new invite")
    ts, nonce, sig = headers.get("x-senti-ts", ""), headers.get("x-senti-nonce", ""), headers.get("x-senti-signature", "")
    if not (ts and nonce and sig) or len(nonce) > 64:
        raise HTTPException(401, "device request is not signed")
    try:
        skew = abs(time.time() - float(ts))
    except ValueError:
        raise HTTPException(401, "device request is not signed")
    window = settings.device_sig_window_s
    if skew > window:
        raise HTTPException(401, f"this Mac's clock is off by more than {window // 60} minutes; set the time automatically")
    try:
        load_device_key(dev.public_key).verify(base64.b64decode(sig), signed_message(method, target, ts, nonce, body),
                                               ec.ECDSA(hashes.SHA256()))
    except (InvalidSignature, ValueError):
        raise HTTPException(401, "device signature is invalid")
    if not nonces.use(f"{dev.id}:{nonce}", window):
        raise HTTPException(401, "device request was replayed")


# ---------------------------------------------------------------- two-factor sign-in (TOTP, RFC 6238)
TOTP_STEP = 30


def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp_code(secret: str, step: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    mac = hmac.new(key, step.to_bytes(8, "big"), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    return f"{(int.from_bytes(mac[off:off + 4], 'big') & 0x7FFFFFFF) % 1_000_000:06d}"


def verify_totp(secret: str, code: str, last_step: int, now: float | None = None) -> int | None:
    """The time step the code belongs to (±1 step for clock drift), or None. Steps at or before last_step are refused,
    so an observed code can't be reused."""
    code = "".join(ch for ch in (code or "") if ch.isdigit())
    if not secret or len(code) != 6:
        return None
    cur = int((now or time.time()) // TOTP_STEP)
    for step in (cur - 1, cur, cur + 1):
        if step > last_step and hmac.compare_digest(totp_code(secret, step), code):
            return step
    return None


def otpauth_uri(secret: str, email: str, issuer: str) -> str:
    from urllib.parse import quote
    return f"otpauth://totp/{quote(issuer)}:{quote(email)}?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"


def qr_svg_data_uri(text: str) -> str:
    import io

    import segno
    buf = io.BytesIO()
    segno.make(text, error="m").save(buf, kind="svg", scale=5, border=2, dark="#2B1E18", light="#FFFFFF")
    return "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()


# ---------------------------------------------------------------- sign-in lockout
class LoginGuard:
    """Failed sign-ins per account and per IP in a sliding window; locked keys are refused before the password is checked."""

    def __init__(self) -> None:
        import collections
        import threading
        self._fails: dict[str, collections.deque] = collections.defaultdict(collections.deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> "collections.deque":
        q = self._fails[key]
        while q and q[0] <= now - settings.lockout_minutes * 60:
            q.popleft()
        return q

    def locked_for(self, key: str, limit: int) -> int:
        now = time.time()
        with self._lock:
            q = self._prune(key, now)
            return int(q[0] + settings.lockout_minutes * 60 - now) + 1 if len(q) >= limit else 0

    def fail(self, key: str) -> None:
        with self._lock:
            self._fails[key].append(time.time())

    def reset(self, key: str) -> None:
        with self._lock:
            self._fails.pop(key, None)


login_guard = LoginGuard()


# ---------------------------------------------------------------- client IP and the admin allowlist
def client_ip(scope) -> str:
    """The caller's address. Behind the bundled nginx this is the real client IP: nginx overwrites X-Forwarded-For with it
    and uvicorn trusts that header only because the backend port is never published beyond this host."""
    c = scope.get("client")
    return c[0] if c else ""


def ip_allowed(ip: str, spec: str) -> bool:
    import ipaddress
    spec = (spec or "").strip()
    if spec.lower() in {"any", "*"}:
        return True
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if addr.version == 6 and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if addr in ipaddress.ip_network(part, strict=False):
                return True
        except ValueError:
            continue
    return False
