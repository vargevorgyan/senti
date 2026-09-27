"""Server gateway end to end: admin compiles + approves a plain-English policy, creates agent tokens; agents use MCP tools."""
import json
import sqlite3

import pytest

POLICY_TEXT = "Support agents can read tickets and customer names and emails, and add notes. Never card numbers or payments."
MODEL_OUTPUT = {
    "roles": {"support": {
        "description": "Customer support",
        "files": {"read": ["tickets/**", "customers/**"], "write": ["tickets/notes/**"], "deny": ["payments/**", "../etc/**"]},
        "commands": {"allow": ["grep", "wc", "ls", "bash"]},
        "database": {"read_tables": ["tickets", "customers"], "deny_columns": ["customers.card_number"]},
        "notes": "Reports are fine to read if they don't contain payment data."}},
    "examples": [
        {"role": "support", "tool": "read_file", "arg": "tickets/1.md", "expected": "allow", "why": "tickets"},
        {"role": "support", "tool": "read_file", "arg": "payments/cards.csv", "expected": "block", "why": "payments"},
        {"role": "support", "tool": "query_db", "arg": "select card_number from customers", "expected": "block", "why": "cards"},
        {"role": "support", "tool": "query_db", "arg": "delete from tickets", "expected": "block", "why": "read-only"},
    ],
}


@pytest.fixture
def gw(client, admin_headers, tmp_path, monkeypatch):
    from app import config, policy_compiler
    root, db = tmp_path / "srv", tmp_path / "srv.db"
    for rel, text in {"tickets/1.md": "printer broken", "tickets/notes/.keep": "", "customers/anna.json": '{"name":"Anna"}',
                      "payments/cards.csv": "4111111111111111", "reports/q3.md": "revenue up"}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    c = sqlite3.connect(db)
    c.executescript("create table customers(id int, name text, email text, card_number text);"
                    "create table tickets(id int, subject text); insert into customers values (1,'Anna','a@x.com','4111');"
                    "insert into tickets values (1,'Printer');")
    c.commit(), c.close()
    monkeypatch.setattr(config.settings, "gateway_root", str(root))
    monkeypatch.setattr(config.settings, "gateway_db", str(db))

    async def fake_model(cfg, prompt, timeout=120.0):
        assert "tickets/" in prompt and "customers(" in prompt  # the model sees the real server contents
        return json.dumps(MODEL_OUTPUT)
    monkeypatch.setattr(policy_compiler, "call_model", fake_model)
    r = client.post("/api/v1/admin/gateway/policy/compile", headers=admin_headers, json={"text": POLICY_TEXT})
    assert r.status_code == 200, r.text
    assert client.post("/api/v1/admin/gateway/policy/approve", headers=admin_headers).status_code == 200
    r = client.post("/api/v1/admin/gateway/agents", headers=admin_headers,
                    json={"name": "helpdesk-bot", "role": "support", "base_url": "https://srv.acme:8443"})
    assert r.status_code == 201, r.text
    return {"root": root, "db": db, "agent": r.json(), "compiled": client.get("/api/v1/admin/gateway/policy", headers=admin_headers).json()}


def rpc(client, token, method, params=None):
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return client.post("/api/v1/mcp/", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})


def call(client, token, tool, **args) -> str:
    r = rpc(client, token, "tools/call", {"name": tool, "arguments": args})
    assert r.status_code == 200, r.text
    return r.json()["result"]["content"][0]["text"]


def fake_supervisor(monkeypatch, verdict):
    from app import corporate
    seen = []

    async def fake(cfg, task, action, content, instructions, facts, timeout=25, allow_threshold=0.6):
        seen.append({"action": action, "instructions": instructions})
        return {"verdict": verdict, "reason": f"supervisor says {verdict}", "p": {verdict: 1.0}, "model": "m", "ms": 1}
    monkeypatch.setattr(corporate, "judge", fake)
    return seen


# ---------------------------------------------------------------- compile + approve
def test_compile_drops_unsafe_items_and_checks_examples(gw):
    draft = gw["compiled"]["active"]
    role = draft["compiled"]["roles"]["support"]
    assert "bash" not in role["commands"]["allow"] and "../etc/**" not in role["files"]["deny"]
    assert draft["version"] == 1


def test_compile_preview_marks_examples(client, admin_headers, gw):
    r = client.get("/api/v1/admin/gateway/policy", headers=admin_headers).json()["draft"]
    assert any("bash" in w for w in r["warnings"]) and any("../etc" in w for w in r["warnings"])
    assert all(e["ok"] for e in r["examples"]), r["examples"]
    assert gw["db"].exists() and sqlite3.connect(gw["db"]).execute("select count(*) from tickets").fetchone()[0] == 1, \
        "the delete example must not touch the live database"


def test_agent_needs_an_approved_role(client, admin_headers, gw):
    r = client.post("/api/v1/admin/gateway/agents", headers=admin_headers, json={"name": "x", "role": "finance"})
    assert r.status_code == 422


def test_agent_token_shown_once_with_connect_command(client, admin_headers, gw):
    a = gw["agent"]
    assert a["token"].startswith("sag_") and a["token"] in a["claude_code"] and a["url"] == "https://srv.acme:8443/api/v1/mcp/"
    listed = client.get("/api/v1/admin/gateway/agents", headers=admin_headers).json()
    assert "token" not in listed[0]


# ---------------------------------------------------------------- auth
def test_mcp_requires_a_valid_token(client, admin_headers, gw):
    assert rpc(client, None, "tools/list").status_code == 401
    assert rpc(client, "sag_wrong", "tools/list").status_code == 401
    token = gw["agent"]["token"]
    assert {t["name"] for t in rpc(client, token, "tools/list").json()["result"]["tools"]} == \
        {"list_files", "read_file", "write_file", "run_command", "query_db"}
    client.delete(f"/api/v1/admin/gateway/agents/{gw['agent']['id']}", headers=admin_headers)
    assert rpc(client, token, "tools/list").status_code == 401


# ---------------------------------------------------------------- tools under the policy
def test_files(client, gw):
    t = gw["agent"]["token"]
    assert call(client, t, "read_file", path="tickets/1.md") == "printer broken"
    assert call(client, t, "read_file", path="payments/cards.csv").startswith("Blocked by Senti")
    assert call(client, t, "read_file", path="../../etc/passwd").startswith("Blocked by Senti")
    listing = call(client, t, "list_files", path=".")
    assert "tickets/" in listing and "payments" not in listing and "reports" not in listing
    assert call(client, t, "write_file", path="tickets/notes/1.md", content="called back").startswith("Wrote")
    assert (gw["root"] / "tickets/notes/1.md").read_text() == "called back"



def test_write_outside_write_rules_is_decided_by_supervisor(client, gw, monkeypatch):
    fake_supervisor(monkeypatch, "block")
    t = gw["agent"]["token"]
    assert call(client, t, "write_file", path="customers/anna.json", content="{}").startswith("Blocked by Senti")
    assert (gw["root"] / "customers/anna.json").read_text() == '{"name":"Anna"}'


def test_unclear_case_goes_to_the_supervisor(client, gw, monkeypatch):
    t = gw["agent"]["token"]
    seen = fake_supervisor(monkeypatch, "allow")
    assert call(client, t, "read_file", path="reports/q3.md") == "revenue up"
    assert "POLICY" in seen[0]["instructions"] and POLICY_TEXT[:30] in seen[0]["instructions"]
    fake_supervisor(monkeypatch, "ask")  # no human is watching: anything but allow is a block
    assert call(client, t, "read_file", path="reports/q3.md").startswith("Blocked by Senti: supervisor says ask")


def test_supervisor_down_fails_closed(client, gw, monkeypatch):
    from app import corporate

    async def down(*a, **k):
        raise ConnectionError("model offline")
    monkeypatch.setattr(corporate, "judge", down)
    assert call(client, gw["agent"]["token"], "read_file", path="reports/q3.md").startswith("Blocked by Senti")


def test_commands(client, gw):
    t = gw["agent"]["token"]
    assert "printer broken" in call(client, t, "run_command", command="grep -r printer tickets")
    assert call(client, t, "run_command", command="grep -r 4111 .").startswith("Blocked by Senti")
    assert call(client, t, "run_command", command="bash -c id").startswith("Blocked by Senti")


def test_database(client, gw):
    t = gw["agent"]["token"]
    out = json.loads(call(client, t, "query_db", sql="select name, email from customers"))
    assert out["rows"] == [["Anna", "a@x.com"]]
    assert call(client, t, "query_db", sql="select * from customers").startswith("Blocked by Senti")
    assert call(client, t, "query_db", sql="delete from tickets").startswith("Blocked by Senti")


def test_every_call_is_logged(client, admin_headers, gw):
    t = gw["agent"]["token"]
    call(client, t, "read_file", path="tickets/1.md")
    call(client, t, "read_file", path="payments/cards.csv")
    ev = client.get("/api/v1/admin/gateway/events", headers=admin_headers).json()
    assert [(e["target"], e["verdict"]) for e in ev[:2]] == [("payments/cards.csv", "block"), ("tickets/1.md", "allow")]
    assert client.get("/api/v1/admin/gateway/agents", headers=admin_headers).json()[0]["calls"] >= 2


def test_gateway_rate_limit(client, gw, monkeypatch):
    from app import config
    monkeypatch.setattr(config.settings, "gateway_rpm", 2)
    t = gw["agent"]["token"]
    outs = [call(client, t, "read_file", path="tickets/1.md") for _ in range(3)]
    assert outs[:2] == ["printer broken"] * 2 and "too many requests" in outs[2]


# ---------------------------------------------------------------- people's Macs (device tokens) instead of agent tokens
def _set_gateway_role(client, admin_headers, email, role):
    u = next(x for x in client.get("/api/v1/admin/users", headers=admin_headers).json() if x["email"] == email)
    r = client.put(f"/api/v1/admin/users/{u['id']}", headers=admin_headers, json={**u, "gateway_role": role})
    assert r.status_code == 200, r.text
    return u


def test_enrolled_mac_needs_server_access_from_admin(client, admin_headers, gw, device):
    tok = device["device_token"]
    assert rpc(client, tok, "tools/list").status_code == 401, "no server role yet → no access"
    _set_gateway_role(client, admin_headers, "dev@acme.test", "support")
    assert call(client, tok, "read_file", path="tickets/1.md") == "printer broken"
    assert call(client, tok, "read_file", path="payments/cards.csv").startswith("Blocked by Senti")
    ev = client.get("/api/v1/admin/gateway/events", headers=admin_headers).json()
    assert ev[0]["agent"].startswith("dev@acme.test · mac-1") and ev[0]["role"] == "support"


def test_revoked_mac_loses_server_access(client, admin_headers, gw, device):
    _set_gateway_role(client, admin_headers, "dev@acme.test", "support")
    client.post(f"/api/v1/admin/devices/{device['device_id']}/revoke", headers=admin_headers)
    assert rpc(client, device["device_token"], "tools/list").status_code == 401


def test_removing_server_access_takes_effect_immediately(client, admin_headers, gw, device):
    u = _set_gateway_role(client, admin_headers, "dev@acme.test", "support")
    assert rpc(client, device["device_token"], "tools/list").status_code == 200
    client.put(f"/api/v1/admin/users/{u['id']}", headers=admin_headers, json={**u, "gateway_role": ""})
    assert rpc(client, device["device_token"], "tools/list").status_code == 401


# ---------------------------------------------------------------- no AI model yet
def test_compile_without_a_model_explains_what_to_do(client, admin_headers, monkeypatch):
    from app import config
    monkeypatch.setattr(config.settings, "corp_model_enabled", False)
    monkeypatch.setattr(config.settings, "policy_model_url", "")
    r = client.post("/api/v1/admin/gateway/policy/compile", headers=admin_headers, json={"text": POLICY_TEXT})
    assert r.status_code == 503 and "Corporate judge" in r.json()["detail"]


def test_compile_with_an_unreachable_model_says_so(client, admin_headers, monkeypatch):
    from app import config
    monkeypatch.setattr(config.settings, "policy_model_url", "http://127.0.0.1:9/v1")
    r = client.post("/api/v1/admin/gateway/policy/compile", headers=admin_headers, json={"text": POLICY_TEXT})
    assert r.status_code == 503 and "Can't reach the AI model at http://127.0.0.1:9/v1" in r.json()["detail"]


def test_overview_includes_the_server_gateway(client, admin_headers, gw):
    t = gw["agent"]["token"]
    call(client, t, "read_file", path="tickets/1.md")
    call(client, t, "read_file", path="payments/cards.csv")
    g = client.get("/api/v1/admin/overview", headers=admin_headers).json()["gateway"]
    assert g["calls_24h"] == 2 and g["allowed"] == 1 and g["blocked"] == 1
    assert g["by_agent"] == {"helpdesk-bot": 2} and sum(g["timeline"]["hours"]) == 2
    assert g["recent_blocks"][0]["target"] == "payments/cards.csv" and g["recent_blocks"][0]["reason"]
