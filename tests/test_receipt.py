import json

import pytest
from fastapi.testclient import TestClient

from constellation import server
from constellation.server import create_app

BASE_URL = "http://127.0.0.1:8765"


@pytest.fixture(autouse=True)
def built_app(tmp_path, monkeypatch):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><html><div id=root></div></html>")
    monkeypatch.setattr(server, "STATIC", static)


def item(id_, kind, name=None, **extra):
    return {"id": id_, "kind": kind, "name": name or id_, "description": "d", "source": "s", **extra}


def get(tmp_path, items, **extra):
    path = tmp_path / "scan.json"
    path.write_text(json.dumps({"items": items, "relations": [], "labels": {}, "clusters": [], "warnings": [], **extra}))
    client = TestClient(create_app(path, checklist=tmp_path / "c.md"), base_url=BASE_URL)
    return client.get("/api/lenses").json()["receipt"]


def cost(n):
    return {"always_on": n, "on_use": None}


def test_receipt_sums_known_tokens_only(tmp_path):
    r = get(
        tmp_path,
        [item("s1", "skill"), item("s2", "skill"), item("h", "hook")],
        costs={"s1": cost(100), "s2": cost(None)},
        hook_weights={"h": {"bytes": 9, "tokens": 30}},
    )
    assert r["total_tokens"] == 130
    assert r["unknown"] == 1


def test_receipt_no_known_tokens_is_none(tmp_path):
    r = get(tmp_path, [item("s1", "skill")])
    assert r["total_tokens"] is None
    assert r["unknown"] == 1
    assert get(tmp_path, [])["total_tokens"] is None


def test_receipt_zero_cost_counts_as_known(tmp_path):
    r = get(tmp_path, [item("s1", "skill")], costs={"s1": cost(0)})
    assert (r["total_tokens"], r["unknown"]) == (0, 0)


def test_receipt_bytes_kept_apart(tmp_path):
    r = get(
        tmp_path,
        [item("s1", "skill"), item("h", "hook")],
        costs={"s1": cost(7)},
        hook_weights={"h": {"bytes": 400, "tokens": None}},
        memory_bytes=2048,
    )
    assert r["uncounted_bytes"] == 2448
    assert r["total_tokens"] == 7
    assert r["unknown"] == 0
    assert {g["kind"]: g["bytes"] for g in r["groups"]} == {"hook": 400, "memory": 2048, "skill": 0}
    assert {"id": None, "kind": "memory", "name": "CLAUDE.md", "tokens": None, "bytes": 2048} in r["rows"]


def test_receipt_hook_tokens_leave_no_uncounted_bytes(tmp_path):
    r = get(tmp_path, [item("h", "hook")], hook_weights={"h": {"bytes": 400, "tokens": 90}})
    assert (r["uncounted_bytes"], r["total_tokens"]) == (0, 90)


def test_receipt_skips_disabled_and_plugins(tmp_path):
    r = get(
        tmp_path,
        [item("p", "plugin"), item("s1", "skill", disabled=True), item("s2", "skill"), item("m", "mcp_server", disabled=True)],
        costs={"p": cost(5), "s1": cost(50), "s2": cost(1)},
    )
    assert [x["id"] for x in r["rows"]] == ["s2"]
    assert r["total_tokens"] == 1


def test_receipt_mcp_servers_are_unknown(tmp_path):
    r = get(tmp_path, [item("a", "mcp_server"), item("b", "mcp_server"), item("c", "connector")])
    group = next(g for g in r["groups"] if g["kind"] == "mcp_server")
    assert (group["count"], group["unknown"], group["tokens"]) == (2, 2, None)
    assert r["unknown"] == 3


def test_receipt_hooks_outside_hook_weights_excluded(tmp_path):
    r = get(tmp_path, [item("h1", "hook"), item("h2", "hook")], hook_weights={"h1": {"bytes": None, "tokens": None}})
    assert [x["id"] for x in r["rows"]] == ["h1"]
    assert r["unknown"] == 1


def test_receipt_row_order(tmp_path):
    r = get(
        tmp_path,
        [item("u", "skill", "u"), item("b2", "skill", "b"), item("b1", "skill", "b"), item("big", "skill", "z"), item("hb", "hook", "hb")],
        costs={"u": cost(None), "b2": cost(5), "b1": cost(5), "big": cost(9)},
        hook_weights={"hb": {"bytes": 50, "tokens": None}},
        memory_bytes=700,
    )
    assert [x["id"] for x in r["rows"]] == ["big", "b1", "b2", None, "hb", "u"]


def test_receipt_group_order(tmp_path):
    kinds = ["connector", "mcp_server", "command", "agent", "skill", "hook"]
    r = get(tmp_path, [item(k, k) for k in kinds], hook_weights={"hook": {"bytes": 1, "tokens": None}}, memory_bytes=1)
    assert [g["kind"] for g in r["groups"]] == ["hook", "memory", "skill", "agent", "command", "mcp_server", "connector"]
    assert get(tmp_path, [item("s", "skill")])["groups"][0]["count"] == 1


def test_lenses_route_404_on_bad_scan(tmp_path):
    path = tmp_path / "scan.json"
    path.write_text("not json")
    assert TestClient(create_app(path, checklist=tmp_path / "c.md"), base_url=BASE_URL).get("/api/lenses").status_code == 404


def test_lenses_route_rejects_foreign_host(tmp_path):
    path = tmp_path / "scan.json"
    path.write_text(json.dumps({"items": []}))
    client = TestClient(create_app(path, checklist=tmp_path / "c.md"), base_url="http://evil.com")
    assert client.get("/api/lenses").status_code == 403


def test_lenses_has_no_descriptions(tmp_path):
    path = tmp_path / "scan.json"
    secret = "sk-ant-api03-PLANTED"
    items = [item(f"{k}{i}", k, description=secret) for i, k in enumerate(["skill", "hook", "mcp_server", "agent"])]
    path.write_text(json.dumps({"items": items, "costs": {"skill0": cost(3)}, "hook_weights": {"hook1": {"bytes": 2, "tokens": 1}}}))
    client = TestClient(create_app(path, checklist=tmp_path / "c.md"), base_url=BASE_URL)
    assert secret not in client.get("/api/lenses").text


def test_receipt_row_order_boundaries(tmp_path):
    r = get(
        tmp_path,
        [
            item("one", "skill", "b"),
            item("zero", "skill", "a"),
            item("hb", "hook", "z"),
            item("unk", "agent", "a"),
            item("A", "command", "CLAUDE.md"),
        ],
        costs={"one": cost(1), "zero": cost(0)},
        hook_weights={"hb": {"bytes": 1, "tokens": None}},
        memory_bytes=0,
    )
    assert [x["id"] for x in r["rows"]] == ["one", "zero", "hb", None, "A", "unk"]


def test_receipt_mcp_rows_keep_their_id(tmp_path):
    r = get(tmp_path, [item("m1", "mcp_server")])
    assert r["rows"][0]["id"] == "m1"
