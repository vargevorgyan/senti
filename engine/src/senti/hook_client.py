"""Pure-Python fallback hook client (used only if swiftc is unavailable). Same protocol and fail-closed behaviour."""
import json
import os
import socket
import sys


def main() -> None:
    agent = sys.argv[1] if len(sys.argv) > 1 else "claude"
    event = sys.argv[2] if len(sys.argv) > 2 else "pre"
    home = os.environ.get("SENTI_HOME", os.path.expanduser("~/.senti"))
    path = os.environ.get("SENTI_SOCKET", os.path.join(home, "senti.sock"))
    if len(path.encode()) > 100:
        path = f"/tmp/senti-{os.getuid()}.sock"
    data = sys.stdin.buffer.read()
    try:
        token = open(os.path.join(home, "hook.token")).read().strip()
    except OSError:
        token = ""

    def fail(why: str):
        if event != "pre":
            fallback = {"cursor": {"continue": True} if event == "prompt" else {}, "cline": {"cancel": False}, "hermes": {}, "antigravity": {}}
            if agent in fallback:
                print(json.dumps(fallback[agent]))
            sys.exit(0)
        reason = f"Senti: I couldn't check this action ({why}), so I'm not letting it run without you."
        code = 0
        if agent in {"opencode", "openclaw", "generic"}:
            out = {"verdict": "block", "reason": reason}
        elif agent == "cursor":
            out, code = {"permission": "deny", "user_message": reason, "agent_message": reason}, 2
        elif agent == "cline":
            out = {"cancel": True, "errorMessage": reason}
        elif agent == "hermes":
            out, code = {"decision": "block", "reason": reason}, 2
        elif agent == "antigravity":
            out = {"decision": "deny", "reason": reason}
        else:
            perm = "deny" if agent in {"codex", "zcode"} else "ask"
            out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": perm, "permissionDecisionReason": reason}}
            code = 2 if agent == "zcode" else 0
        print(json.dumps(out))
        sys.exit(code)

    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(int(os.environ.get("SENTI_HOOK_TIMEOUT", "290")))
        s.connect(path)
        s.sendall(f"POST /v1/hook/{agent} HTTP/1.1\r\nHost: senti\r\nContent-Type: application/json\r\n"
                  f"X-Senti-Token: {token}\r\nContent-Length: {len(data)}\r\nConnection: close\r\n\r\n".encode() + data)
        buf = b""
        while chunk := s.recv(65536):
            buf += chunk
    except Exception as e:
        fail(type(e).__name__)
    head, _, body = buf.partition(b"\r\n\r\n")
    if not head.startswith((b"HTTP/1.1 200", b"HTTP/1.0 200")):
        fail("engine error")
    if not body.strip():
        if event == "pre" and agent != "codex":
            fail("empty reply")  # every agent but Codex needs an explicit answer
        sys.exit(0)
    sys.stdout.write(body.decode(errors="replace") + "\n")


if __name__ == "__main__":
    main()
