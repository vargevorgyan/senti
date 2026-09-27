"""Runs one brokered command: redeems the grant, substitutes secret values, masks them in the output.

Invoked only by commands the engine rewrote:  python -m senti.secret_exec <grant> -- '<command with {{senti:NAME}}>'
"""
from __future__ import annotations

import json
import os
import selectors
import socket
import subprocess
import sys

from .config import senti_home, socket_path
from .secrets import PLACEHOLDER


def redeem(grant: str, command: str) -> dict[str, str] | None:
    body = json.dumps({"grant": grant, "command": command}).encode()
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(15)
    s.connect(socket_path())
    s.sendall(b"POST /v1/secrets/redeem HTTP/1.1\r\nHost: senti\r\nContent-Type: application/json\r\n"
              + f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body)
    buf = b""
    while chunk := s.recv(65536):
        buf += chunk
    head, _, payload = buf.partition(b"\r\n\r\n")
    if not head.startswith(b"HTTP/1.1 200"):
        return None
    return json.loads(payload).get("values")


def partial_tail(buf: bytes, values: list[bytes]) -> int:
    """Length of the longest suffix of buf that is a proper prefix of a secret value (must be held back)."""
    best = 0
    for v in values:
        for k in range(min(len(v) - 1, len(buf)), best, -1):
            if buf.endswith(v[:k]):
                best = k
                break
    return best


def main() -> int:
    args = sys.argv[1:]
    if len(args) != 3 or args[1] != "--":
        print("senti: invalid brokered command", file=sys.stderr)
        return 2
    grant, command = args[0], args[2]
    try:
        values = redeem(grant, command)
    except OSError as e:
        values = None
        print(f"senti: could not reach Senti ({e})", file=sys.stderr)
    if not values:
        print("senti: this secret grant is invalid or expired; the command was not run", file=sys.stderr)
        return 126
    real = PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), command)
    masks = sorted(((v, f"[senti:{k}]") for k, v in values.items() if v), key=lambda x: -len(x[0]))

    def mask(b: bytes) -> bytes:
        for v, label in masks:
            b = b.replace(v.encode(), label.encode())
        return b

    p = subprocess.Popen(["/bin/sh", "-c", real], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=os.environ.copy())
    sel = selectors.DefaultSelector()
    sel.register(p.stdout, selectors.EVENT_READ, sys.stdout.buffer)
    sel.register(p.stderr, selectors.EVENT_READ, sys.stderr.buffer)
    pending = {p.stdout: b"", p.stderr: b""}
    open_streams = 2
    while open_streams:
        for key, _ in sel.select():
            data = os.read(key.fileobj.fileno(), 65536)
            if not data:
                sel.unregister(key.fileobj)
                open_streams -= 1
                if pending[key.fileobj]:
                    key.data.write(mask(pending[key.fileobj]))
                    key.data.flush()
                continue
            buf = pending[key.fileobj] + data
            tail = partial_tail(buf, [v.encode() for v, _ in masks])  # a value may be split across reads
            key.data.write(mask(buf[:len(buf) - tail]))
            key.data.flush()
            pending[key.fileobj] = buf[len(buf) - tail:]
    return p.wait()


if __name__ == "__main__":
    sys.exit(main())
