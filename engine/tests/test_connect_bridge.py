"""`senti connect` (assistant configs) and `senti mcp` (the stdio → HTTPS bridge to the company server)."""
import io
import json

import httpx
import pytest

from senti import connect, mcp_bridge


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SENTI_HOME", str(tmp_path / ".senti"))
    for d in ["Library/Application Support/Claude", ".cursor", ".codex", ".config/opencode"]:
        (tmp_path / d).mkdir(parents=True)
    (tmp_path / ".cursor/mcp.json").write_text(json.dumps({"mcpServers": {"github": {"command": "gh-mcp"}}}))
    (tmp_path / ".codex/config.toml").write_text('model = "gpt-5"\n\n[mcp_servers.docs]\ncommand = "docs-mcp"\n')
    monkeypatch.setattr(connect.shutil, "which", lambda name: None)  # no Claude Code CLI in the test
    return tmp_path


def test_connect_adds_one_secret_free_entry_and_keeps_the_rest(home):
    for name in ["claude-desktop", "cursor", "codex", "opencode"]:
        assert "not installed" not in connect.CONNECT[name]()
    cursor = json.loads((home / ".cursor/mcp.json").read_text())["mcpServers"]
    assert cursor["github"] == {"command": "gh-mcp"} and cursor["company-server"]["args"] == ["-m", "senti.cli", "mcp"]
    toml = (home / ".codex/config.toml").read_text()
    assert 'model = "gpt-5"' in toml and "[mcp_servers.docs]" in toml and "[mcp_servers.company-server]" in toml
    oc = json.loads((home / ".config/opencode/opencode.json").read_text())["mcp"]["company-server"]
    assert oc["type"] == "local" and oc["command"][-3:] == ["-m", "senti.cli", "mcp"]
    everything = "".join(p.read_text() for p in home.rglob("*") if p.is_file() and "senti-backup" not in p.name)
    assert "sdt_" not in everything and "sag_" not in everything, "no token may end up in an assistant's config"


def test_connect_twice_changes_nothing_and_remove_restores(home):
    connect.cursor(), connect.codex()
    before = (home / ".codex/config.toml").read_text()
    assert connect.cursor() == "already connected" and connect.codex() == "already connected"
    assert (home / ".codex/config.toml").read_text() == before
    connect.cursor(remove=True), connect.codex(remove=True)
    assert json.loads((home / ".cursor/mcp.json").read_text())["mcpServers"] == {"github": {"command": "gh-mcp"}}
    assert (home / ".codex/config.toml").read_text() == 'model = "gpt-5"\n\n[mcp_servers.docs]\ncommand = "docs-mcp"\n'


def test_assistants_that_are_missing_are_skipped(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(connect.shutil, "which", lambda name: None)
    assert {n: f() for n, f in connect.CONNECT.items()} == {n: "not installed" for n in connect.CONNECT}


# ---------------------------------------------------------------- bridge
def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_bridge_passes_answers_through():
    c = client_for(lambda r: httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}))
    assert mcp_bridge.forward(c, "https://srv/api/v1/mcp/", '{"jsonrpc":"2.0","id":1,"method":"tools/list"}') == \
        [{"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}]


def test_bridge_is_silent_for_notifications():
    c = client_for(lambda r: httpx.Response(202))
    assert mcp_bridge.forward(c, "https://srv/api/v1/mcp/", '{"jsonrpc":"2.0","method":"notifications/initialized"}') == []


def test_bridge_explains_missing_access():
    c = client_for(lambda r: httpx.Response(401, json={"detail": "x"}))
    out = mcp_bridge.forward(c, "https://srv/api/v1/mcp/", '{"jsonrpc":"2.0","id":7,"method":"tools/list"}')
    assert out[0]["id"] == 7 and "People page" in out[0]["error"]["message"]


def test_bridge_reads_event_streams():
    body = 'event: message\ndata: {"jsonrpc":"2.0","id":2,"result":{}}\n\n'
    c = client_for(lambda r: httpx.Response(200, text=body, headers={"content-type": "text/event-stream"}))
    assert mcp_bridge.forward(c, "https://srv/api/v1/mcp/", '{"jsonrpc":"2.0","id":2,"method":"ping"}') == [{"jsonrpc": "2.0", "id": 2, "result": {}}]


def test_bridge_sends_the_macs_token_and_pinned_certificate(tmp_path, monkeypatch):
    from senti.config import Settings
    monkeypatch.setenv("SENTI_HOME", str(tmp_path))
    s = Settings.load()
    s.backend_url, s.device_token = "https://srv.acme:8443", "sdt_mac"
    s.save()
    seen = {}

    def handler(request):
        seen.update(auth=request.headers["authorization"], url=str(request.url))
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}})
    real = httpx.Client
    monkeypatch.setattr(mcp_bridge.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler), **{
        k: v for k, v in kw.items() if k != "verify"}))
    out = io.StringIO()
    assert mcp_bridge.run(stdin=io.StringIO('{"jsonrpc":"2.0","id":1,"method":"ping"}\n'), stdout=out) == 0
    assert seen == {"auth": "Bearer sdt_mac", "url": "https://srv.acme:8443/api/v1/mcp/"}
    assert json.loads(out.getvalue()) == {"jsonrpc": "2.0", "id": 1, "result": {}}


def test_bridge_refuses_without_enrollment(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTI_HOME", str(tmp_path))
    assert mcp_bridge.run(stdin=io.StringIO(""), stdout=io.StringIO()) == 2


def test_claude_code_is_added_with_add_json(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SENTI_HOME", str(tmp_path / ".senti"))
    calls = []
    monkeypatch.setattr(connect.shutil, "which", lambda name: "/usr/local/bin/claude" if name == "claude" else None)

    class R:
        returncode, stdout, stderr = 0, "", ""
    monkeypatch.setattr(connect.subprocess, "run", lambda argv, **kw: calls.append(argv) or R())
    assert connect.claude() == "connected (user scope)"
    add = calls[-1]
    assert add[:6] == ["/usr/local/bin/claude", "mcp", "add-json", "--scope", "user", "company-server"]
    spec = json.loads(add[6])
    assert spec["type"] == "stdio" and spec["args"] == ["-m", "senti.cli", "mcp"] and spec["env"]["SENTI_HOME"].endswith(".senti")
