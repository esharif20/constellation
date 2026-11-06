"""compute(): the saved scan, the habit ledger and the pins become Assessments; pins file; /api/assess, /api/pin and `assess`."""

import json
import os
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from constellation import assessment, habits, pins, server
from constellation.cli import main
from constellation.snapshot import snapshot
from constellation.usage import mac

SALT = "cd" * 32
TODAY = "2026-11-05"
BASE = "http://127.0.0.1:8765"
LONG = "Drafts and sends the status update email to the whole team every Friday afternoon."
HASH = "9f3e1c"  # a project hash in the ledger; it must never reach an API reply


def scan(**extra):
    items = [
        {"id": "s:a", "kind": "skill", "name": "alpha", "description": LONG, "source": ""},
        {"id": "s:b", "kind": "skill", "name": "beta", "description": LONG + " Beta.", "source": ""},
        {"id": "m:user", "kind": "mcp_server", "name": "search", "description": "stdio server, shape: search", "source": ""},
        {"id": "m:local", "kind": "mcp_server", "name": "search", "description": "stdio server, shape: search", "source": ""},
        {"id": "h:1", "kind": "hook", "name": "Stop:*", "description": "Hook", "source": ""},
    ]
    items[2]["id"], items[3]["id"] = "claude-code:mcp_server:user/search", "claude-code:mcp_server:local/1/search"
    return {
        "items": items,
        "costs": {"s:a": {"always_on": 400, "on_use": None}, "s:b": {"always_on": 300, "on_use": None}},
        "conflicts_unused": [],
        "hook_weights": {"h:1": {"bytes": 1200, "tokens": None}},
        "setup": "setup1",
        **extra,
    }


def ledger_file(path, days=60, used=("s:a",)):
    d = date.fromisoformat(TODAY)
    day_rows = {(d - timedelta(n)).isoformat(): {"sessions": 2, "projects": {HASH: 2}} for n in range(days)}
    items = {}
    for id_ in ("s:a", "s:b"):
        record_days = {k: {"n": 2, "s": 1, "p": {HASH: 1, "07aa42": 1}} for k in day_rows} if id_ in used else {}
        items[mac(SALT, id_, 12)] = {"first_seen": min(day_rows), "days": record_days}
    habits.save(path, {"setup1": {"salt": SALT, "days": day_rows, "items": items, "co": {}}})


def test_the_ledger_backs_the_verdicts_and_the_unused_item_could_go(tmp_path):
    ledger_file(tmp_path / "habits.json")
    found = assessment.compute(scan(), tmp_path / "habits.json", tmp_path / "pins.json", TODAY)
    assert found.ledger is True and found.evidence.active_days == 60 and found.evidence.sessions == 120
    assert found.assessments["s:a"].tier == "keep"
    assert found.assessments["s:b"].tier == "could_go" and found.assessments["s:b"].saves == 300
    assert found.evidence.items["s:a"].count == 120


def test_without_a_ledger_the_scans_own_usage_is_used(tmp_path):
    data = scan(
        usage={"s:a": {"count": 5, "last_used": "2026-11-01"}, "s:b": {"count": 0, "last_used": None}},
        usage_window={"files": 60, "first": "2026-09-01", "last": "2026-11-01", "skipped": 0},
    )
    found = assessment.compute(data, tmp_path / "none.json", tmp_path / "pins.json", TODAY)
    assert found.ledger is False
    assert [found.assessments[i].tier for i in ("s:a", "s:b")] == ["keep", "could_go"]
    assert assessment.compute(scan(), tmp_path / "none.json", tmp_path / "p.json", TODAY).assessments["s:a"].tier == "too_early"


def test_a_pin_keeps_an_item(tmp_path):
    ledger_file(tmp_path / "habits.json")
    pins.add(tmp_path / "pins.json", "s:b", TODAY)
    found = assessment.compute(scan(), tmp_path / "habits.json", tmp_path / "pins.json", TODAY)
    assert found.assessments["s:b"].tier == "keep" and found.assessments["s:b"].reasons[0].code == "pinned"


def test_only_the_shadowed_mcp_copy_is_redundant_and_same_names_do_not_collide(tmp_path):
    data = scan(conflicts=[{"kind": "mcp_name", "key": "search", "item_ids": sorted(["m:user", "m:local"]), "reason": "r"}])
    data["conflicts"][0]["item_ids"] = ["claude-code:mcp_server:local/1/search", "claude-code:mcp_server:user/search"]
    found = assessment.compute(data, tmp_path / "none.json", tmp_path / "p.json", TODAY).assessments
    assert found["claude-code:mcp_server:user/search"].tier == "redundant"
    assert found["claude-code:mcp_server:local/1/search"].tier != "redundant"
    assert found["claude-code:mcp_server:user/search"].reasons[0].text.startswith("Never loaded")
    keys = assessment._keys(data["items"])
    assert keys["claude-code:mcp_server:user/search"] == "search (user)" and keys["s:a"] == "alpha"
    twins = [{"id": "x", "kind": "skill", "name": "n"}, {"id": "y", "kind": "skill", "name": "n"}]
    assert sorted(assessment._keys(twins).values()) == ["n (skill) [x]", "n (skill) [y]"]


def test_overlaps_plugins_and_hooks_are_adapted(tmp_path):
    data = scan(
        overlaps=[
            {"a_id": "s:a", "b_id": "s:b", "verdict": "duplicate", "reason": "r"},
            {"a_id": "s:a", "b_id": "h:1", "verdict": "distinct", "reason": ""},
        ],
    )
    data["items"].append({"id": "p:1", "kind": "plugin", "name": "pack", "description": "Plugin", "source": ""})
    data["relations"] = [{"source": "p:1", "target": "s:b", "kind": "contains"}, {"source": "s:a", "target": "h:1", "kind": "contains"}]
    view = assessment.adapt(data, assessment._keys(data["items"]))
    assert view["overlaps"] == [{"a": "alpha", "b": "beta", "verdict": "duplicate"}]
    assert view["plugin_children"] == {"pack": 1} and [i for i in view["items"] if i.get("plugin")][0]["name"] == "beta"
    assert view["hook_bytes"] == {"Stop:*": 1200}
    assert assessment.adapt({**data, "hook_weights": {"h:1": "junk"}}, assessment._keys(data["items"]))["hook_bytes"] == {}


def test_no_project_hash_or_day_leaves_in_a_reply(tmp_path, monkeypatch):
    ledger_file(tmp_path / "habits.json")
    path = tmp_path / "scan.json"
    path.write_text(json.dumps(scan()))
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html></html>")
    monkeypatch.setattr(server, "STATIC", static)
    client = TestClient(
        server.create_app(path, checklist=tmp_path / "c.md", habits=tmp_path / "habits.json", pins=tmp_path / "pins.json"), base_url=BASE
    )
    for route in ("/api/assess", "/api/brief"):
        text = client.get(route).text
        assert HASH not in text and "2026-1" not in text, route
    assert client.get("/api/assess").json()["evidence"] == {"sessions": 120, "active_days": 60, "span_days": 60, "ledger": True}


def test_pin_endpoint_validates_and_writes_privately(tmp_path, monkeypatch):
    path = tmp_path / "scan.json"
    path.write_text(json.dumps(scan()))
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html></html>")
    monkeypatch.setattr(server, "STATIC", static)
    pin_path = tmp_path / "private" / "pins.json"
    client = TestClient(server.create_app(path, checklist=tmp_path / "c.md", pins=pin_path), base_url=BASE)
    assert client.post("/api/pin", json={"id": "nope"}).status_code == 404
    assert client.post("/api/pin", json={"id": "s:a", "extra": 1}).status_code == 422
    assert client.post("/api/pin", json={"id": ""}).status_code == 422
    assert client.post("/api/pin", content='{"id":"s:a"}', headers={"content-type": "text/plain"}).status_code == 415
    assert client.post("/api/pin", json={"id": "s:a"}, headers={"host": "evil.example"}).status_code == 403
    assert client.post("/api/pin", json={"id": "s:a"}, headers={"origin": "http://evil.example"}).status_code == 403
    assert not pin_path.exists()
    assert client.post("/api/pin", json={"id": "s:a"}).json() == {"pinned": True, "added": True}
    assert client.post("/api/pin", json={"id": "s:a"}).json()["added"] is False
    assert pin_path.stat().st_mode & 0o777 == 0o600 and pin_path.parent.stat().st_mode & 0o777 == 0o700
    assert list(pins.load(pin_path)) == ["s:a"]
    assert client.get("/api/assess").json()["items"]["s:a"]["tier"] == "keep"
    with pytest.raises(ValueError, match="Pins file"):
        server.create_app(path, checklist=tmp_path / "c.md", pins=path)


def test_pins_file_reading_is_defensive(tmp_path):
    f = tmp_path / "pins.json"
    assert pins.load(f) == {}
    for bad in (
        "not json",
        "[]",
        '{"version": 2, "pins": {}}',
        '{"version": 1, "pins": []}',
        json.dumps({"version": 1, "pins": {str(n): "d" for n in range(pins.MAX_PINS + 1)}}),
    ):
        f.write_text(bad)
        assert pins.load(f) == {}
    f.write_text(json.dumps({"version": 1, "pins": {"ok": "2026-01-01", "x" * 401: "d", "n": 5}}))
    assert pins.load(f) == {"ok": "2026-01-01"}
    f.write_text(json.dumps({"version": 1, "pins": {str(n): "d" for n in range(pins.MAX_PINS)}}))
    with pytest.raises(ValueError, match="too many"):
        pins.add(f, "one-more")
    assert not any(p.name.startswith(".pins-") for p in tmp_path.iterdir())


def test_pin_write_failure_leaves_no_temp_file(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "replace", lambda *a: (_ for _ in ()).throw(OSError("boom")))
    with pytest.raises(OSError):
        pins.add(tmp_path / "pins.json", "s:a")
    assert list(tmp_path.iterdir()) == []


def test_assess_command_prints_json_and_is_read_only(tmp_path, capsys):
    path = tmp_path / "scan.json"
    path.write_text(json.dumps(scan()))
    before = path.read_bytes()
    assert main(["assess", str(path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert set(out["items"]) == {i["id"] for i in scan()["items"]} and out["items"]["s:a"]["tier"] == "too_early"
    assert path.read_bytes() == before and not (tmp_path / "habits.json").exists()
    assert main(["assess", str(tmp_path / "missing.json")]) == 2
    path.write_text(json.dumps({"items": [{"id": 1}]}))
    assert main(["assess", str(path)]) == 2


def test_the_public_snapshot_never_carries_verdicts_habits_or_pins():
    data = {**scan(), "assessments": {"s:a": {"tier": "could_go"}}, "habits": {"x": 1}, "pins": ["s:a"], "evidence": {"sessions": 9}}
    data["items"][0]["changed_on"] = "2026-10-01"
    data["items"][0]["tier"] = "could_go"
    text = json.dumps(snapshot(data))
    assert not any(word in text for word in ("could_go", "assessments", "habits", "pins", "2026-10-01", "evidence", "changed_on"))
