"""Builders on hand-made scans and stand-in engines: ordering, caps, fallbacks and the exact arguments handed to the engine."""

from types import SimpleNamespace as NS
from typing import Any

import pytest

from constellation import cli_reports as cr

PLAIN, COLOUR = cr.Style(), cr.Style(color=True)


def entry(id_, name=None, kind="skill", **over):
    return {"id": id_, "name": name or id_, "kind": kind, "description": "d", **over}


def fake_scan(items, *, relations=None, overlaps=None, assessments=None, counts=None, referenced=None, sessions=3):
    ev = NS(
        sessions=sessions,
        active_days=2,
        span_days=9,
        items={k: NS(count=v, referenced_by=(referenced or {}).get(k, [])) for k, v in (counts or {}).items()},
    )
    data = {"items": items, "relations": relations, "overlaps": overlaps}
    return cr.Scan(data, NS(assessments=assessments or {}, evidence=ev))


def verdict(tier="keep", saves=None, twin_id=None, reasons=(), label="Keep", confidence="high"):
    return NS(tier=tier, saves=saves, twin_id=twin_id, reasons=[NS(text=t) for t in reasons], label=label, confidence=confidence)


def test_label_falls_back_to_the_id_for_a_dangling_reference():
    s = fake_scan([entry("a", "Alpha")])

    assert (s.label("a"), s.label("gone")) == ("Alpha", "gone")


def test_title_is_bold_only_with_colour():
    assert (PLAIN.title("T"), COLOUR.title("T")) == ("T", "\033[1mT\033[0m")


# ---- unused ----


def test_unused_skips_tracked_off_and_untracked_and_sorts_by_saving():
    items = [entry(k) for k in ("off", "untracked", "used", "none", "azero", "one", "big", "tie-b", "tie-a")]
    judged = {
        "off": verdict("off"),
        "untracked": verdict("untracked"),
        "used": verdict(saves=500),
        "none": verdict(saves=None),
        "azero": verdict(saves=0),
        "one": verdict(saves=1),
        "big": verdict(saves=300),
        "tie-b": verdict(saves=300),
        "tie-a": verdict(saves=300),
    }
    counts = {k: 0 for k in judged} | {"used": 2}
    s = fake_scan(items, assessments=judged, counts=counts)

    out = cr._unused(s, None)

    assert [r["name"] for r in out["rows"]] == ["big", "tie-a", "tie-b", "one", "azero", "none"]
    assert out["rows"][0] == {"name": "big", "label": "Keep", "confidence": "high", "saves": 300}
    assert (out["sessions"], out["active_days"], out["span_days"], out["count"]) == (3, 2, 9, 6)


def test_unused_shows_twenty_rows_and_counts_them_all():
    ids = [f"i{n:02}" for n in range(21)]
    s = fake_scan([entry(k) for k in ids], assessments={k: verdict(saves=10 + n) for n, k in enumerate(ids)}, counts=dict.fromkeys(ids, 0))

    out = cr._unused(s, None)

    assert out["count"] == 21 and len(out["rows"]) == 20 and out["rows"][-1]["saves"] == 11


def test_unused_without_sessions_lists_nothing():
    s = fake_scan([entry("a")], assessments={"a": verdict()}, counts={"a": 0}, sessions=0)

    assert cr._unused(s, None)["rows"] == []


# ---- twins ----


def test_twins_say_who_you_use_and_skip_distinct_pairs():
    items = [entry(k, k.upper()) for k in "abcdefghijkl"]

    def pair(x, y, v="overlap"):
        return {"a_id": x, "b_id": y, "verdict": v, "reason": x + y}

    overlaps = [pair("a", "b", "distinct"), pair("c", "d"), pair("e", "f"), pair("g", "h"), pair("i", "j"), pair("k", "l")]
    counts = {"a": 9, "b": 9, "c": 2, "d": 2, "e": 1, "f": 3, "g": 3, "h": 1, "j": 4}  # i, k, l have no usage record at all

    out = cr._twins(fake_scan(items, overlaps=overlaps, counts=counts), None)["pairs"]

    assert [(p["a"], p["b"], p["you_use"]) for p in out] == [
        ("C", "D", "both about equally"),
        ("E", "F", "F"),
        ("G", "H", "G"),
        ("I", "J", "J"),
        ("K", "L", "neither yet"),
    ]
    assert out[0] == {"a": "C", "b": "D", "verdict": "overlap", "reason": "cd", "you_use": "both about equally"}


def test_twins_with_no_overlaps_key_is_empty():
    assert cr._twins(fake_scan([entry("a")], overlaps=None), None) == {"pairs": []}


# ---- why ----


def test_why_collects_references_parts_twin_and_reasons():
    items = [
        entry("t", "Target"),
        entry("tw", "Twin"),
        entry("c2", "Child2"),
        entry("c1", "Child1"),
        entry("u", "User"),
        entry("p", "Plugin"),
    ]
    rels = [
        {"source": "t", "target": "c2", "kind": "contains"},
        {"source": "t", "target": "c1", "kind": "contains"},
        {"source": "t", "target": "gone-child", "kind": "contains"},
        {"source": "t", "target": "u", "kind": "uses"},
        {"source": "p", "target": "t", "kind": "contains"},
        {"source": "u", "target": "t", "kind": "uses"},
        {"source": "gone-source", "target": "t", "kind": "triggers"},
        {"source": "u", "target": "c1", "kind": "uses"},
    ]
    judged = {"t": verdict(saves=77, twin_id="tw", reasons=["first", "second"], label="Review", confidence="low")}
    s = fake_scan(items, relations=rels, assessments=judged, counts={"t": 0}, referenced={"t": ["tw", "gone-ev"]})

    assert cr._why(s, "Target") == {
        "name": "Target",
        "kind": "skill",
        "verdict": "Review",
        "confidence": "low",
        "reasons": ["first", "second"],
        "frees": 77,
        "referenced_by": ["Twin", "User", "gone-ev", "gone-source"],
        "contains": ["Child1", "Child2", "gone-child"],
        "twin": "Twin",
        "history_days": 2,
    }


def test_why_with_no_relations_twin_or_references():
    s = fake_scan([entry("t", "Target")], relations=None, assessments={"t": verdict()}, counts={"t": 0})

    out = cr._why(s, "Target")

    assert (out["referenced_by"], out["contains"], out["twin"]) == ([], [], None)


def test_why_without_a_name_says_no_item_is_named_blank():
    with pytest.raises(cr.ReportError) as raised:
        cr._why(fake_scan([entry("t", "Target")]), None)

    assert str(raised.value) == "No Item named ''."


# ---- cost ----


def test_cost_groups_by_owning_plugin_and_keeps_unmeasured_out(monkeypatch):
    rows = [{"id": f"i{n}", "tokens": t} for n, t in enumerate([5, 7, None, 3, 100, 4])]
    monkeypatch.setattr(cr, "receipt", lambda data: {"total_tokens": 119, "unknown": 1, "rows": rows})
    rels = [{"source": "pl", "target": "i0", "kind": "contains"}, {"source": "pl", "target": "i1", "kind": "contains"}]
    rels += [{"source": "gone", "target": "i3", "kind": "contains"}, {"source": "pl", "target": "i4", "kind": "uses"}]
    s = fake_scan([entry("pl", "Plug")], relations=rels)

    out = cr._cost(s, None)

    assert out["plugins"] == [
        {"name": "(not in a plugin)", "tokens": 104, "items": 2},
        {"name": "Plug", "tokens": 12, "items": 2},
        {"name": "gone", "tokens": 3, "items": 1},
    ]
    assert (out["total"], out["unknown"], out["top"]) == (119, 1, rows)


def test_cost_breaks_a_token_tie_by_name_and_shows_ten_rows(monkeypatch):
    rows = [{"id": f"i{n}", "tokens": 1} for n in range(12)]
    monkeypatch.setattr(cr, "receipt", lambda data: {"total_tokens": 12, "unknown": 0, "rows": rows})
    rels = [{"source": "b", "target": "i0", "kind": "contains"}, {"source": "a", "target": "i1", "kind": "contains"}]

    out = cr._cost(fake_scan([entry("a", "A"), entry("b", "B")], relations=rels), None)

    assert [g["name"] for g in out["plugins"]] == ["(not in a plugin)", "A", "B"]
    assert len(out["top"]) == 10


# ---- doctor ----


def stub_engine(monkeypatch, *, total=100000, rows=(), hooks=(), clashes=(), trig=()):
    monkeypatch.setattr(cr, "receipt", lambda data: {"total_tokens": total})
    monkeypatch.setattr(
        cr, "build_brief", lambda *a: {"range": {"low": 1, "high": 2, "unknown": 3}, "safe": {"rows": list(rows)}, "look": {"rows": []}}
    )
    monkeypatch.setattr(cr, "hook_safety", lambda data: list(hooks))
    monkeypatch.setattr(cr, "conflicts", lambda data: list(clashes))
    monkeypatch.setattr(cr, "trigger_audit", lambda data: {"rows": list(trig)})


def test_doctor_counts_everything_from_the_engine(monkeypatch):
    rows = [{"reason": f"r{n}", "saves": n} for n in range(6)]
    trig = [{"flags": ["greedy"]}, {"flags": ["never"]}, {"flags": ["greedy", "never"]}, {"flags": ["vague"]}, {"flags": ["never"]}]
    stub_engine(monkeypatch, rows=rows, hooks=[{"can_block": True}, {"can_block": False}, {"can_block": True}], clashes=[1, 2], trig=trig)
    items = [
        entry("m", kind="mcp_server"),
        entry("m2", kind="mcp_server", disabled=True),
        entry("c", kind="connector"),
        entry("c2", kind="connector", disabled=True),
    ]
    s = cr.Scan({"items": items, "warnings": ["w1", "w2"]}, NS(assessments={}, evidence=NS()))

    assert cr._doctor(s, None) == {
        "session_start": {"tokens": 100000, "window": 200000, "percent": 50.0},
        "reclaimable": {"low": 1, "high": 2, "unknown": 3},
        "findings": [{"text": f"r{n}", "saves": n} for n in range(5)],
        "hooks": {"count": 3, "can_block": 2},
        "clashes": 2,
        "triggers": {"greedy": 2, "never": 3},
        "mcp": {"servers": 1, "connectors": 1},
        "warnings": 2,
    }


def test_doctor_with_unmeasured_start_and_no_warnings(monkeypatch):
    stub_engine(monkeypatch, total=None)
    s = cr.Scan({"items": [], "warnings": None}, NS(assessments={}, evidence=NS()))

    out = cr._doctor(s, None)

    assert out["session_start"] == {"tokens": None, "window": 200000, "percent": None} and out["warnings"] == 0
    assert cr._doctor(cr.Scan({"items": []}, NS(assessments={}, evidence=NS())), None)["warnings"] == 0


def test_doctor_lists_safe_findings_before_look_findings(monkeypatch):
    stub_engine(monkeypatch, rows=[{"reason": "safe", "saves": 1}])
    monkeypatch.setattr(
        cr,
        "build_brief",
        lambda *a: {
            "range": {"low": 0, "high": 0, "unknown": 0},
            "safe": {"rows": [{"reason": "s", "saves": 1}]},
            "look": {"rows": [{"reason": "l", "saves": None}]},
        },
    )

    out = cr._doctor(cr.Scan({"items": []}, NS(assessments={}, evidence=NS())), None)

    assert out["findings"] == [{"text": "s", "saves": 1}, {"text": "l", "saves": None}]


# ---- ask and clean ----


def test_ask_hands_the_engine_the_scan_question_empty_history_and_an_index_builder(monkeypatch):
    seen: dict[str, Any] = {}

    class Index:
        def __init__(self, items):
            seen["items"] = items

        def close(self):
            seen["closed"] = True

    class Chat:
        def answer(self, data, question, history, index_for, found):
            seen.update(data=data, question=question, history=history, found=found)
            index_for(["an item"])
            return {"answer": "42"}

    monkeypatch.setattr(cr.retrieve, "Index", Index)
    monkeypatch.setattr(cr, "LocalChat", Chat)
    s = cr.Scan({"items": []}, NS(assessments={}, evidence=NS()))

    assert cr._ask(s, "why?") == {"question": "why?", "answer": "42"}
    assert (seen["data"], seen["question"], seen["history"], seen["found"], seen["items"], seen["closed"]) == (
        s.data,
        "why?",
        [],
        s.found,
        ["an item"],
        True,
    )
    assert cr._ask(s, None) == {"question": None, "answer": "42"} and seen["question"] == ""


def test_clean_asks_for_the_five_best_candidates(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(cr, "render_cleanup", lambda data, top: seen.append((data, top)) or "text")
    monkeypatch.setattr(cr, "write_private", lambda path, text: seen.append((path, text)))
    s = cr.Scan({"items": []}, NS(assessments={}, evidence=NS()))

    cr.clean(s, tmp_path / "out.md", False)

    assert seen == [(s.data, 5), (tmp_path / "out.md", "text")]


# ---- coloured headings and the warning threshold ----


def test_every_command_title_is_bold_with_colour():
    cost = {"total": 1, "unknown": 0, "top": [], "plugins": []}
    unused = {"sessions": 1, "span_days": 1, "active_days": 1, "count": 0, "rows": []}
    hooks = {"hooks": [{"name": "h", "phase": "p", "can_block": False, "runs": "r", "bytes": None}]}
    trig = {"files": 1, "rows": [{"name": "s", "flags": ["never"], "count": 0}]}

    assert cr._r_cost(cost, COLOUR).startswith("\033[1mSession-start bill\033[0m\n")
    assert cr._r_unused(unused, COLOUR).startswith("\033[1mNot used lately\033[0m\n")
    assert cr._r_hooks(hooks, COLOUR).startswith("\033[1mHooks, by phase and weight\033[0m\n")
    assert cr._r_triggers(trig, COLOUR).startswith("\033[1mTriggers\033[0m\n")


def test_doctor_warns_when_greedy_and_never_counts_are_equal():
    d = {
        "session_start": {"tokens": 1, "window": 200000, "percent": 0.1},
        "reclaimable": {"low": 0, "high": 0, "unknown": 0},
        "findings": [],
        "hooks": {"count": 1, "can_block": 0},
        "clashes": 0,
        "triggers": {"greedy": 1, "never": 1},
        "mcp": {"servers": 0, "connectors": 0},
        "warnings": 0,
    }

    assert "  ! 1 skills never fire, 1 fire greedily\n" in cr._r_doctor(d, PLAIN)


def test_a_name_half_as_similar_as_the_cutoff_still_counts_as_close():
    with pytest.raises(cr.ReportError) as raised:
        cr.find_item(fake_scan([entry("abcdef")]), "abcxyz")

    assert str(raised.value) == "No Item named 'abcxyz'. Did you mean: abcdef?"
