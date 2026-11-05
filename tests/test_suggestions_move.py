from constellation.brief import brief
from constellation.report import render_cleanup, render_report
from constellation.suggestions import suggest

LABEL = "zzsecretclient"


def data(counts, *, window=("2026-10-01", "2026-10-20"), extra_items=(), relations=(), kind="skill", **item):
    items = [{"id": "s", "kind": kind, "name": "deploy", "description": "", "scope": "global", **item}, *extra_items]
    return {
        "items": items,
        "relations": list(relations),
        "costs": {"s": {"always_on": 40, "on_use": None}},
        "usage": {},
        "usage_window": {"files": 3, "first": window[0], "last": window[1], "skipped": 0} if window else None,
        "projects": {"p1": LABEL, "p2": "other", "p3": "third"},
        "usage_by_project": {"s": {k: {"count": n, "last_used": "2026-10-20"} for k, n in counts.items()}},
    }


def moves(d):
    return [s for s in suggest(d) if s.kind == "move_to_project"]


def test_thresholds():
    for counts, yes in (({"p1": 4, "p2": 1}, True), ({"p1": 3, "p2": 1}, False), ({"p1": 2}, False), ({"p1": 3}, True)):
        assert bool(moves(data(counts))) is yes, counts
    assert not moves(data({"p1": 3, "p2": 3}))  # tie
    assert not moves(data({"p1": 8, "p2": 1, "p3": 1}))  # three projects
    assert not moves(data({}))


def test_fields_and_no_label_anywhere():
    d = data({"p1": 9, "p2": 1})
    (s,) = moves(d)
    assert (s.project, s.confidence, s.tokens_saved, s.item_ids) == ("p1", "high", 40, ("s",))
    assert "20 days" in s.reason and "10 times" in s.reason and "9 of them" in s.reason
    text = s.reason + render_report(d, top=5, color=False, width=100, show_all=False) + render_cleanup(d, top=5)
    assert LABEL not in text and "p1" not in s.reason
    assert "Used mostly in one project" in render_report(d, top=5, color=False, width=100, show_all=False)
    assert s.reason in render_cleanup(d, top=5)
    row = brief(d)["scope"]["rows"][0]
    assert row["project"] == "p1" and row["project_label"] == LABEL and row["confidence"] == "high"
    assert "deletes older ones" in brief(d)["scope"]["caveat"]


def test_confidence_tiers():
    day13, day14 = ("2026-10-01", "2026-10-13"), ("2026-10-01", "2026-10-14")
    assert moves(data({"p1": 5}, window=day14))[0].confidence == "high"
    assert moves(data({"p1": 5}, window=day13))[0].confidence == "medium"
    assert moves(data({"p1": 4}, window=day14))[0].confidence == "medium"
    s = moves(data({"p1": 5}, window=None))[0]
    assert s.confidence == "medium" and "days" not in s.reason


def test_skips():
    assert not moves(data({"p1": 5}, scope="project"))
    assert not moves(data({"p1": 5}, disabled=True))
    assert not moves(data({"p1": 5}, kind="hook"))
    copy = {"id": "c", "kind": "skill", "name": "deploy", "description": "", "scope": "project", "project": "p1"}
    assert not moves(data({"p1": 5}, extra_items=[copy]))
    assert moves(data({"p1": 5}, extra_items=[{**copy, "project": "p2"}]))


def test_plugin_is_judged_as_a_unit():
    d = data(
        {},
        kind="plugin",
        extra_items=[
            {"id": "a", "kind": "skill", "name": "a", "description": "", "scope": "global"},
            {"id": "b", "kind": "skill", "name": "b", "description": "", "scope": "global"},
        ],
        relations=[{"source": "s", "target": "a", "kind": "contains"}, {"source": "s", "target": "b", "kind": "contains"}],
    )
    d["usage_by_project"] = {
        "a": {"p1": {"count": 2, "last_used": None}},
        "b": {"p1": {"count": 2, "last_used": None}, "p2": {"count": 1, "last_used": None}},
    }
    (s,) = moves(d)
    assert s.item_ids == ("s",) and "settings" in s.reason and "5 times" in s.reason and "4 of them" in s.reason


def _item(id_, kind="skill", **extra):
    return {"id": id_, "kind": kind, "name": id_, "description": "", **extra}


def test_every_skip_is_a_continue_and_defaults_are_global():
    items = [
        _item("proj", scope="project"),
        _item("off", disabled=True),
        _item("hook", "hook"),
        _item("plug", "plugin"),
        _item("inner"),
        _item("none"),
        _item("tie"),
        _item("three"),
        _item("low"),
        _item("copyme"),
        {**_item("cp"), "name": "copyme", "scope": "project", "project": "p1"},
        _item("good"),  # no scope key: defaults to global
        _item("agent1", "agent", scope="global"),
        _item("mcp1", "mcp_server", scope="global"),
    ]
    use = {n: {"p1": {"count": 5, "last_used": None}} for n in ("proj", "off", "hook", "inner", "copyme", "good", "agent1", "mcp1")}
    use["tie"] = {"p1": {"count": 3, "last_used": None}, "p2": {"count": 3, "last_used": None}}
    use["three"] = {k: {"count": 5, "last_used": None} for k in ("p1", "p2", "p3")}
    use["low"] = {"p1": {"count": 3, "last_used": None}, "p2": {"count": 1, "last_used": None}}
    d = {
        "items": items,
        "relations": [{"source": "plug", "target": "inner", "kind": "contains"}],
        "usage_by_project": use,
        "usage_window": None,
    }
    assert sorted(s.item_ids[0] for s in moves(d)) == ["agent1", "good", "mcp1", "plug"]


def test_exact_texts():
    d = data({"p1": 9, "p2": 1}, kind="plugin", name="deploy")
    assert (
        moves(d)[0].reason
        == "deploy (plugin) was used 10 times over 20 days, 9 of them in one project. Enable it only in that project's settings."
    )
    d = data({"p1": 9, "p2": 1}, window=None)
    assert moves(d)[0].reason == "deploy (skill) was used 10 times, 9 of them in one project. Move it into that project's .claude/ folder."
    plain = render_report(d, top=5, color=False, width=200, show_all=False)
    assert "Used mostly in one project -" in plain
    assert (
        "  - deploy (skill) was used 10 times, 9 of them in one project. Move it into that project's .claude/ folder. (medium confidence)"
        in plain
    )
    assert "\n  Based only on the transcripts" in plain and "\033" not in plain
    assert "\033[2m  Based only" in render_report(d, top=5, color=True, width=200, show_all=False)
    assert "\033[1mUsed mostly in one project" in render_report(d, top=5, color=True, width=200, show_all=False)
    wrapped = render_report(d, top=5, color=False, width=60, show_all=False)
    assert "\n      " in wrapped.split("Used mostly")[1]
    clean = render_cleanup(d, top=5)
    assert "\n\n## Used mostly in one project\n\n- [ ] deploy (skill) was used 10 times" in clean
    assert brief(d)["scope"]["rows"][0] == {
        "id": moves(d)[0].id,
        "kind": "move_to_project",
        "item_ids": ["s"],
        "removes": None,
        "reason": moves(d)[0].reason,
        "tokens_saved": 40,
        "project": "p1",
        "confidence": "medium",
        "project_label": LABEL,
    }
