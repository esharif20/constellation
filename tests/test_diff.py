import json

from constellation.cli import main
from constellation.diff import diff_scans, render_diff


def item(id, name="n", kind="skill", description="d", disabled=False):
    return {"id": id, "kind": kind, "name": name, "description": description, "source": "s", "disabled": disabled}


def scan(items, costs=None, at=None):
    data = {"items": items, "costs": {k: {"always_on": v[0], "on_use": v[1]} for k, v in (costs or {}).items()}}
    if at:
        data["scanned_at"] = at
    return data


def test_added_and_removed_by_id():
    d = diff_scans(scan([item("a", "A"), item("b", "B")]), scan([item("b", "B"), item("c", "C")], {"c": (420, None)}))
    assert d["added"] == [{"id": "c", "kind": "skill", "name": "C", "always_on": 420}]
    assert [r["id"] for r in d["removed"]] == ["a"] and d["removed"][0]["always_on"] is None
    assert d["changed"] == []


def test_changed_lists_only_differing_fields_in_order():
    old = scan([item("a", "A", description="x")], {"a": (300, 5)})
    new = scan([item("a", "A", description="y")], {"a": (520, 5)})
    (row,) = diff_scans(old, new)["changed"]
    assert row["fields"] == ["always_on", "description"]
    assert row["always_on"] == [300, 520] and row["on_use"] == [5, 5]
    both = diff_scans(scan([item("a", "A")], {"a": (1, 2)}), scan([item("a", "A", disabled=True)], {"a": (3, 4)}))
    assert both["changed"][0]["fields"] == ["always_on", "on_use", "disabled"]
    assert diff_scans(scan([item("a")], {"a": (1, 2)}), scan([item("a")], {"a": (1, 2)}))["changed"] == []


def test_description_text_never_in_output(tmp_path, capsys):
    old = scan([item("a", "A", description="SECRET-DESC one")])
    new = scan([item("a", "A", description="SECRET-DESC two")])
    assert "SECRET-DESC" not in render_diff(diff_scans(old, new), color=False, width=80)
    (tmp_path / "o.json").write_text(json.dumps(old))
    (tmp_path / "n.json").write_text(json.dumps(new))
    assert main(["diff", str(tmp_path / "o.json"), str(tmp_path / "n.json"), "--json"]) == 0
    assert "SECRET-DESC" not in capsys.readouterr().out


def test_name_fallback_matches_other_machine():
    d = diff_scans(scan([item("local/1/git", "git", "mcp_server")]), scan([item("local/2/git", "git", "mcp_server")]))
    assert d["added"] == d["removed"] == d["changed"] == []
    dup = diff_scans(scan([item("x/1", "git"), item("x/2", "git")]), scan([item("y/1", "git")]))
    assert len(dup["removed"]) == 2 and len(dup["added"]) == 1
    dup = diff_scans(scan([item("x/1", "git")]), scan([item("y/1", "git"), item("y/2", "git")]))
    assert len(dup["removed"]) == 1 and len(dup["added"]) == 2
    kinds = diff_scans(scan([item("x", "git", "skill")]), scan([item("y", "git", "hook")]))
    assert len(kinds["added"]) == len(kinds["removed"]) == 1


def test_totals_skip_unknown():
    old = scan([item("a"), item("b")], {"a": (100, None), "b": (None, None)})
    new = scan([item("a"), item("b"), item("c")], {"a": (750, None)})
    t = diff_scans(old, new)["always_on"]
    assert t == {"old": 100, "new": 750, "delta": 650, "unknown_old": 1, "unknown_new": 2}
    assert diff_scans(new, old)["always_on"]["delta"] == -650


def test_sorted_by_kind_name_id():
    d = diff_scans(scan([]), scan([item("2", "b", "hook"), item("3", "a", "skill"), item("1", "a", "hook")]))
    assert [r["id"] for r in d["added"]] == ["1", "2", "3"]


def test_render_copy():
    old = scan([item("r", "release-notes"), item("h", "mend-gasket", "hook"), item("k", "keep")], {"r": (300, None)}, "2026-10-01")
    new = scan(
        [item("r", "release-notes", description="e"), item("p", "pdf-tools"), item("k", "keep")],
        {"r": (520, None), "p": (420, 1)},
        "2026-11-04",
    )
    out = render_diff(diff_scans(old, new), color=False, width=80)
    assert out.splitlines()[0] == "Setup diff: 2026-10-01 -> 2026-11-04"
    assert "Always-on: 300 -> 940 tokens (+640); unknown 2 -> 1" in out
    assert "Added (1)\n+ skill  pdf-tools  420 tokens" in out
    assert "Removed (1)\n- hook  mend-gasket  unknown" in out
    assert "Changed (1)\n~ skill  release-notes  always-on 300 -> 520, description" in out
    assert "\033" in render_diff(diff_scans(old, new), color=True, width=80)


def test_render_empty_and_unknown_date():
    out = render_diff(diff_scans(scan([item("a")]), scan([item("a")])), color=False, width=80)
    assert out.startswith("Setup diff: unknown date -> unknown date\n")
    assert out.rstrip().endswith("No differences.") and "Added" not in out
    assert "on-use 5 -> unknown" in render_diff(
        diff_scans(scan([item("a")], {"a": (1, 5)}), scan([item("a")], {"a": (1, None)})), color=False, width=80
    )


def test_render_truncates_to_width():
    d = diff_scans(scan([]), scan([item("a", "x" * 200)]))
    rows = [x for x in render_diff(d, color=False, width=40).splitlines() if x.startswith("+ ")]
    assert len(rows) == 1 and len(rows[0]) == 40 and rows[0].endswith("…")


def test_cli_diff_text_and_json(tmp_path, capsys):
    (tmp_path / "o.json").write_text(json.dumps(scan([item("a", "A")])))
    (tmp_path / "n.json").write_text(json.dumps(scan([item("b", "B")])))
    assert main(["diff", str(tmp_path / "o.json"), str(tmp_path / "n.json")]) == 0
    out = capsys.readouterr().out
    assert "Added (1)" in out and "+ skill  B  unknown" in out
    assert main(["diff", str(tmp_path / "o.json"), str(tmp_path / "n.json"), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["added"][0]["id"] == "b"


def test_cli_diff_bad_file_exits_2(tmp_path, capsys):
    (tmp_path / "o.json").write_text(json.dumps(scan([])))
    assert main(["diff", str(tmp_path / "o.json"), str(tmp_path / "missing.json")]) == 2
    assert main(["diff", str(tmp_path / "missing.json"), str(tmp_path / "o.json")]) == 2
    assert "not a constellation scan" in capsys.readouterr().err


def test_old_side_disabled_and_changed_order():
    d = diff_scans(
        scan([item("a", "z", disabled=True), item("b", "a")], {"b": (1, 1)}), scan([item("a", "z"), item("b", "a")], {"b": (2, 1)})
    )
    assert [(r["name"], r["fields"]) for r in d["changed"]] == [("a", ["always_on"]), ("z", ["disabled"])]


def test_render_exact_plain_and_color():
    d = diff_scans(scan([item("a", "A")]), scan([item("a", "A", description="x")]))
    head = "Setup diff: unknown date -> unknown date\nAlways-on: 0 -> 0 tokens (+0); unknown 1 -> 1\n"
    assert render_diff(d, color=False, width=80) == head + "\nChanged (1)\n~ skill  A  description\n"
    assert render_diff(d, color=True, width=80) == (
        "\033[1mSetup diff: unknown date -> unknown date\033[0m\nAlways-on: 0 -> 0 tokens (+0); unknown 1 -> 1\n"
        "\n\033[1mChanged (1)\033[0m\n\033[33m~ skill  A  description\033[0m\n"
    )
    for old, new in (([], [item("a")]), ([item("a")], [])):
        assert "No differences." not in render_diff(diff_scans(scan(old), scan(new)), color=False, width=80)
    assert render_diff(diff_scans(scan([]), scan([])), color=False, width=80).endswith("unknown 0 -> 0\n\nNo differences.\n")
