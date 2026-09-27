"""`senti mcp`: a local MCP server (stdio) that forwards to the organization's server gateway.

Why a bridge: AI assistants (Claude Code, Claude Desktop, Cursor, Codex, OpenCode) refuse the organization's self-signed
certificate, and a token pasted into their config files is easy to leak. The bridge uses what the Mac already has from
enrollment — the pinned certificate, the device token and the device key (every request is signed, so the token alone is
useless elsewhere) — so the assistant's config holds no secret at all:
    {"command": "<python>", "args": ["-m", "senti.cli", "mcp"]}
Bots without an enrolled Mac can use it too: senti mcp --backend URL --fingerprint FP --token sag_…
"""
from __future__ import annotations

import hashlib
import json
import ssl
import sys
from urllib.parse import urlparse

import httpx

from .config import Settings, tls_verify

NO_ACCESS = ("Senti: this Mac has no access to the company server. Ask your administrator to give you a server role "
             "(People page), or check that this Mac is still enrolled.")


def pinned_context(backend_url: str, fingerprint: str) -> ssl.SSLContext:
    """Trust the server's own CA with this SHA-256 fingerprint (or, for older servers, exactly its certificate).
    Nothing is written to disk."""
    from .sync import trusted_ca_pem
    ca = trusted_ca_pem(backend_url, fingerprint)
    if ca is not None:
        return ssl.create_default_context(cadata=ca)
    u = urlparse(backend_url)
    pem = ssl.get_server_certificate((u.hostname, u.port or 443), timeout=10)
    got = hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()
    want = fingerprint.lower().replace(":", "").replace("sha256", "").strip("= ")
    if got != want:
        raise RuntimeError(f"certificate fingerprint mismatch: server has {got}, expected {want}")
    ctx = ssl.create_default_context(cadata=pem)
    ctx.check_hostname = False  # the pinned certificate itself is the identity
    ctx.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
    return ctx


def _error(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def forward(client: httpx.Client, url: str, line: str) -> list[dict]:
    """One JSON-RPC message from the assistant → zero or more messages back."""
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        return [_error(None, -32700, "invalid JSON")]
    msg_id = msg.get("id") if isinstance(msg, dict) else None
    try:
        r = client.post(url, content=line)
    except httpx.HTTPError as e:
        return [] if msg_id is None else [_error(msg_id, -32000, f"Senti: can't reach the company server ({type(e).__name__})")]
    except RuntimeError as e:  # no usable device key: never send the token unsigned
        return [] if msg_id is None else [_error(msg_id, -32001, f"Senti: {e}")]
    if r.status_code in (401, 403):
        return [] if msg_id is None else [_error(msg_id, -32001, NO_ACCESS)]
    if r.status_code == 202 or not r.content:
        return []  # notifications get no answer
    if r.status_code >= 400:
        return [] if msg_id is None else [_error(msg_id, -32000, f"Senti: server error {r.status_code}")]
    if "text/event-stream" in r.headers.get("content-type", ""):
        out = []
        for ln in r.text.splitlines():
            if ln.startswith("data:") and ln[5:].strip():
                out.append(json.loads(ln[5:].strip()))
        return out
    body = r.json()
    return body if isinstance(body, list) else [body]


def run(backend: str = "", token: str = "", fingerprint: str = "", stdin=None, stdout=None) -> int:
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    s = Settings.load()
    base = (backend or s.backend_url).rstrip("/")
    tok = token or s.device_token
    if not base or not tok:
        print("senti mcp: this Mac hasn't joined an organization (senti enroll …), and no --backend/--token given",
              file=sys.stderr)
        return 2
    verify = pinned_context(base, fingerprint) if fingerprint else (tls_verify(s) if not backend else True)
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if token:
        headers["Authorization"] = f"Bearer {tok}"  # a bot's agent token (no Mac, no device key)
        auth = None
    else:
        from .devicekey import DeviceAuth
        auth = DeviceAuth(tok)  # this Mac: token + device-key signature on every message
    url = base + "/api/v1/mcp/"
    with httpx.Client(verify=verify, headers=headers, timeout=120, auth=auth) as client:
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            for out in forward(client, url, line):
                stdout.write(json.dumps(out, separators=(",", ":")) + "\n")
                stdout.flush()
    return 0
