"""status.py: builder, summary rules, renderer and the CLI verb, all on invented data."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from constellation import status as st
from constellation.assessment import Assessed
from constellation.cli import main
from constellation.cli_reports import Style

DEMO = Path(__file__).parent.parent / "docs" / "design" / "demo.json"


def item(id_: str, kind: str = "skill", name: str | None = None) -> dict:
    return {"id": id_, "kind": kind, "name": name or id_, "description": "d"}


def found(*tiers: str) -> Assessed:
    return Assessed({f"i{n}": SimpleNamespace(tier=t) for n, t in enumerate(tiers)}, None, False)  # type: ignore[arg-type]


def data(**over):
    base = {
        "items": [item("p", "plugin", "acme"), item("a"), item("b"), item("c")],
        "relations": [{"source": "p", "target": "a", "kind": "contains"}, {"source": "p", "target": "b", "kind": "contains"}],
        "costs": {"a": {"always_on": 300}, "b": {"always_on": 100}, "c": {"always_on": 150}},
        "scanned_at": "2026-11-01",
    }
    return base | over


READY = {
    "state": "ready",
    "since": "2026-10-25",
    "session_start": {"delta": -40},
    "added": [1],
    "removed": [],
    "went_quiet": [{"name": "old-skill"}],
}


def test_bars_group_by_plugin_then_kind_and_cap_at_top():
    s = st.build(data(), found("keep"), None, 0, "2026-11-01")
    assert s.total == 550 and s.bars == [("acme", 400), ("skill (no plugin)", 150)] and s.more == 0 and s.percent == 0.3
    many = data(items=[item(f"s{n}") for n in range(10)], relations=[], costs={f"s{n}": {"always_on": n + 1} for n in range(10)})
    s = st.build(many, found(), None, 0, "2026-11-01")
    assert s.bars == [("skill (no plugin)", 55)] and s.more == 0
    kinds = data(
        items=[item(f"p{n}", "plugin", f"pl{n}") for n in range(10)] + [item(f"s{n}") for n in range(10)],
        relations=[{"source": f"p{n}", "target": f"s{n}", "kind": "contains"} for n in range(10)],
        costs={f"s{n}": {"always_on": n + 1} for n in range(10)},
    )
    s = st.build(kinds, found(), None, 0, "2026-11-01")
    assert [n for n, _ in s.bars] == [f"pl{n}" for n in range(9, 1, -1)] and s.more == 2


def test_verdict_counts_by_tier_and_ignored_tiers():
    s = st.build(
        data(),
        found("keep", "keep_rare", "review", "redundant", "could_go", "could_go", "too_early", "off", "untracked"),
        None,
        0,
        "2026-11-01",
    )
    assert s.verdicts == [("Keep", 2), ("Review", 1), ("Likely redundant", 1), ("Could go", 2), ("Not enough history", 1)]


def test_week_and_age():
    s = st.build(data(), found(), READY, 2, "2026-11-04")
    assert s.week == {"since": "2026-10-25", "delta": -40, "added": 1, "removed": 0, "quiet": ["old-skill"]}
    assert s.pins == 2 and s.age_days == 3
    assert st.build(data(), found(), {"state": "first"}, 0, "2026-11-01").week is None
    assert st.build(data(), found(), None, 0, "2026-11-01").age_days == 0
    assert st.build(data(scanned_at="2026-11-09"), found(), None, 0, "2026-11-01").age_days == 0  # clock skew never goes negative
    assert st.build(data(scanned_at=None), found(), None, 0, "2026-11-01").age_days is None


def test_unmeasured_total():
    s = st.build(data(costs={}), found(), None, 0, "2026-11-01")
    assert (s.total, s.percent, s.bars, s.unknown) == (None, None, [], 3)


@pytest.mark.parametrize(
    ("tiers", "age", "tokens", "summary"),
    [
        ((), 14, 100, "Healthy: nothing looks removable."),
        (("could_go",), 0, 100, "Needs a look: 1 Items look removable."),
        (("redundant", "could_go"), 0, 100, "Needs a look: 2 Items look removable."),
        ((), 15, 100, "Needs a look: nothing looks removable, the scan is 15 days old, scan again."),
        ((), 0, 20_000, "Needs a look: nothing looks removable, session start takes 10.0% of the window."),
        ((), 0, 19_000, "Healthy: nothing looks removable."),
    ],
)
def test_summary(tiers, age, tokens, summary):
    day = f"2026-11-{1 + age:02d}"
    s = st.build(data(costs={"a": {"always_on": tokens}}), found(*tiers), None, 0, day)
    assert s.summary == summary


def test_render_exact_plain_and_colour():
    s = st.build(data(), found("keep", "could_go"), READY, 1, "2026-11-04")
    out = st.render(s, Style())
    assert out == (
        "Constellation status\n\n"
        "  Session start: 550 tokens, 0.3% of a 200k window\n"
        "\nAlways on, biggest first\n"
        "  acme               " + "█" * 24 + "  400\n"
        "  skill (no plugin)  " + "█" * 9 + " " * 15 + "  150\n"
        "\nVerdicts\n"
        "  Keep 1   Review 0   Likely redundant 0   Could go 1   Not enough history 0\n"
        "\nThis week\n"
        "  Since 2026-10-25: 1 added, 0 removed, session start -40 tokens\n"
        "  Went quiet: old-skill\n\n"
        "  Pins: 1   Last scan: 3 days ago\n"
        "  ! Needs a look: 1 Items look removable.\n"
    )
    assert "\033[1mConstellation status\033[0m" in st.render(s, Style(color=True)) and "\033[33m!\033[0m" in st.render(s, Style(color=True))


def test_render_empty_states():
    s = st.build(data(costs={}, scanned_at="2026-10-01"), found(), {"state": "first"}, 0, "2026-11-01")
    out = st.render(s, Style())
    assert "Session start: not measured (3 Items unmeasured)\n" in out and "Always on" not in out
    assert "  No earlier scan to compare with yet. Scan again later.\n" in out
    assert "Last scan: 31 days ago" in out and "  ✗ Needs a look: nothing looks removable, the scan is 31 days old" in out
    quiet = st.build(data(scanned_at=None), found(), {**READY, "went_quiet": [], "session_start": {"delta": None}}, 0, "2026-11-01")
    out = st.render(quiet, Style())
    assert "session start not measured" in out and "Went quiet: nothing" in out and "Last scan: unknown" in out
    assert "Last scan: today" in st.render(st.build(data(), found(), None, 0, "2026-11-01"), Style())
    assert "  and 2 more\n" in st.render(
        st.build(data(), found(), None, 0, "2026-11-01").__class__(**{**s.__dict__, "bars": [("a", 1)], "more": 2}), Style()
    )
    unmeasured = st.build(data(items=[item("m", "mcp_server")], relations=[], costs={}), found(), None, 0, "2026-11-01")
    assert unmeasured.unknown == 1 and "(1 Items unmeasured)" in st.render(unmeasured, Style())


def test_cli_verb_text_json_and_missing_file(tmp_path, capsys):
    capsys.readouterr()
    assert main(["status", str(DEMO)]) == 0
    text = capsys.readouterr().out
    assert text.startswith("Constellation status\n") and "No earlier scan to compare with yet" in text
    assert main(["status", str(DEMO), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert set(out) == {"total", "unknown", "percent", "bars", "more", "verdicts", "week", "pins", "age_days", "summary"}
    assert main(["status", str(tmp_path / "none.json")]) == 2
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"items": [{"id": 1}]}))
    assert main(["status", str(bad)]) == 2
    assert "could not be read" in capsys.readouterr().err


def test_tiny_bar_has_one_block():
    assert st._bar(1, 10_000) == "█" and st._bar(10_000, 10_000) == "█" * 24


def test_equal_groups_sort_by_name():
    d = data(
        items=[item("p1", "plugin", "zeta"), item("p2", "plugin", "alpha"), item("a"), item("b")],
        relations=[{"source": "p1", "target": "a", "kind": "contains"}, {"source": "p2", "target": "b", "kind": "contains"}],
        costs={"a": {"always_on": 7}, "b": {"always_on": 7}},
    )
    assert st.build(d, found(), None, 0, "2026-11-01").bars == [("alpha", 7), ("zeta", 7)]


def test_render_healthy_mark_and_week_wording():
    healthy = st.render(st.build(data(), found("keep"), None, 0, "2026-11-01"), Style())
    assert "  ✓ Healthy: nothing looks removable.\n" in healthy
    two = {**READY, "went_quiet": [{"name": "a"}, {"name": "b"}], "session_start": {"delta": None}}
    out = st.render(st.build(data(), found(), two, 0, "2026-11-04"), Style())
    assert "Since 2026-10-25: 1 added, 0 removed, session start not measured\n  Went quiet: a, b\n" in out
    edge = data(scanned_at="2026-11-01")
    assert "  ! Needs a look: 1 Items" in st.render(st.build(edge, found("could_go"), None, 0, "2026-11-15"), Style())
    assert "  ✗ Needs a look: 1 Items" in st.render(st.build(edge, found("could_go"), None, 0, "2026-11-16"), Style())


def test_cli_reads_pins_and_weekly_sidecar_and_formats_output(tmp_path, capsys):
    from constellation import pins, weekly
    from constellation.assessment import compute
    from constellation.brief import build_brief

    scan = json.loads(DEMO.read_text()) | {"setup": "demo-setup", "scanned_at": "2026-11-05"}
    path = tmp_path / "scan.json"
    path.write_text(json.dumps(scan))
    pins.add(pins.DEFAULT_CACHE, scan["items"][0]["id"])
    pins.add(pins.DEFAULT_CACHE, scan["items"][1]["id"])
    pins.add(pins.DEFAULT_CACHE, "not-in-this-scan")
    found_ = compute(scan)
    snap = weekly.snapshot(scan, found_, build_brief(scan, found_.assessments, found_.evidence))
    old = {**snap, "date": "2000-01-01"}
    weekly.record(weekly.DEFAULT_CACHE, old)
    capsys.readouterr()
    assert main(["status", str(path), "--json"]) == 0
    raw = capsys.readouterr().out
    out = json.loads(raw)
    assert raw.startswith('{\n  "total"') and raw.endswith("}\n") and not raw.endswith("\n\n")
    assert out["pins"] == 2 and out["week"]["since"] == "2000-01-01"
    assert main(["status", str(path)]) == 0
    text = capsys.readouterr().out
    assert text.endswith("\n") and not text.endswith("\n\n") and "Since 2000-01-01:" in text


def test_cli_bad_scan_message_is_exact(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"items": [{"id": 1}]}))
    capsys.readouterr()
    assert main(["status", str(bad)]) == 2
    assert capsys.readouterr().err == "The saved scan could not be read; run `constellation scan` again.\n"
