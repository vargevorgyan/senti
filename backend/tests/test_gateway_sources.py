"""The admin picks what the server gateway exposes: folders and SQLite files inside the shared host folder."""
import json
import shutil
import sqlite3

import pytest

from test_gateway_api import call, fake_supervisor, gw  # noqa: F401  (fixture)


@pytest.fixture
def share(gw, tmp_path, monkeypatch):  # noqa: F811
    """The gw fixture's folders at the top of a shared folder (paths in its policy stay valid), its database, a second
    database with an overlapping table, and folders that are never chosen."""
    from app import config
    base = tmp_path / "share"
    base.mkdir()
    for d in gw["root"].iterdir():
        shutil.copytree(d, base / d.name)
    shutil.copy(gw["db"], base / "support.db")
    c = sqlite3.connect(base / "crm.db")
    c.executescript("create table customers(id int, name text, salary int); insert into customers values (1,'Boss',9000);"
                    "create table leads(id int, company text); insert into leads values (1,'Acme');")
    c.commit(), c.close()
    (base / "other").mkdir()
    (base / "other" / "secret.txt").write_text("not for agents")
    (base / ".hidden").mkdir()
    monkeypatch.setattr(config.settings, "gateway_share", str(base))
    return {**gw, "base": base}


def put(client, admin_headers, **body):
    return client.put("/api/v1/admin/gateway/sources", headers=admin_headers, json=body)


def test_admin_sees_what_the_shared_folder_contains(client, admin_headers, share):
    s = client.get("/api/v1/admin/gateway/sources", headers=admin_headers).json()
    assert {"tickets", "customers", "other", "."} <= set(s["options"]["folders"])
    assert ".hidden" not in s["options"]["folders"], "hidden folders are not offered"
    assert s["options"]["databases"] == ["crm.db", "support.db"] and s["configured"] is False


def test_several_folders_are_reachable_and_nothing_else(client, admin_headers, share):
    t = share["agent"]["token"]
    assert put(client, admin_headers, folders=["tickets", "customers"], databases=["support.db"]).status_code == 200
    assert call(client, t, "read_file", path="tickets/1.md") == "printer broken"
    assert "Anna" in call(client, t, "read_file", path="customers/anna.json")
    assert "Blocked" in call(client, t, "read_file", path="other/secret.txt"), "a folder that wasn't chosen"
    listing = call(client, t, "list_files", path=".")
    assert "tickets/" in listing and "customers/" in listing and "other" not in listing and ".db" not in listing
    assert "Blocked" in call(client, t, "run_command", command="grep -r printer ."), "recursive tools stay inside the choice"
    assert "Blocked" in call(client, t, "run_command", command="grep -r secret other")


def test_one_database_needs_no_name(client, admin_headers, share):
    put(client, admin_headers, folders=["tickets"], databases=["support.db"])
    assert json.loads(call(client, share["agent"]["token"], "query_db", sql="select name from customers"))["rows"] == [["Anna"]]
    out = call(client, share["agent"]["token"], "query_db", sql="select name from customers", database="main")
    assert json.loads(out)["rows"] == [["Anna"]], "SQLite's name for the only database"



def test_several_databases_are_named_and_rules_can_be_per_database(client, admin_headers, share):
    t = share["agent"]["token"]
    put(client, admin_headers, folders=["tickets"], databases=["support.db", "crm.db"])
    out = call(client, t, "query_db", sql="select name from customers")
    assert "Blocked" in out and "crm" in out and "support" in out, "with two databases the agent must name one"
    assert json.loads(call(client, t, "query_db", sql="select name from customers", database="support"))["rows"] == [["Anna"]]
    # the support role reads `customers` in any database (unqualified rule) ...
    assert json.loads(call(client, t, "query_db", sql="select name from customers", database="crm.db"))["rows"] == [["Boss"]]
    # ... but crm's `leads` table isn't in its rules
    assert "Blocked" in call(client, t, "query_db", sql="select * from leads", database="crm")
    assert "Unknown database" in call(client, t, "query_db", sql="select 1", database="payroll")


def test_qualified_rules_only_apply_to_their_database(share):
    from app.gateway_ops import Sources, decide
    from app.gateway_policy import RolePolicy
    role = RolePolicy.model_validate({"database": {"read_tables": ["support.customers"], "deny_columns": ["crm.customers.salary"]}})
    src = Sources(share["base"], ["tickets"], {"support": str(share["base"] / "support.db"), "crm": str(share["base"] / "crm.db")})
    assert decide(role, "query_db", "select name from customers", src, "support")[0].verdict == "allow"
    assert decide(role, "query_db", "select name from customers", src, "crm")[0].verdict == "block"


def test_no_database_means_query_db_is_blocked(client, admin_headers, share):
    put(client, admin_headers, folders=["tickets"], databases=[])
    out = call(client, share["agent"]["token"], "query_db", sql="select name from customers")
    assert "Blocked" in out and "No database" in out


def test_database_files_are_never_readable_as_files(client, admin_headers, share, monkeypatch):
    fake_supervisor(monkeypatch, "allow")  # even a lenient supervisor can't hand out the raw file
    shutil.copy(share["base"] / "support.db", share["base"] / "tickets" / "inner.db")
    put(client, admin_headers, folders=["tickets"], databases=["tickets/inner.db"])
    t = share["agent"]["token"]
    assert "Blocked" in call(client, t, "read_file", path="tickets/inner.db")
    assert "inner.db" not in call(client, t, "list_files", path="tickets")


def test_sources_must_be_inside_the_shared_folder(client, admin_headers, share):
    assert put(client, admin_headers, folders=["../"], databases=[]).status_code == 422
    assert put(client, admin_headers, folders=["/etc"], databases=[]).status_code == 422
    assert put(client, admin_headers, folders=["tickets"], databases=["../../etc/passwd"]).status_code == 422
    assert put(client, admin_headers, folders=["tickets"], databases=["tickets/1.md"]).status_code == 422
    assert put(client, admin_headers, folders=[], databases=[]).status_code == 422


def test_a_source_that_disappears_is_dropped(client, admin_headers, share):
    put(client, admin_headers, folders=["tickets", "customers"], databases=["support.db"])
    shutil.rmtree(share["base"] / "tickets")
    t = share["agent"]["token"]
    assert "Blocked" in call(client, t, "read_file", path="tickets/1.md")
    assert "Anna" in call(client, t, "read_file", path="customers/anna.json"), "the other choice keeps working"
    shutil.rmtree(share["base"] / "customers")
    (share["base"] / "support.db").unlink()
    assert "Blocked" in call(client, t, "list_files", path="."), "nothing left: fails closed"


def test_runner_refuses_paths_outside_the_share_even_if_the_backend_asks(share):
    from app import gateway_ops
    for bad in ["../x", "/etc", "~/x", "a/../../x"]:
        with pytest.raises(ValueError):
            gateway_ops.inside_share(bad)
    assert "error" in gateway_ops.handle({"op": "check", "tool": "read_file", "arg": "x", "role": {}, "folders": ["../.."]})


def test_older_single_choice_is_still_understood(client, admin_headers, share):
    from app.db import SessionLocal
    from app.routers.gateway import _set_kv
    with SessionLocal() as db:
        _set_kv(db, "gateway_sources", {"folder": "tickets", "database": "support.db"})
    s = client.get("/api/v1/admin/gateway/sources", headers=admin_headers).json()
    assert s["folders"] == ["tickets"] and s["databases"] == ["support.db"]
    assert call(client, share["agent"]["token"], "read_file", path="tickets/1.md") == "printer broken"


def test_sources_need_an_admin(client, share):
    client.cookies.clear()  # the gw fixture signed in; drop that session
    assert client.get("/api/v1/admin/gateway/sources").status_code == 401
    assert client.put("/api/v1/admin/gateway/sources", json={"folders": ["."]}).status_code == 401


def test_changes_are_in_the_change_log(client, admin_headers, share):
    put(client, admin_headers, folders=["tickets", "customers"], databases=["support.db"])
    log = client.get("/api/v1/admin/changelog", headers=admin_headers).json()
    assert any(c["action"] == "gateway_sources.update" and c["target"] == "customers, tickets" for c in log)
