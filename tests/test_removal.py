import json

import pytest
from fastapi.testclient import TestClient

from constellation import server
from constellation.cli import main
from constellation.removal import MAX_NEIGHBOURS, removal_preview
from constellation.server import create_app


def item(id_, kind="skill", name=None, description="", **extra):
    return {"id": id_, "kind": kind, "name": name or id_, "description": description, **extra}


def scan(**extra):
    return {"items": [item("a", name="alpha-tool", description="Sorts things")], "relations": [], **extra}


def test_lone_unused_item_is_safe():
    out = removal_preview(scan(), "a")
    assert out["safe"] and out["verdict"] == "Safe to remove"
    assert out["loses_coverage"] and out["covered_by"] == [] and out["cluster"] is None
    assert out["reasons"] == ["Nothing refers to it and nothing relies on it alone."]
    assert out["used"] is None and out["last_used"] is None


def test_unknown_id_raises():
    with pytest.raises(KeyError):
        removal_preview(scan(), "zzz")


def test_used_item_with_no_twin_needs_a_check():
    out = removal_preview(scan(usage={"a": {"count": 1, "last_used": "2026-10-01"}}), "a")
    assert not out["safe"] and out["verdict"] == "Check these first"
    assert out["reasons"] == ["Nothing else does the same job, and you used it 1 time."]
    assert (out["used"], out["last_used"]) == (1, "2026-10-01")
    zero = removal_preview(scan(usage={"a": {"count": 0}}), "a")
    assert zero["safe"]
    assert removal_preview(scan(usage={"a": {"count": 2}}), "a")["reasons"] == ["Nothing else does the same job, and you used it 2 times."]
    assert removal_preview(scan(usage={"a": {"count": "many"}}), "a")["used"] is None
    many = removal_preview(scan(usage={"a": {"count": 3}}), "a")
    assert many["reasons"] == ["Nothing else does the same job, and you used it 3 times."]


def test_twin_keeps_coverage_and_disabled_twin_does_not():
    data = scan(usage={"a": {"count": 5}})
    data["items"] += [item("b", name="beta-tool"), item("c", name="gamma-tool", disabled=True)]
    data["overlaps"] = [
        {"a_id": "a", "b_id": "b", "verdict": "duplicate", "reason": "same"},
        {"a_id": "c", "b_id": "a", "verdict": "overlap", "reason": "half"},
        {"a_id": "a", "b_id": "b", "verdict": "distinct", "reason": "x"},
    ]
    out = removal_preview(data, "a")
    assert out["safe"] and not out["loses_coverage"]
    assert out["covered_by"] == [{"id": "b", "name": "beta-tool", "kind": "skill", "why": "same", "verdict": "duplicate"}]
    data["items"][1]["disabled"] = True
    assert removal_preview(data, "a")["loses_coverage"]


def test_twins_are_listed_by_name_then_id():
    data = {"items": [item("a"), item("c", name="aa"), item("b", name="zz"), item("e", name="aa")], "relations": []}
    data["overlaps"] = [{"a_id": "a", "b_id": i, "verdict": "duplicate", "reason": "r"} for i in ("b", "e", "c")]
    assert [r["id"] for r in removal_preview(data, "a")["covered_by"]] == ["c", "e", "b"]


def test_a_mention_needs_a_description():
    data = {"items": [item("a", name="xxxx"), item("b", description=None), item("c", description="XXXX")], "relations": []}
    assert [r["id"] for r in removal_preview(data, "a")["referenced_by"]] == ["c"]


def test_distinct_and_unrelated_overlaps_do_not_cover():
    data = scan()
    data["items"] += [item("b"), item("c")]
    data["overlaps"] = [
        {"a_id": "a", "b_id": "b", "verdict": "distinct", "reason": "x"},
        {"a_id": "b", "b_id": "c", "verdict": "duplicate", "reason": "y"},
    ]
    assert removal_preview(data, "a")["covered_by"] == []


def test_references_hooks_and_wrappers():
    data = scan()
    data["items"] += [
        item("s", name="zeta", description="Run ALPHA-TOOL first."),
        item("s2", name="eta", description="alpha-tool-extra and my-alpha-tool are other things"),
        item("w", kind="agent", name="wrap", description="Wraps"),
        item("h", kind="hook", name="PreToolUse:Bash", description="./run alpha-tool --now"),
        item("h2", kind="hook", name="Stop", description="x"),
        item("d", name="off", description="alpha-tool", disabled=True),
    ]
    data["relations"] = [
        {"source": "h2", "target": "a", "kind": "triggers"},
        {"source": "s2", "target": "a", "kind": "uses"},
        {"source": "s2", "target": "a", "kind": "contains"},
        {"source": "d", "target": "a", "kind": "uses"},
    ]
    data["items"].append(item("w2", kind="agent", name="wrapped"))  # something this Item wraps does not refer to it
    data["overlaps"] = [
        {"a_id": "w", "b_id": "a", "verdict": "wrapper", "reason": "wraps"},
        {"a_id": "a", "b_id": "w2", "verdict": "wrapper", "reason": "r"},
    ]
    out = removal_preview(data, "a")
    assert [(r["name"], r["why"]) for r in out["referenced_by"]] == [
        ("eta", "calls it"),
        ("wrap", "calls it"),
        ("zeta", "mentions its name"),
    ]
    assert [(r["name"], r["why"]) for r in out["hooks"]] == [("PreToolUse:Bash", "mentions its name"), ("Stop", "calls it")]
    assert out["reasons"] == ["3 other Items refer to it.", "2 hooks call or name it."]
    assert not out["safe"]


def test_singular_wording_and_short_names_are_not_matched():
    data = {
        "items": [item("a", name="ab"), item("b", description="uses ab here"), item("h", kind="hook", name="Stop", description="x")],
        "relations": [],
    }
    assert removal_preview(data, "a")["safe"]
    data["items"][0]["name"] = "abc"
    data["items"][1]["description"] = "abc"
    data["relations"] = [{"source": "h", "target": "a", "kind": "triggers"}]
    assert removal_preview(data, "a")["reasons"] == ["1 other Item refers to it.", "1 hook calls or names it."]


def test_plugin_parts_and_cluster():
    data = {
        "items": [item("p", "plugin", "pack"), item("s1", name="one"), item("s2", name="two"), item("x", name="off", disabled=True)],
        "relations": [
            {"source": "p", "target": "s2", "kind": "contains"},
            {"source": "p", "target": "s1", "kind": "contains"},
            {"source": "p", "target": "gone", "kind": "contains"},
        ],
    }
    data["clusters"] = [{"name": "Other", "item_ids": ["q"]}, {"name": "Packs", "item_ids": ["p", "s1", "s2", "x", "missing"]}]
    out = removal_preview(data, "p")
    assert [r["name"] for r in out["contains"]] == ["one", "two"]
    assert out["reasons"] == ["Removing it also removes its 2 parts."]
    assert {r["why"] for r in out["contains"]} == {"goes with it"}
    assert out["cluster"] == {"name": "Packs", "others": ["one", "two"], "more": 0}
    one = removal_preview(data, "s1")
    assert one["cluster"] == {"name": "Packs", "others": ["pack", "two"], "more": 0}
    assert removal_preview(
        {"items": [item("p", "plugin", "pack"), item("s", name="one")], "relations": [{"source": "p", "target": "s", "kind": "contains"}]},
        "p",
    )["reasons"] == ["Removing it also removes its 1 part."]


def test_cluster_neighbours_are_capped_and_exclude_twins():
    ids = [f"n{i}" for i in range(MAX_NEIGHBOURS + 3)]
    data = {
        "items": [item("a", name="alpha"), *(item(i, name=i) for i in ids)],
        "relations": [],
        "clusters": [{"name": "G", "item_ids": ["a", *ids]}],
    }
    data["overlaps"] = [{"a_id": "a", "b_id": "n0", "verdict": "duplicate", "reason": "r"}]
    out = removal_preview(data, "a")
    assert out["cluster"]["more"] == 2 and len(out["cluster"]["others"]) == MAX_NEIGHBOURS and "n0" not in out["cluster"]["others"]
    data["items"][1:] = data["items"][1:2]
    data["clusters"] = [{"name": "G", "item_ids": ["a", "n0"]}]
    assert removal_preview(data, "a")["cluster"] is None


def test_missing_relations_and_malformed_overlap_lists():
    out = removal_preview(
        {"items": [item("a", description=None)], "relations": None, "overlaps": None, "clusters": None, "usage": None}, "a"
    )
    assert out["safe"]


@pytest.fixture
def scan_file(tmp_path):
    data = scan(usage={"a": {"count": 2, "last_used": "2026-10-02"}})
    data["items"].append(item("s", name="zeta", description="Needs alpha-tool"))
    path = tmp_path / "scan.json"
    path.write_text(json.dumps(data))
    return path


def test_cli_prints_a_read_only_preview(scan_file, capsys):
    assert main(["remove-preview", "alpha-tool", str(scan_file)]) == 0
    out = capsys.readouterr().out
    assert "Check these first" in out and "zeta (mentions its name)" in out and "Nothing was changed; remove it by hand." in out
    assert json.loads(scan_file.read_text())["items"][0]["name"] == "alpha-tool"


def test_cli_json_and_safe_and_missing(scan_file, capsys, tmp_path):
    assert main(["remove-preview", "alpha-tool", str(scan_file), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["referenced_by"][0]["name"] == "zeta"
    assert main(["remove-preview", "zeta", str(scan_file)]) == 0
    safe = capsys.readouterr().out
    assert "Safe to remove" in safe and "Referred to by" not in safe and "Same group" not in safe
    assert main(["remove-preview", "nope", str(scan_file)]) == 2


def test_cli_prints_group_and_twins(tmp_path, capsys):
    data = {
        "items": [item("a", name="alpha"), item("b", name="beta")],
        "relations": [],
        "clusters": [{"name": "G", "item_ids": ["a", "b", "c"]}],
    }
    path = tmp_path / "s.json"
    path.write_text(json.dumps(data))
    main(["remove-preview", "alpha", str(path)])
    assert "Same group (G): beta\n" in capsys.readouterr().out
    data["items"] += [item(f"n{i}", name=f"n{i}") for i in range(MAX_NEIGHBOURS + 1)]
    data["clusters"][0]["item_ids"] += [f"n{i}" for i in range(MAX_NEIGHBOURS + 1)]
    data["overlaps"] = [{"a_id": "a", "b_id": "b", "verdict": "overlap", "reason": "r"}]
    path.write_text(json.dumps(data))
    main(["remove-preview", "alpha", str(path)])
    out = capsys.readouterr().out
    assert "Also covered by: beta\n" in out and "and 1 more\n" in out


@pytest.fixture
def client(scan_file, tmp_path, monkeypatch):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html>")
    monkeypatch.setattr(server, "STATIC", static)
    return TestClient(create_app(scan_file, checklist=tmp_path / "c.md"), base_url="http://127.0.0.1:8765")


def test_api_removal(client):
    body = client.get("/api/removal", params={"id": "a"}).json()
    assert body["verdict"] == "Check these first" and body["referenced_by"][0]["id"] == "s"
    assert client.get("/api/removal", params={"id": "nope"}).status_code == 404
    assert client.get("/api/removal").status_code == 422


def test_api_removal_refuses_non_local_hosts_and_bad_scans(client, scan_file, tmp_path):
    assert TestClient(client.app, base_url="http://evil.example").get("/api/removal", params={"id": "a"}).status_code in (400, 403)
    scan_file.write_text("nope")
    assert client.get("/api/removal", params={"id": "a"}).status_code == 404
    scan_file.write_text(json.dumps({"items": ["x"]}))
    assert client.get("/api/removal", params={"id": "a"}).status_code == 404
