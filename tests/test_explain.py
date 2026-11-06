import json

import pytest
from fastapi.testclient import TestClient

from constellation import server
from constellation.server import create_app

BASE_URL = "http://127.0.0.1:8765"
IDS = ["local/1/srv", *(f"skill:s{n}" for n in range(1, 8))]


@pytest.fixture(autouse=True)
def built_app(tmp_path, monkeypatch):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html>")
    monkeypatch.setattr(server, "STATIC", static)


def scan(**extra):
    items = [{"id": i, "kind": "skill", "name": f"gizmo-{n}", "description": "d", "source": "x"} for n, i in enumerate(IDS)]
    clusters = [{"name": n, "item_ids": IDS[a:b]} for n, a, b in [("Delta", 0, 1), ("Bravo", 1, 3), ("Alpha", 3, 5), ("Charlie", 5, 8)]]
    overlaps = [
        {"a_id": IDS[0], "b_id": IDS[1], "verdict": "duplicate", "reason": "same"},
        {"a_id": IDS[2], "b_id": IDS[3], "verdict": "duplicate", "reason": "same"},
        {"a_id": IDS[4], "b_id": IDS[5], "verdict": "wrapper", "reason": "calls"},
        {"a_id": IDS[6], "b_id": IDS[7], "verdict": "duplicate", "reason": "same"},
    ]
    costs = {i: {"always_on": 10 * (n + 1), "on_use": None} for n, i in enumerate(IDS[:6])}
    return {
        "items": items,
        "relations": [],
        "labels": {},
        "clusters": clusters,
        "overlaps": overlaps,
        "costs": costs,
        "warnings": [],
        **extra,
    }


def get(tmp_path, data, query=""):
    path = tmp_path / "scan.json"
    path.write_text(json.dumps(data))
    return TestClient(create_app(path), base_url=BASE_URL).get("/api/explain" + query)


def test_explain_lists_three_largest_clusters_five_costs_unused_and_capped_actions(tmp_path):
    usage = {i: {"count": 0 if n < 7 else 2} for n, i in enumerate(IDS)}
    window = {"files": 4, "first": "2026-10-01", "last": "2026-10-10", "skipped": 0}
    body = get(tmp_path, scan(usage=usage, usage_window=window)).json()
    assert [c["name"] for c in body["clusters"]] == ["Charlie", "Alpha", "Bravo"]
    assert [c["items"] for c in body["clusters"]] == [3, 2, 2]
    assert [c["name"] for c in body["costs"]] == ["gizmo-5", "gizmo-4", "gizmo-3", "gizmo-2", "gizmo-1"]
    assert body["costs"][0] == {"name": "gizmo-5", "kind": "skill", "always_on": 60}
    assert len(body["unused"]) == 5 and len(body["actions"]) == 8
    assert body["window"] == {"files": 4, "days": 10}
    assert (body["items"], body["known"], body["unknown"], body["public"]) == (8, 210, 2, False)


def test_explain_never_counts_unknown_cost_as_zero(tmp_path):
    body = get(tmp_path, scan()).json()
    assert body["clusters"][0]["always_on"] == 60  # Charlie: gizmo-5 known, 6 and 7 unknown
    assert body["unknown"] == 2
    none = scan(costs={})
    body = get(tmp_path, none).json()
    assert body["known"] is None and body["costs"] == []
    assert {c["always_on"] for c in body["clusters"]} == {None}
    assert "cost not measured" in body["text"] and "cost unknown" in body["text"]


def test_explain_unused_is_null_without_usage_window(tmp_path):
    body = get(tmp_path, scan()).json()
    assert body["unused"] is None and body["window"] is None
    assert "Usage was not read in this scan." in body["text"]


def test_explain_ties_are_ordered_by_name(tmp_path):
    data = scan()
    data["costs"] = {i: {"always_on": 5, "on_use": None} for i in IDS}
    data["clusters"] = [{"name": n, "item_ids": [IDS[k]]} for k, n in enumerate(["Zed", "Mid", "Abe", "Kay"])]
    data["items"][5]["name"] = "gizmo-0"  # a name tie is broken by id
    body = get(tmp_path, data).json()
    assert [c["name"] for c in body["clusters"]] == ["Abe", "Kay", "Mid"]
    assert [c["name"] for c in body["costs"]] == ["gizmo-0", "gizmo-0", "gizmo-1", "gizmo-2", "gizmo-3"]
    assert body["costs"][0]["name"] == "gizmo-0"


def test_public_explain_has_no_usage_ids_or_private_text(tmp_path):
    ghp = "".join(["ghp_", "aB3dE5gH" * 4, "7jK9"])
    ant = "".join(["sk-ant-", "a1B2c3D4" * 4])
    leak = f"/Users/demo-person/x a@b.example {ghp} {ant}"
    data = scan(
        usage={i: {"count": 0} for i in IDS},
        usage_window={"files": 4, "first": "2026-10-01", "last": "2026-10-10", "skipped": 0},
        warnings=["warnmarker-77"],
        memory_bytes=987654,
        scope="scopemarker-77",
        project="projectmarker-77",
    )
    data["overlaps"][0]["reason"] = f"see {leak}"
    data["items"][0]["source"] = "local/1/srv"
    data["items"][1]["name"] = f"named {leak}"
    data["items"][2].update(command="commandmarker-77", scope="scopemarker-77", project="projectmarker-77", memory_bytes=987654)
    data["clusters"][0]["name"] = f"cluster {leak}"
    res = get(tmp_path, data, "?public=true")
    text = res.text
    banned = ["/Users/demo-person/x", "a@b.example", ghp, ant, "local/1/srv", "2026-10-", "-77", "987654", *IDS]
    assert [m for m in banned if m in text] == []
    body = res.json()
    assert body["public"] is True and body["unused"] is None and body["window"] is None
    assert set(body) == {"public", "items", "known", "unknown", "clusters", "costs", "unused", "window", "scanned_at", "actions", "text"}
    assert body["actions"] and all(a["reason"].strip() for a in body["actions"])


def test_public_explain_has_no_remove_unused_action(tmp_path):
    data = scan(usage={i: {"count": 0} for i in IDS}, usage_window={"files": 4, "first": "2026-10-01", "last": "2026-10-10", "skipped": 0})
    data["overlaps"] = []
    assert "never seen" in get(tmp_path, data).json()["actions"][0]["reason"]
    assert get(tmp_path, data, "?public=1").json()["actions"] == []


def test_explain_text_has_fixed_headings_and_public_footer(tmp_path):
    headings = [
        "# My Claude Code setup",
        "## Largest clusters",
        "## Costliest always-on",
        "## Not used lately",
        "## Three suggested actions",
    ]
    local = get(tmp_path, scan()).json()["text"]
    public = get(tmp_path, scan(), "?public=true").json()["text"]
    for text in (local, public):
        assert [line for line in text.splitlines() if line.startswith("#")] == headings
    footer = "Shared from Constellation (public summary: no usage dates, paths or ids)."
    assert footer not in local and public.rstrip().endswith(footer)
    assert "Not included in public summaries." in public and "Not included" not in local


def test_explain_404_when_scan_unreadable(tmp_path):
    client = TestClient(create_app(tmp_path / "missing.json"), base_url=BASE_URL)
    assert client.get("/api/explain").status_code == 404


def test_render_explain_exact_text_local_and_empty(tmp_path):
    from constellation.explain import explain, render_explain

    usage = {i: {"count": 0} for i in IDS[:2]}
    data = scan(usage=usage, usage_window={"files": 4, "first": "2026-10-01", "last": "2026-10-10", "skipped": 0})
    data["clusters"] = data["clusters"][:1]
    data["overlaps"] = []
    out = render_explain(explain(data))
    assert out == (
        "# My Claude Code setup\n\n"
        "8 items, 210 always-on tokens known, 2 with unknown cost.\n\n"
        "## Largest clusters\n\n- Delta: 1 items, 10 tokens\n\n"
        "## Costliest always-on\n\n- gizmo-5 (skill): 60 tokens\n- gizmo-4 (skill): 50 tokens\n"
        "- gizmo-3 (skill): 40 tokens\n- gizmo-2 (skill): 30 tokens\n- gizmo-1 (skill): 20 tokens\n\n"
        "## Not used lately\n\nChecked 4 transcripts over 10 days.\n\n"
        "- gizmo-1 (skill): 20 tokens\n- gizmo-0 (skill): 10 tokens\n\n"
        "## Three suggested actions\n\n"
        "- gizmo-1 (skill) was never seen in 4 transcripts (2026-10-01 to 2026-10-10, 10 days). It costs 20 always-on tokens every session."
        " Claude Code deletes old transcripts and 0 skipped files were not read, so this is not proof it is unused. (saves 20 tokens)\n"
        "- gizmo-0 (skill) was never seen in 4 transcripts (2026-10-01 to 2026-10-10, 10 days). It costs 10 always-on tokens every session."
        " Claude Code deletes old transcripts and 0 skipped files were not read, so this is not proof it is unused. (saves 10 tokens)\n"
    )
    bare = {"items": [], "clusters": [], "relations": [], "labels": {}, "costs": {}, "overlaps": []}
    assert render_explain(explain(bare)) == (
        "# My Claude Code setup\n\n0 items, cost not measured, 0 with unknown cost.\n\n"
        "## Largest clusters\n\n- None.\n\n## Costliest always-on\n\n- None measured.\n\n"
        "## Not used lately\n\nUsage was not read in this scan.\n\n## Three suggested actions\n\n- None.\n"
    )
    nowin = {**bare, "usage_window": {"files": 2, "first": None, "last": None, "skipped": 0}}
    assert explain(nowin)["window"] == {"files": 2, "days": 0}
    assert explain(nowin)["unused"] == []
    assert "Checked 2 transcripts over 0 days.\n\n- None.\n" in render_explain(explain(nowin))


def test_render_explain_exact_text_public_and_unknown_costs(tmp_path):
    from constellation.explain import explain, render_explain

    data = scan()
    data["costs"] = {}
    data["clusters"] = data["clusters"][:1]
    data["overlaps"] = data["overlaps"][:1]
    out = render_explain(explain(data, public=True))
    assert out == (
        "# My Claude Code setup\n\n"
        "8 items, cost not measured, 8 with unknown cost.\n\n"
        "## Largest clusters\n\n- Delta: 1 items, cost unknown\n\n"
        "## Costliest always-on\n\n- None measured.\n\n"
        "## Not used lately\n\nNot included in public summaries.\n\n"
        "## Three suggested actions\n\n"
        "- Remove one of these two: gizmo-0 (skill) and gizmo-1 (skill). same (saves cost unknown)\n\n"
        "Shared from Constellation (public summary: no usage dates, paths or ids).\n"
    )


def test_explain_rejects_a_non_local_host(tmp_path):
    path = tmp_path / "scan.json"
    path.write_text(json.dumps(scan()))
    client = TestClient(create_app(path), base_url=BASE_URL)
    assert client.get("/api/explain", headers={"host": "evil.example:8765"}).status_code == 403


def test_explain_public_flag_must_be_boolean_and_defaults_to_private(tmp_path):
    # Fail-open risk: a missing flag means the PRIVATE summary, so the UI must check response.public before sharing.
    for query in ("?public=maybe", "?public="):
        assert get(tmp_path, scan(), query).status_code == 422
    assert get(tmp_path, scan()).json()["public"] is False


def test_explain_404_does_not_show_the_scan_path(tmp_path):
    res = TestClient(create_app(tmp_path / "missing.json"), base_url=BASE_URL).get("/api/explain")
    assert res.json() == {"detail": "scan could not be read"}


def test_explain_action_dates_come_from_the_scan_and_never_leak_publicly():
    from constellation.explain import explain

    usage = {IDS[1]: {"count": 2, "last_used": "2026-10-09"}, IDS[2]: {"count": 0}}
    data = scan(scanned_at="2026-11-05", usage=usage, usage_window={"files": 4, "first": "2026-10-01", "last": "2026-10-10", "skipped": 0})
    body = explain(data)
    assert body["scanned_at"] == "2026-11-05" and len(body["actions"]) <= 8
    assert all(set(a) == {"kind", "reason", "tokens_saved", "last_used", "since"} for a in body["actions"])
    unused = next(a for a in body["actions"] if a["kind"] == "remove_unused")
    assert unused["since"] == "2026-10-01" and unused["last_used"] is None
    assert all(a["since"] is None for a in body["actions"] if a["kind"] != "remove_unused")
    assert any(a["last_used"] == "2026-10-09" for a in body["actions"])
    pub = explain(data, public=True)
    assert pub["scanned_at"] is None and all(a["last_used"] is None and a["since"] is None for a in pub["actions"])
    assert explain(scan())["scanned_at"] is None
