"""The admin picks what the server gateway exposes: a folder and a SQLite file inside the shared host folder."""
import shutil
import sqlite3

import pytest

from test_gateway_api import call, gw  # noqa: F401  (fixture)


@pytest.fixture
def share(gw, tmp_path, monkeypatch):  # noqa: F811
    """The gw fixture's files and database, moved into a shared folder with a second, unrelated folder."""
    from app import config
    base = tmp_path / "share"
    shutil.copytree(gw["root"], base / "support")
    shutil.copy(gw["db"], base / "support.db")
    (base / "other").mkdir()
    (base / "other" / "secret.txt").write_text("not for agents")
    (base / ".hidden").mkdir()
    monkeypatch.setattr(config.settings, "gateway_share", str(base))
    return {**gw, "base": base}


def put(client, admin_headers, **body):
    return client.put("/api/v1/admin/gateway/sources", headers=admin_headers, json=body)


def test_admin_sees_what_the_shared_folder_contains(client, admin_headers, share):
    s = client.get("/api/v1/admin/gateway/sources", headers=admin_headers).json()
    assert "support" in s["folders"] and "other" in s["folders"] and "." in s["folders"]
    assert ".hidden" not in s["folders"], "hidden folders are not offered"
    assert s["databases"] == ["support.db"] and s["configured"] is False


def test_chosen_folder_and_database_are_what_agents_reach(client, admin_headers, share):
    token = share["agent"]["token"]
    assert put(client, admin_headers, folder="support", database="support.db").status_code == 200
    assert "printer broken" in call(client, token, "read_file", path="tickets/1.md")
    assert "Anna" in call(client, token, "query_db", sql="select name from customers")
    assert "Blocked" in call(client, token, "read_file", path="../other/secret.txt"), "nothing outside the chosen folder"


def test_no_database_means_query_db_is_blocked(client, admin_headers, share):
    put(client, admin_headers, folder="support", database="")
    out = call(client, share["agent"]["token"], "query_db", sql="select name from customers")
    assert "Blocked" in out and "No database" in out


def test_the_database_file_is_never_readable_as_a_file(client, admin_headers, share, monkeypatch):
    from test_gateway_api import fake_supervisor
    fake_supervisor(monkeypatch, "allow")  # even a lenient supervisor can't hand out the raw file
    shutil.copy(share["base"] / "support.db", share["base"] / "support" / "inner.db")
    put(client, admin_headers, folder="support", database="support/inner.db")
    token = share["agent"]["token"]
    assert "Blocked" in call(client, token, "read_file", path="inner.db")
    assert "inner.db" not in call(client, token, "list_files", path=".")


def test_sources_must_be_inside_the_shared_folder(client, admin_headers, share):
    assert put(client, admin_headers, folder="../", database="").status_code == 422
    assert put(client, admin_headers, folder="/etc", database="").status_code == 422
    assert put(client, admin_headers, folder="support", database="../../etc/passwd").status_code == 422
    assert put(client, admin_headers, folder="support", database="support/tickets/1.md").status_code == 422


def test_a_source_that_disappears_fails_closed(client, admin_headers, share):
    put(client, admin_headers, folder="support", database="support.db")
    shutil.rmtree(share["base"] / "support")
    assert "Blocked" in call(client, share["agent"]["token"], "read_file", path="tickets/1.md")


def test_runner_refuses_paths_outside_the_share_even_if_the_backend_asks(share):
    from app import gateway_ops
    for bad in ["../x", "/etc", "~/x", "a/../../x"]:
        with pytest.raises(ValueError):
            gateway_ops.inside_share(bad)
    assert "error" in gateway_ops.handle({"op": "check", "tool": "read_file", "arg": "x", "role": {}, "folder": "../.."})


def test_sources_need_an_admin(client, share):
    client.cookies.clear()  # the gw fixture signed in; drop that session
    assert client.get("/api/v1/admin/gateway/sources").status_code == 401
    assert client.put("/api/v1/admin/gateway/sources", json={"folder": "."}).status_code == 401


def test_changes_are_in_the_change_log(client, admin_headers, share):
    put(client, admin_headers, folder="support", database="support.db")
    log = client.get("/api/v1/admin/changelog", headers=admin_headers).json()
    assert any(c["action"] == "gateway_sources.update" and c["target"] == "support" for c in log)
    assert sqlite3  # keep the import for readers adding database cases
