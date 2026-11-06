import json
import os
import re
import stat

import pytest

from constellation import weekly
from constellation.assessment import Assessed
from constellation.brief import build_brief
from constellation.verdict_types import Assessment, Evidence, ItemEvidence, Reason
from constellation.weekly import FIRST, TOP, summarize

NOW, TODAY = "2026-11-06", "2026-11-06"
R0 = {"low": 0, "high": 0, "unknown": 0, "confidence": "low"}


def it(kind="skill", name="a", tier="keep", label="Keep", why="Used 5 times", q=False, c=100, u=0):
    return {"k": kind, "n": name, "t": tier, "l": label, "w": why, "q": q, "c": c, "u": u}


def snap(day, items, setup="s", reclaim=R0):
    return {"setup": setup, "date": day, "items": items, "reclaim": reclaim}


def pair(then, now, since=None, today=TODAY, day=NOW, **kw):
    """summarize() of two item maps, the older dated 2026-10-30."""
    return summarize(snap(day, now, **kw), [snap("2026-10-30", then, **kw)], today, since)


# ---- the first-scan and baseline-choice states ----


def test_first_scan_says_not_enough_history():
    assert summarize(snap(NOW, {"h": it()}), [], TODAY) == {"state": "first", "headline": FIRST}
    assert re.fullmatch(r"^Not enough history yet: .*$", FIRST)


@pytest.mark.parametrize("other", [snap(NOW, {}), snap("2026-11-07", {}), snap("2026-10-01", {}, setup="other")])
def test_same_day_later_or_other_setup_is_not_a_baseline(other):
    assert summarize(snap(NOW, {"h": it()}), [other], TODAY)["state"] == "first"


def test_baseline_is_the_newest_earlier_snapshot_of_this_setup():
    saved = [
        snap("2026-10-01", {"x": it(name="x")}),
        snap("2026-11-05", {"y": it(name="y")}),
        snap("2026-11-06", {}),
        snap("2026-11-04", {}),
    ]
    got = summarize(snap(NOW, {"y": it(name="y")}), saved, TODAY)
    assert (got["since"], got["days"], got["added"], got["removed"]) == ("2026-11-05", 1, [], [])


def test_a_snapshot_dated_after_today_is_ignored_as_clock_skew():
    saved = [snap("2026-11-01", {"y": it(name="y")}), snap("2026-11-20", {"z": it(name="z")})]
    got = summarize(snap("2026-12-01", {"y": it(name="y")}), saved, TODAY)
    assert (got["since"], got["added"], got["removed"], got["days"]) == ("2026-11-01", [], [], 30)
    assert summarize(snap("2026-12-01", {}), [snap("2026-11-20", {})], TODAY)["state"] == "first"
    assert summarize(snap("2026-12-01", {}), [snap(TODAY, {})], TODAY)["state"] == "ready"  # today itself is not the future


def test_since_picks_the_newest_snapshot_on_or_before_it():
    saved = [snap("2026-10-01", {"a": it()}), snap("2026-10-20", {}), snap("2026-11-02", {})]
    now = snap(NOW, {})
    assert summarize(now, saved, TODAY, "2026-10-20")["since"] == "2026-10-20"
    assert summarize(now, saved, TODAY, "2026-10-19")["since"] == "2026-10-01"
    assert summarize(now, saved, TODAY, "2026-09-30") == {"state": "first", "headline": FIRST}
    assert summarize(now, saved, TODAY)["since"] == "2026-11-02"


# ---- what changed ----


def test_added_and_removed_are_names_and_kinds_only_sorted_and_cleaned():
    then = {"h1": it("skill", "gone-b"), "h2": it("agent", "gone-a"), "h3": it("skill", "stays")}
    now = {"h3": it("skill", "stays"), "h4": it("skill", "new\nline  name"), "h5": it("agent", "new-agent")}
    got = pair(then, now)
    assert got["added"] == [{"kind": "agent", "name": "new-agent"}, {"kind": "skill", "name": "new line name"}]
    assert got["removed"] == [{"kind": "agent", "name": "gone-a"}, {"kind": "skill", "name": "gone-b"}]
    assert "h1" not in json.dumps(got) and "h4" not in json.dumps(got)


def test_no_change_has_empty_lists_and_a_plain_headline():
    items = {"h": it(c=100)}
    got = pair(items, items, reclaim=R0)
    assert got["state"] == "ready"
    assert (
        got["headline"]
        == "Since 2026-10-30: no Items added or removed; session start 100 to 100 tokens (+0); you could free 0 tokens (was 0)."
    )
    assert (got["verdict_changes"], got["went_quiet"], got["used_most"]) == ([], [], [])


def test_headline_counts_changes_quiet_and_reclaim_ranges():
    then = {"a": it(name="a"), "b": it(name="b")}
    now = {"a": it(name="a", q=True), "c": it(name="c")}
    r_then = {"low": 100, "high": 500, "unknown": 1, "confidence": "low"}
    summary = summarize(snap(NOW, now, reclaim={**R0, "low": 1200, "high": 3400}), [snap("2026-10-30", then, reclaim=r_then)], TODAY)
    assert summary["headline"] == (
        "Since 2026-10-30: 1 added, 1 removed; session start 200 to 200 tokens (+0); 1 went quiet; "
        "you could free 1,200 to 3,400 tokens (was 100 to 500)."
    )
    assert summary["reclaim"] == {"now": {**R0, "low": 1200, "high": 3400}, "then": r_then}


def test_a_single_value_range_is_not_written_twice():
    got = pair({}, {}, reclaim={"low": 700, "high": 700, "unknown": 0, "confidence": "high"})
    assert got["headline"].endswith("you could free 700 tokens (was 700).")


# ---- session-start cost, honest about unknowns ----


def test_session_start_delta_and_unknown_counts():
    then = {"a": it(c=100), "b": it(name="b", c=None)}
    now = {"a": it(c=150), "c": it(name="c", c=None), "d": it(name="d", c=None), "e": it(name="e", c=40)}
    got = pair(then, now)["session_start"]
    assert got == {"then": 100, "now": 190, "delta": 90, "unknown_then": 1, "unknown_now": 2}
    assert "counting known costs only" in pair(then, now)["headline"]


def test_equal_unknown_counts_are_still_flagged():
    both = {"a": it(c=500), "b": it(name="b", c=None)}
    assert "counting known costs only" in pair(both, both)["headline"]


def test_unknown_on_one_side_alone_is_flagged_and_a_fall_is_signed():
    full = {"a": it(c=500)}
    one_sided = pair({"a": it(c=500)}, {"a": it(c=200), "b": it(name="b", c=None)})
    assert one_sided["session_start"]["delta"] == -300
    assert "(-300) counting known costs only" in one_sided["headline"]
    assert "counting" not in pair(full, {"a": it(c=200)})["headline"]
    assert "counting" in pair({"a": it(c=500), "b": it(name="b", c=None)}, {"a": it(c=200)})["headline"]


def test_nothing_measured_is_not_zero():
    unknown = {"a": it(c=None)}
    for then, now in (
        (unknown, unknown),
        (unknown, {"a": it(c=10)}),
        ({"a": it(c=10)}, unknown),
        ({}, {"a": it(c=10)}),
        ({"a": it(c=10)}, {}),
    ):
        got = pair(then, now)
        assert got["session_start"]["delta"] is None
        assert "session start cost not measured" in got["headline"]
    both = pair(unknown, unknown)["session_start"]
    assert (both["then"], both["now"]) == (None, None)
    zero = pair({"a": it(c=0)}, {"a": it(c=0)})["session_start"]
    assert (zero["then"], zero["now"], zero["delta"]) == (0, 0, 0)  # a measured zero is real


# ---- verdict changes, quiet Items, most used ----


def test_verdict_flips_say_from_to_and_why_most_serious_first():
    then = {k: it(name=k, tier="keep", label="Keep") for k in "abcd"} | {"e": it(name="e", tier="keep", label="Keep")}
    now = {
        "a": it(name="a", tier="review", label="Review", why="Used 6 times, none in 74 active days"),
        "b": it(name="b", tier="could_go", label="Could go", why="Never used"),
        "c": it(name="c", tier="keep", label="Keep"),
        "d": it(name="d", tier="could_go", label="Could go", why="Never used either"),
        "e": it(name="e", tier="redundant", label="Likely redundant", why="Does the job of b"),
        "f": it(name="f", tier="could_go", label="Could go"),
    }
    got = pair(then, now)["verdict_changes"]
    assert got == [
        {"kind": "skill", "name": "b", "from": "Keep", "to": "Could go", "why": "Never used"},
        {"kind": "skill", "name": "d", "from": "Keep", "to": "Could go", "why": "Never used either"},
        {"kind": "skill", "name": "e", "from": "Keep", "to": "Likely redundant", "why": "Does the job of b"},
        {"kind": "skill", "name": "a", "from": "Keep", "to": "Review", "why": "Used 6 times, none in 74 active days"},
    ]


def test_every_tier_has_a_place_in_the_severity_order():
    tiers = ("keep", "keep_rare", "review", "redundant", "could_go", "too_early", "off", "untracked")
    assert sorted(tiers) == sorted(weekly._SEVERITY)


def test_flips_to_tiers_sort_in_the_documented_order():
    tiers = ("off", "untracked", "keep_rare", "too_early", "review", "redundant", "could_go")
    then = {t: it(name=t, tier="keep") for t in tiers}
    now = {t: it(name=t, tier=t, label=t.upper()) for t in tiers}
    assert [r["name"] for r in pair(then, now)["verdict_changes"]] == [
        "could_go",
        "redundant",
        "review",
        "too_early",
        "keep_rare",
        "untracked",
        "off",
    ]


def test_went_quiet_lists_only_newly_quiet_items():
    then = {"a": it(name="a", q=True), "b": it(name="b"), "c": it(name="c")}
    now = {
        "a": it(name="a", q=True),
        "b": it(name="b", q=True),
        "c": it(name="c"),
        "d": it(name="d", q=True),
        "e": it(name="e", kind="agent", q=True),
    }
    got = pair(then, now)["went_quiet"]
    assert got == [{"kind": "agent", "name": "e"}, {"kind": "skill", "name": "b"}, {"kind": "skill", "name": "d"}]


def test_used_most_counts_this_periods_new_uses_only():
    then = {"a": it(name="a", u=10), "b": it(name="b", u=5), "c": it(name="c", u=9), "z": it(name="z", u=4)}
    now = {"a": it(name="a", u=13), "b": it(name="b", u=5), "c": it(name="c", u=2), "d": it(name="d", u=7), "z": it(name="z", u=5)}
    got = pair(then, now)["used_most"]
    assert got == [
        {"kind": "skill", "name": "d", "uses": 7},
        {"kind": "skill", "name": "a", "uses": 3},
        {"kind": "skill", "name": "z", "uses": 1},
    ]


def test_used_most_is_capped_and_ties_break_by_name():
    now = {f"h{n}": it(name=f"n{n}", u=2) for n in range(TOP + 3)}
    got = pair({}, now)["used_most"]
    assert TOP == 5 and [r["name"] for r in got] == ["n0", "n1", "n2", "n3", "n4"]


# ---- the text report ----


def test_render_first_scan_and_full_report():
    first = summarize(snap(NOW, {}), [], TODAY)
    assert weekly.render(first) == f"Weekly state of your setup\n{FIRST}\n"
    then = {"a": it(name="a", u=1, q=False), "gone": it(name="gone")}
    now = {"a": it(name="a", tier="review", label="Review", why="Idle", u=4, q=True, c=300), "new": it(name="new", c=None)}
    r = {"low": 1200, "high": 3400, "unknown": 2, "confidence": "medium"}
    text = weekly.render(summarize(snap(NOW, now, reclaim=r), [snap("2026-10-30", then)], TODAY))
    assert text == (
        "Weekly state of your setup\n"
        "Since 2026-10-30: 1 added, 1 removed; session start 200 to 300 tokens (+100) counting known costs only; 1 went quiet; "
        "you could free 1,200 to 3,400 tokens (was 0).\n"
        "\nAdded (1)\n  skill  new\n"
        "\nRemoved (1)\n  skill  gone\n"
        "\nWent quiet (1)\n  skill  a\n"
        "\nVerdict changes\n  a: Keep -> Review  (Idle)\n"
        "\nUsed most\n  a  3 sessions\n"
        "\nSession start: 200 -> 300 tokens (+100); unknown cost 0 -> 1\n"
        "Reclaimable: 1,200 to 3,400 tokens, medium confidence; was 0\n"
        "  + 2 with unknown cost, not counted\n"
    )


def test_render_plain_no_change_and_not_measured():
    text = weekly.render(pair({"a": it(c=None)}, {"a": it(c=None)}))
    assert text == (
        "Weekly state of your setup\n"
        "Since 2026-10-30: no Items added or removed; session start cost not measured; you could free 0 tokens (was 0).\n"
        "\nSession start: not measured; unknown cost 1 -> 1\n"
        "Reclaimable: 0 tokens, low confidence; was 0\n"
    )


# ---- the sidecar file ----


def test_record_and_load_round_trip_privately(tmp_path):
    path = tmp_path / "cache" / "weekly.json"
    a, b = snap("2026-11-01", {"h": it()}), snap("2026-11-02", {})
    weekly.record(path, a)
    weekly.record(path, b)
    assert weekly.load(path) == [a, b]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600 and stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert json.loads(path.read_text())["v"] == 1
    assert [p.name for p in path.parent.iterdir()] == ["weekly.json"]


@pytest.mark.parametrize("confidence", ["high", "medium", "low"])
def test_each_confidence_is_valid(confidence):
    assert weekly._valid(mutated(**{"reclaim.confidence": confidence}))


def test_record_makes_missing_parents_privately_and_names_its_temp_file(tmp_path, monkeypatch):
    seen = []
    real = os.replace
    monkeypatch.setattr(os, "replace", lambda a, b: (seen.append(a), real(a, b))[1])
    path = tmp_path / "a" / "b" / "w.json"
    weekly.record(path, snap("2026-11-01", {}))
    assert [(os.path.dirname(x), os.path.basename(x).startswith(".weekly-")) for x in seen] == [(str(path.parent), True)]
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_record_warns_when_it_starts_a_corrupt_file_over(tmp_path, capsys):
    path = tmp_path / "w.json"
    path.write_text("{")
    weekly.record(path, snap("2026-11-01", {}))
    assert capsys.readouterr().err == f"weekly history {path} could not be read; starting it over\n"
    assert len(weekly.load(path)) == 1


def test_an_existing_loose_directory_is_tightened(tmp_path):
    (tmp_path / "d").mkdir(mode=0o755)
    os.chmod(tmp_path / "d", 0o755)
    weekly.record(tmp_path / "d" / "w.json", snap("2026-11-01", {}))
    assert stat.S_IMODE((tmp_path / "d").stat().st_mode) == 0o700


def test_record_replaces_the_same_setup_and_day_and_keeps_others(tmp_path):
    path = tmp_path / "w.json"
    for s in (snap("2026-11-01", {"h": it()}), snap("2026-11-01", {}, setup="t"), snap("2026-11-01", {"k": it(name="k")})):
        weekly.record(path, s)
    got = weekly.load(path)
    assert [(s["setup"], list(s["items"])) for s in got] == [("s", ["k"]), ("t", [])]


def test_record_keeps_only_the_newest(tmp_path):
    path = tmp_path / "w.json"
    for n in range(weekly.KEEP + 2):
        weekly.record(path, snap(f"2026-{n // 28 + 1:02d}-{n % 28 + 1:02d}", {}))
    days = [s["date"] for s in weekly.load(path)]
    assert weekly.KEEP == 60 and len(days) == 60 and days == sorted(days) and days[0] == "2026-01-03"


def test_record_failure_removes_its_temp_file_and_keeps_the_old_one(tmp_path, monkeypatch):
    path = tmp_path / "w.json"
    weekly.record(path, snap("2026-11-01", {}))
    monkeypatch.setattr(os, "replace", lambda *a: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError, match=r"^disk$"):
        weekly.record(path, snap("2026-11-02", {}))
    assert [p.name for p in tmp_path.iterdir()] == ["w.json"] and len(weekly.load(path)) == 1


@pytest.mark.parametrize(
    "raw", ["", "{", "[]", "null", '{"v": 2, "snapshots": []}', '{"v": 1}', '{"v": 1, "snapshots": {}}', "\x00", "[" * 100000]
)
def test_a_corrupt_file_is_no_history_and_warns_once_asked(tmp_path, capsys, raw):
    path = tmp_path / "w.json"
    path.write_text(raw)
    assert weekly.load(path) == []
    assert capsys.readouterr().err == ""
    assert weekly.load(path, warn=True) == []
    assert capsys.readouterr().err == f"weekly history {path} could not be read; starting it over\n"


def test_a_directory_in_place_of_the_file_is_no_history(tmp_path):
    assert weekly.load(tmp_path) == []


def test_a_missing_file_is_no_history_and_silent(tmp_path, capsys):
    assert weekly.load(tmp_path / "none.json", warn=True) == []
    assert capsys.readouterr().err == ""


GOOD = snap("2026-11-01", {"h": it(c=None)})


def mutated(**changes):
    out = json.loads(json.dumps(GOOD))
    for path, value in changes.items():
        target = out
        *head, last = path.split(".")
        for p in head:
            target = target[p]
        if value == "DELETE":
            del target[last]
        else:
            target[last] = value
    return out


BAD = [
    mutated(setup=7),
    mutated(date="20261101"),
    mutated(date="2026-13-01"),
    mutated(date=7),
    mutated(items=[]),
    mutated(reclaim=[]),
    {**GOOD, "extra": 1},
    {k: v for k, v in GOOD.items() if k != "reclaim"},
    mutated(**{"items.h": []}),
    mutated(**{"items.h.k": 1}),
    mutated(**{"items.h.n": 1}),
    mutated(**{"items.h.t": 1}),
    mutated(**{"items.h.l": 1}),
    mutated(**{"items.h.w": 1}),
    mutated(**{"items.h.q": 1}),
    mutated(**{"items.h.u": -1}),
    mutated(**{"items.h.u": True}),
    mutated(**{"items.h.u": 1.0}),
    mutated(**{"items.h.c": -1}),
    mutated(**{"items.h.c": "1"}),
    mutated(**{"items.h.c": True}),
    mutated(**{"items.h.extra": 1}),
    mutated(**{"items.h.c": "DELETE"}),
    mutated(**{"reclaim.low": -1}),
    mutated(**{"reclaim.high": None}),
    mutated(**{"reclaim.unknown": 1.5}),
    mutated(**{"reclaim.confidence": "certain"}),
    mutated(**{"reclaim.extra": 1}),
    mutated(**{"reclaim.low": "DELETE"}),
]


@pytest.mark.parametrize("bad", BAD)
def test_invalid_snapshots_are_dropped_and_the_rest_kept(tmp_path, bad):
    path = tmp_path / "w.json"
    path.write_text(json.dumps({"v": 1, "snapshots": [bad, GOOD, "x", None]}))
    assert weekly.load(path) == [GOOD]


def test_good_snapshot_shapes_are_accepted():
    assert weekly._valid(GOOD) and weekly._valid(mutated(**{"items.h.c": 0, "items.h.u": 0, "reclaim.confidence": "high"}))
    assert weekly._valid(mutated(items={}, setup=""))  # an empty setup key or item map is shaped correctly; build() refuses it separately
    assert not weekly._valid(None) and not weekly._valid("x")


# ---- the snapshot taken at scan time ----

DATA = {
    "setup": "s1",
    "scanned_at": "2026-11-06",
    "items": [
        {"id": "p:skill:alpha", "kind": "skill", "name": "alpha", "description": "d"},
        {"id": "p:skill:beta", "kind": "skill", "name": "beta", "description": "d"},
        {"id": "p:skill:gamma", "kind": "skill", "name": "gamma", "description": "d"},
    ],
    "costs": {"p:skill:alpha": {"always_on": 120}, "p:skill:beta": {"always_on": None}},
    "overlaps": [],
    "relations": [],
}


def assessed(active_days=40, ledger=True, **ev):
    a = lambda id_, tier, label, why: Assessment(  # noqa: E731
        id_, tier, label, "high", (Reason("c", why), Reason("d", "second")), "none", None, 1, None, None
    )
    asm = {
        "p:skill:alpha": a("p:skill:alpha", "review", "Review", "Idle a while"),
        "p:skill:beta": a("p:skill:beta", "keep", "Keep", "Used lately"),
        "p:skill:gamma": a("p:skill:gamma", "keep", "Keep", "Fine"),
    }
    items = {
        "p:skill:alpha": ItemEvidence(sessions_used=9, days_used=5, mean_gap=2.0, idle_active_days=7),
        "p:skill:beta": ItemEvidence(sessions_used=0, days_used=0),
    }
    return Assessed(asm, Evidence(30, active_days, 50, 1.0, {}, 0.0, items), ledger)


def test_snapshot_holds_names_tiers_costs_uses_and_the_range():
    found = assessed()
    brief = build_brief(DATA, found.assessments, found.evidence)
    s = weekly.snapshot(DATA, found, brief)
    assert weekly._valid(s)
    assert (s["setup"], s["date"], s["reclaim"]) == ("s1", "2026-11-06", {"low": 0, "high": 0, "unknown": 0, "confidence": "high"})
    by_name = {v["n"]: v for v in s["items"].values()}
    assert by_name["alpha"] == {"k": "skill", "n": "alpha", "t": "review", "l": "Review", "w": "Idle a while", "q": True, "c": 120, "u": 9}
    assert by_name["beta"]["c"] is None and by_name["beta"]["q"] is False and by_name["beta"]["u"] == 0
    assert by_name["gamma"] == {"k": "skill", "n": "gamma", "t": "keep", "l": "Keep", "w": "Fine", "q": False, "c": None, "u": 0}
    assert all(re.fullmatch(r"[0-9a-f]{12}", h) for h in s["items"])
    assert not any("p:skill" in h for h in s["items"])


def test_quiet_needs_a_rhythm_and_more_than_three_gaps_idle():
    ev = lambda **kw: ItemEvidence(sessions_used=3, days_used=3, **kw)  # noqa: E731
    assert weekly._quiet(ev(mean_gap=2.0, idle_active_days=7))
    assert not weekly._quiet(ev(mean_gap=2.0, idle_active_days=6))  # OVERDUE_MULT times the gap is still on time
    assert not weekly._quiet(ev(mean_gap=None, idle_active_days=99))
    assert not weekly._quiet(ev(mean_gap=2.0, idle_active_days=None))


@pytest.mark.parametrize(
    ("days", "ledger", "want"),
    [(13, True, "low"), (14, True, "medium"), (29, True, "medium"), (30, True, "high"), (99, False, "medium"), (5, False, "low")],
)
def test_range_confidence_follows_history_length(days, ledger, want):
    assert weekly._confidence(assessed(active_days=days, ledger=ledger)) == want


def test_range_in_the_snapshot_is_the_briefs_range():
    found = assessed()
    brief = {"range": {"low": 10, "high": 90, "unknown": 2}}
    assert weekly.snapshot(DATA, found, brief)["reclaim"] == {"low": 10, "high": 90, "unknown": 2, "confidence": "high"}


def test_an_item_without_a_cost_entry_is_unknown():
    data = {**DATA, "costs": {}}
    found = assessed()
    assert {v["c"] for v in weekly.snapshot(data, found, build_brief(data, found.assessments, found.evidence))["items"].values()} == {None}
    data = {k: v for k, v in DATA.items() if k != "costs"}
    assert {v["c"] for v in weekly.snapshot(data, found, build_brief(data, found.assessments, found.evidence))["items"].values()} == {None}


def test_build_uses_the_sidecar_and_hides_history_it_cannot_tie_to_a_setup(tmp_path, monkeypatch):
    monkeypatch.setattr("constellation.history._today", lambda: "2026-11-06")
    found = assessed()
    brief = build_brief(DATA, found.assessments, found.evidence)
    path = tmp_path / "w.json"
    assert weekly.build(DATA, found, brief, path)["state"] == "first"
    old = weekly.snapshot({**DATA, "scanned_at": "2026-10-30"}, found, brief)
    weekly.record(path, old)
    got = weekly.build(DATA, found, brief, path)
    assert (got["state"], got["since"]) == ("ready", "2026-10-30")
    assert weekly.build(DATA, found, brief, path, since="2026-10-29")["state"] == "first"
    for broken in ({"setup": None}, {"scanned_at": None}, {"scanned_at": "soon"}):
        assert weekly.build({**DATA, **broken}, found, brief, path) == {"state": "first", "headline": FIRST}


def test_build_defaults_to_the_default_cache(tmp_path, monkeypatch):
    monkeypatch.setattr("constellation.history._today", lambda: "2026-11-06")
    found = assessed()
    brief = build_brief(DATA, found.assessments, found.evidence)
    weekly.record(weekly.DEFAULT_CACHE, weekly.snapshot({**DATA, "scanned_at": "2026-11-01"}, found, brief))
    assert weekly.build(DATA, found, brief)["since"] == "2026-11-01"


def test_record_scan_writes_a_snapshot_and_never_raises(tmp_path, monkeypatch):
    path = tmp_path / "w.json"
    assert weekly.record_scan(DATA, path) == []
    assert [s["date"] for s in weekly.load(path)] == ["2026-11-06"]
    assert weekly.record_scan({"items": 3}, path) != []
    warnings = weekly.record_scan({**DATA, "items": [{"id": "x"}]}, path)
    assert re.fullmatch(r"^could not save the weekly snapshot: .*$", warnings[0])


def test_record_scan_defaults_to_the_default_cache():
    assert weekly.record_scan(DATA) == []
    assert len(weekly.load(weekly.DEFAULT_CACHE)) == 1


def test_record_scan_reports_an_unwritable_file_as_a_warning(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    got = weekly.record_scan(DATA, blocker / "w.json")
    assert len(got) == 1 and got[0].startswith("could not save the weekly snapshot: ")
