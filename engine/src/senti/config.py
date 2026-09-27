"""Paths and settings for the local Senti engine.

Everything lives under ``SENTI_HOME`` (default ``~/.senti``). Agents must never be allowed to
write there; the rules layer treats it as a guard path (self-protection).
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

HOME = Path.home()


def senti_home() -> Path:
    return Path(os.environ.get("SENTI_HOME", HOME / ".senti")).expanduser()


def socket_path() -> str:
    # Unix socket paths are limited to 104 bytes on macOS.
    p = os.environ.get("SENTI_SOCKET") or str(senti_home() / "senti.sock")
    if len(p.encode()) > 100:
        p = f"/tmp/senti-{os.getuid()}.sock"
    return p


@dataclass
class Settings:
    """Persisted engine settings (``~/.senti/config.json``)."""

    # Org backend (optional). Empty backend_url = personal mode with the built-in profile.
    backend_url: str = ""
    device_id: str = ""
    device_token: str = ""
    backend_public_key: str = ""  # base64 Ed25519 public key pinned at enrollment
    backend_cert: str = ""        # path of the TLS trust anchor pinned at enrollment (self-signed deployments)
    backend_cert_kind: str = ""   # "ca": the organization's own CA (normal chain + hostname checks); "leaf": one certificate
    device_key_type: str = ""     # "secure-enclave" or "software" (devicekey.py)
    agent_identity: str = "enforce"
    # local model gateway for DIY agents (OpenAI-compatible proxy, loopback only)
    gateway_enabled: bool = True
    gateway_port: int = 11435
    gateway_upstream: str = "http://localhost:11434/v1"
    gateway_cwd: str = ""  # enforce | record: verify the calling process really is the claimed agent
    org_name: str = ""
    user_email: str = ""
    # Local judge
    local_model: str = "mlx-community/Qwen3-4B-Instruct-2507-4bit"
    local_judge: bool = True
    # Company Macs use the organization's cloud AI filter; no model is loaded on the Mac unless this is turned on
    local_judge_on_company_macs: bool = False
    allow_threshold: float = 0.6
    unload_after_idle_s: int = 900
    # Behaviour
    notifications: bool = True
    undo_snapshots: bool = True
    approval_timeout_s: int = 240
    judge_timeout_s: float = 20.0
    extra: dict = field(default_factory=dict)

    @classmethod
    def load(cls) -> "Settings":
        p = senti_home() / "config.json"
        if p.exists():
            data = json.loads(p.read_text())
            known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
            return cls(**known)
        return cls()

    def save(self) -> None:
        home = senti_home()
        home.mkdir(parents=True, exist_ok=True)
        os.chmod(home, 0o700)
        p = home / "config.json"
        p.write_text(json.dumps(asdict(self), indent=2))
        os.chmod(p, 0o600)

    @property
    def enrolled(self) -> bool:
        return bool(self.backend_url and self.device_token)


def ensure_dirs() -> Path:
    home = senti_home()
    for sub in ("", "audit", "snapshots", "sandbox", "bin"):
        (home / sub).mkdir(parents=True, exist_ok=True)
    os.chmod(home, 0o700)
    return home


def hook_token(create: bool = False) -> str:
    """Per-install secret the hook presents on the socket, so random same-user processes can't drive the engine."""
    import secrets
    p = senti_home() / "hook.token"
    if p.exists() and p.read_text().strip():
        return p.read_text().strip()
    if not create:
        return ""
    p.parent.mkdir(parents=True, exist_ok=True)
    tok = secrets.token_urlsafe(32)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(tok)
    return tok


def tls_verify(settings: "Settings"):
    """httpx `verify=` value. Organization CA pinned at join: only certificates it issued, for the right host name, are
    trusted (the server certificate can be renewed without re-joining). Older joins pinned one certificate. Otherwise:
    normal public CA verification."""
    import ssl
    if settings.backend_cert and os.path.exists(settings.backend_cert):
        ctx = ssl.create_default_context(cafile=settings.backend_cert)
        if settings.backend_cert_kind != "ca":
            ctx.check_hostname = False  # the pinned certificate itself is the identity
            ctx.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
        return ctx
    return True
