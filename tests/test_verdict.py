import json
from dataclasses import asdict, replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from constellation import verdict as v
from constellation.verdict_types import Evidence, Habits, ItemEvidence, ItemHabits

FIX = Path(__file__).parent / "fixtures" / "assess"
TODAY = date(2026, 11, 5)


def load() -> tuple[dict[str, Any], Evidence, Habits]:
    setup = json.loads((FIX / "setup.json").read_text())
    raw = setup["evidence"]
    ev = Evidence(
        **{
            **raw,
            "projects": {k: tuple(x) for k, x in raw["projects"].items()},
            "items": {k: ItemEvidence(**x) for k, x in raw["items"].items()},
        }
    )
    habits = Habits(
        active_days=34,
        projects_active=5,
        items={
            "git-helper": ItemHabits(decayed_use=30.0, all_time=41, projects_used=5, top_project_share=0.4),
            "release-notes": ItemHabits(decayed_use=2.4, all_time=3),
            "repo-map": ItemHabits(decayed_use=7.0, all_time=9, projects_used=1, top_project_share=1.0),
        },
    )
    return setup, ev, habits


def as_json(assessments: dict[str, Any]) -> list[Any]:
    return json.loads(json.dumps([asdict(a) for a in assessments.values()]))


def test_assess_reproduces_expected_json() -> None:
    setup, ev, habits = load()
    got = v.assess(setup, ev, habits, frozenset(), TODAY)
    expected = json.loads((FIX / "expected.json").read_text())
    assert as_json(got) == expected["assessments"]
    assert v.totals(got) == {**expected["brief"]["range"], "safe_saves": 990, "look_saves": 2710}


def test_every_fixture_item_has_one_to_three_short_reasons() -> None:
    setup, ev, habits = load()
    for a in v.assess(setup, ev, habits, frozenset(), TODAY).values():
        assert 1 <= len(a.reasons) <= 3
        assert all(len(r.text) <= 90 for r in a.reasons)
        assert a.saves != 0


def test_fixture_evidence_builder_matches_given_derived_fields() -> None:
    setup, ev, habits = load()
    built = v.evidence(setup, habits, replace(ev, items={}))
    assert built.items["quarterly-report"].purpose_class == "rare"
    assert built.items["release-notes"].purpose_class == "rare"
    assert built.items["scratch-notes"].vague is True
    assert built.items["git-helper"].count == 41
    assert all(i.referenced_by == () for i in built.items.values())


# --- small builders -------------------------------------------------------------------------------------------------


def item(
    name: str, kind: str = "skill", cost: int | None = 400, desc: str = "Use when you need to do the specific thing here now", **more: Any
) -> dict[str, Any]:
    return {"id": f"x:{kind}:{name}", "kind": kind, "name": name, "description": desc, "origin": "pack", "always_on": cost, **more}


def run(
    items: list[dict[str, Any]], per: dict[str, ItemEvidence] | None = None, *, days: int = 40, sessions: int = 60, skipped: float = 0.0,
    habits: dict[str, ItemHabits] | None = None, pins: frozenset[str] = frozenset(), **data: Any,
) -> dict[str, Any]:  # fmt: skip
    ev = Evidence(sessions, days, days, 1.5, {}, skipped, per or {})
    return v.assess({"items": items, **data}, ev, Habits(days, 5, habits or {}), pins, TODAY)


def one(a: dict[str, Any], name: str, kind: str = "skill") -> Any:
    return a[f"x:{kind}:{name}"]


# --- pure helpers ---------------------------------------------------------------------------------------------------


def test_purpose_class_whole_words() -> None:
    assert v.purpose_class("drafts the release notes", "x") == "rare"
    assert v.purpose_class("a released thing", "x") == "everyday"
    assert v.purpose_class("sets up", "quarterly-thing") == "rare"
    assert v.purpose_class("start a new project", "x") == "occasional"
    assert v.purpose_class("deploys", "x") == "everyday"
    assert v.purpose_cue("Release then deploy", "x") == ("rare", "release")
    assert v.purpose_cue("RELEASE", "x") == ("rare", "release")
    assert v.purpose_cue("nothing here", "x") == ("everyday", None)
    assert v.purpose_class("check the audit", "x") == "rare"
    assert v.purpose_class("run a benchmark", "x") == "occasional"


def test_specificity_boundary() -> None:
    assert v.specificity("a b c d e f g") == (7, True)
    assert v.specificity("a b c d e f g h") == (8, False)
    assert v.specificity("") == (0, True)


def test_referenced_by() -> None:
    a, b = item("alpha"), item("beta", desc="Calls alpha when needed, never alphabet")
    data = {"items": [a, b, item("gamma", desc="uses alpha-two"), item("off", desc="alpha", disabled=True)]}
    assert v.referenced_by(a, data) == ("beta",)
    wrapped = {"items": [a, item("w")], "overlaps": [{"a": "w", "b": "alpha", "verdict": "wrapper"}]}
    assert v.referenced_by(a, wrapped) == ("w",)
    assert v.referenced_by(item("w"), wrapped) == ()
    assert v.referenced_by(a, {"items": [a]}) == ()
    reversed_wrap = {"items": [a, item("w")], "overlaps": [{"a": "alpha", "b": "w", "verdict": "wrapper"}]}
    assert v.referenced_by(a, reversed_wrap) == ()
    other = {"items": [a, item("w")], "overlaps": [{"a": "w", "b": "alpha", "verdict": "duplicate"}]}
    assert v.referenced_by(a, other) == ()


def test_clip_boundary() -> None:
    assert v.clip("x" * 90) == "x" * 90
    assert len(v.clip("x" * 91)) == 90


# --- NEED thresholds: n-1 and n ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cls", "days", "sessions", "want"),
    [
        ("everyday", 9, 99, None), ("everyday", 10, 14, None), ("everyday", 10, 15, "medium"), ("everyday", 24, 99, "medium"),
        ("everyday", 25, 39, "medium"), ("everyday", 25, 40, "high"),
        ("occasional", 29, 99, None), ("occasional", 30, 0, "medium"), ("occasional", 59, 99, "medium"), ("occasional", 60, 0, "high"),
        ("rare", 89, 99, None), ("rare", 90, 0, "medium"), ("rare", 500, 500, "medium"),
    ],
)  # fmt: skip
def test_need_confidence(cls: str, days: int, sessions: int, want: str | None) -> None:
    assert v.need_confidence(cls, days, sessions) == want


@pytest.mark.parametrize(("days", "want"), [(9, "too_early"), (10, "could_go")])
def test_never_seen_exposure_edge(days: int, want: str) -> None:
    assert one(run([item("a")], days=days, sessions=20), "a").tier == want


@pytest.mark.parametrize(("sessions", "want"), [(14, "too_early"), (15, "could_go")])
def test_never_seen_session_edge(sessions: int, want: str) -> None:
    assert one(run([item("a")], days=12, sessions=sessions), "a").tier == want


def test_never_seen_confidence_high_edges() -> None:
    assert one(run([item("a")], days=24, sessions=99), "a").confidence == "medium"
    assert one(run([item("a")], days=25, sessions=39), "a").confidence == "medium"
    assert one(run([item("a")], days=25, sessions=40), "a").confidence == "high"


def test_rare_and_occasional_never_seen() -> None:
    rare = {"a": ItemEvidence(purpose_class="rare")}
    early = one(run([item("a")], rare, days=89), "a")
    assert (early.tier, early.confidence, early.group, early.recheck_after) == ("keep_rare", "low", "wait", 1)
    late = one(run([item("a")], rare, days=90), "a")
    assert (late.tier, late.confidence) == ("could_go", "medium")
    occ = {"a": ItemEvidence(purpose_class="occasional")}
    assert one(run([item("a")], occ, days=29), "a").tier == "too_early"
    assert one(run([item("a")], occ, days=30), "a").confidence == "medium"
    assert one(run([item("a")], occ, days=60), "a").confidence == "high"


def test_too_early_texts_and_recheck() -> None:
    a = one(run([item("a")], days=6, sessions=8), "a")
    assert a.reasons[0].text == "Only 8 sessions over 6 active days; check back after ~5 more"
    assert a.recheck_after == 5  # 10 days needed (4 more) but 15 sessions at 1.5 a day (5 more)
    assert one(run([item("a")], days=1, sessions=1), "a").reasons[0].text == "Only 1 session over 1 active day; check back after ~10 more"
    assert one(run([item("a")], days=0, sessions=0), "a").reasons[0].text == "No session history yet"
    # enough days, too few sessions: sessions at 1.5 per day decide (ceil(5 / 1.5) = 4)
    assert one(run([item("a")], days=12, sessions=10), "a").recheck_after == 4
    assert one(run([item("a")], days=12, sessions=14), "a").recheck_after == 1


def test_cost_floor_edge() -> None:
    assert one(run([item("a", cost=49)]), "a").tier == "review"
    assert one(run([item("a", cost=49)]), "a").reasons[0].code == "costs_little"
    assert one(run([item("a", cost=50)]), "a").tier == "could_go"
    unknown = one(run([item("a", cost=None)]), "a")
    assert (unknown.tier, unknown.saves, unknown.reasons[0].text) == ("review", None, "Not used, and its cost is unknown; no rush")
    assert one(run([item("a", cost=49)]), "a").reasons[0].text == "Not used, but costs little; no rush"


def test_vague_review_after_exposure() -> None:
    per = {"a": ItemEvidence(vague=True)}
    assert one(run([item("a", desc="notes helper")], per, days=9), "a").tier == "too_early"
    got = one(run([item("a", desc="notes helper")], per, days=10, sessions=20), "a")
    assert (got.action, got.confidence, got.group, got.saves) == ("fix_description", "low", "look", 400)
    assert one(run([item("a", desc="one")], per), "a").reasons[0].text == "Its description is 1 word, so Claude may never pick it"


# --- grace ---------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("first", "tier"), [("2026-10-22", "too_early"), ("2026-10-21", "could_go")])
def test_grace_edge(first: str, tier: str) -> None:
    assert one(run([item("a")], {"a": ItemEvidence(first_seen=first)}), "a").tier == tier


def test_grace_texts() -> None:
    r = lambda **k: one(run([item("a")], {"a": ItemEvidence(**k)}), "a").reasons[0].text  # noqa: E731
    assert r(first_seen="2026-11-05") == "Added today"
    assert r(first_seen="2026-11-04") == "Added 1 day ago"
    assert r(first_seen="2026-10-30", changed_on="2026-11-03") == "Changed 2 days ago"
    assert r(first_seen="2026-11-03", changed_on="2026-10-30") == "Added 2 days ago"
    assert r(first_seen="2026-10-01", changed_on="2026-11-01") == "Changed 4 days ago"
    assert one(run([item("a")], {"a": ItemEvidence(first_seen="2026-11-06")}), "a").tier == "could_go"  # future day ignored
    used = ItemEvidence(count=5, sessions_used=5, changed_on="2026-11-01")
    assert one(run([item("a")], {"a": used}), "a").tier == "too_early"


# --- used ----------------------------------------------------------------------------------------------------------


def used(**k: Any) -> dict[str, ItemEvidence]:
    return {"a": ItemEvidence(**{"count": 6, "sessions_used": 6, "days_used": 6, **k})}


@pytest.mark.parametrize(("idle", "tier"), [(29, "keep"), (30, "review")])
def test_stale_idle_edge(idle: int, tier: str) -> None:
    assert one(run([item("a")], used(idle_active_days=idle)), "a").tier == tier


@pytest.mark.parametrize(("idle", "tier"), [(29, "keep"), (30, "review")])
def test_stale_with_short_gap(idle: int, tier: str) -> None:
    assert one(run([item("a")], used(idle_active_days=idle, mean_gap=9.0)), "a").tier == tier


@pytest.mark.parametrize(("idle", "tier"), [(59, "keep"), (60, "review")])
def test_stale_scales_with_gap(idle: int, tier: str) -> None:
    assert one(run([item("a")], used(idle_active_days=idle, mean_gap=20.0)), "a").tier == tier


@pytest.mark.parametrize(("days", "tier"), [(29, "keep"), (30, "review")])
def test_stale_needs_exposure(days: int, tier: str) -> None:
    assert one(run([item("a")], used(idle_active_days=40), days=days), "a").tier == tier


def test_stale_texts() -> None:
    plain = one(run([item("a")], used(idle_active_days=40)), "a")
    assert (plain.reasons[0].code, plain.reasons[0].text, plain.action, plain.saves) == (
        "stale",
        "Not used in 40 active days",
        "remove",
        400,
    )
    assert plain.confidence == "medium"
    fading = one(run([item("a")], used(idle_active_days=40, mean_gap=4.0, trend="fading")), "a")
    assert (fading.reasons[0].code, fading.reasons[0].text) == ("fading", "Not used in 40 active days; you used it about every 4 before")


@pytest.mark.parametrize(("count", "share", "tier"), [(2, 1.0, "keep"), (3, 0.79, "keep"), (3, 0.8, "review")])
def test_move_edges(count: int, share: float, tier: str) -> None:
    got = one(run([item("a")], used(count=count), habits={"a": ItemHabits(top_project_share=share)}), "a")
    assert got.tier == tier


def test_move_texts_and_scope() -> None:
    h = {"a": ItemHabits(top_project_share=0.9)}
    got = one(run([item("a")], used(), habits=h), "a")
    assert (got.action, got.reasons[0].text) == ("move_to_project", "Used 6 times, mostly in one repo; move it there to save 400 elsewhere")
    assert one(run([item("a", cost=None)], used(), habits=h), "a").reasons[0].text == "Used 6 times, mostly in one repo; move it there"
    assert one(run([item("a", scope="project")], used(), habits=h), "a").tier == "keep"


@pytest.mark.parametrize(("pct", "tier"), [(11, "keep"), (10, "review")])
def test_bottom_edge(pct: int, tier: str) -> None:
    got = one(run([item("a")], used(percentile=pct, trend="fading")), "a")
    assert got.tier == tier
    if tier == "review":
        assert (got.confidence, got.action, got.group) == ("low", "none", "wait")
    assert one(run([item("a")], used(percentile=pct, trend="steady")), "a").tier == "keep"
    assert one(run([item("a")], used(percentile=None, trend="fading")), "a").tier == "keep"


def test_keep_confidence_and_texts() -> None:
    assert one(run([item("a")], used(sessions_used=14)), "a").confidence == "medium"
    assert one(run([item("a")], used(sessions_used=15)), "a").confidence == "high"
    h = {"a": ItemHabits(projects_used=2)}
    assert one(run([item("a")], used(percentile=89), habits=h), "a").reasons[0].text == "Used 6 times in 2 of 5 projects"
    assert one(run([item("a")], used(percentile=90), habits=h), "a").reasons[0].text == "Used 6 times in 2 of 5 projects; in your top 10%"
    assert one(run([item("a")], used(percentile=95)), "a").reasons[0].text == "Used 6 times; in your top 5%"
    keep = one(run([item("a")], used()), "a")
    assert (keep.action, keep.saves, keep.group, keep.risk, keep.label) == ("none", None, None, 1, "Keep")


def test_rare_used_is_keep_rare_labelled_keep() -> None:
    got = one(run([item("a", desc="drafts the quarterly summary")], used(purpose_class="rare")), "a")
    assert (got.tier, got.label, got.group, got.reasons[0].text) == ("keep_rare", "Keep", None, "Used 6 times; made for quarterly work")
    assert one(run([item("a")], used(purpose_class="rare")), "a").reasons[0].text == "Used 6 times; made for occasional work"


# --- redundancy ----------------------------------------------------------------------------------------------------


def twins(
    a_use: int, b_use: int, a_dec: float, b_dec: float, a_cost: int = 400, b_cost: int = 400, **k: Any
) -> dict[str, Any]:  # fmt: skip
    per = {"a": ItemEvidence(count=a_use), "b": ItemEvidence(count=b_use)}
    hab = {"a": ItemHabits(decayed_use=a_dec), "b": ItemHabits(decayed_use=b_dec)}
    return run(
        [item("a", cost=a_cost), item("b", cost=b_cost)], per, habits=hab, overlaps=[{"a": "a", "b": "b", "verdict": "duplicate"}], **k
    )  # fmt: skip


def test_loser_is_less_used_then_more_expensive_then_id() -> None:
    assert one(twins(0, 5, 0.0, 3.0), "a").tier == "redundant"
    assert one(twins(5, 0, 3.0, 0.0), "b").tier == "redundant"
    assert one(twins(0, 0, 1.0, 1.0, a_cost=100, b_cost=200), "b").tier == "redundant"
    assert one(twins(0, 0, 1.0, 1.0, a_cost=200, b_cost=100), "a").tier == "redundant"
    assert one(twins(0, 0, 1.0, 1.0), "a").tier == "redundant"  # tie on all: smaller id goes
    assert one(twins(0, 0, 1.0, 1.0, a_cost=200, b_cost=100), "b").tier != "redundant"
    assert one(twins(0, 0, 1.0, 1.0, a_cost=200, b_cost=200), "b").tier != "redundant"
    unknown = run([item("a", cost=None), item("b", cost=10)], overlaps=[{"a": "a", "b": "b", "verdict": "duplicate"}])
    assert one(unknown, "b").tier == "redundant"


def test_pinned_twin_never_loses() -> None:
    pins = frozenset({"x:skill:a"})
    got = twins(0, 5, 0.0, 3.0, pins=pins)
    assert (one(got, "a").tier, one(got, "b").tier) == ("keep", "redundant")
    both = twins(0, 0, 0.0, 0.0, pins=frozenset({"x:skill:a", "x:skill:b"}))
    assert (one(both, "a").tier, one(both, "b").tier) == ("keep", "keep")
    flagged = run([item("a"), item("b")], {"a": ItemEvidence(pinned=True)}, overlaps=[{"a": "a", "b": "b", "verdict": "duplicate"}])
    assert one(flagged, "a").reasons[0].code == "pinned"
    assert one(flagged, "b").tier == "redundant"


def test_loser_reasons_and_confidence() -> None:
    clear = one(twins(0, 3, 0.0, 2.0), "a")
    assert (clear.confidence, clear.reasons[0].text) == ("high", "Does the same job as b; you used that 3 times, this one never")
    assert (clear.action, clear.saves, clear.group) == ("remove_twin", 400, "safe")
    short = one(twins(0, 3, 0.0, 2.0, days=9), "a")
    assert short.confidence == "medium"
    neither = one(twins(0, 0, 0.0, 0.0), "a")
    assert (neither.confidence, neither.reasons[0].text) == ("medium", "Does the same job as b; neither has been used")
    lesser = one(twins(2, 9, 0.5, 4.0), "a")
    assert (lesser.confidence, lesser.reasons[0].text) == ("medium", "Does the same job as b, which you use more (9 vs 2 times)")
    assert one(twins(0, 3, 0.0, 2.0, skipped=0.06), "a").confidence == "medium"
    assert one(twins(0, 3, 0.0, 2.0, skipped=0.05), "a").confidence == "high"
    assert one(twins(0, 3, 0.0, 2.0, sessions=14), "a").confidence == "low"


def test_twin_winner_and_both_used() -> None:
    win = one(twins(0, 0, 3.0, 0.0), "a")
    assert (win.tier, win.reasons[0].text) == ("keep", "Its twin b could go")
    per = {"a": ItemEvidence(count=4, percentile=50), "b": ItemEvidence(count=9, percentile=80)}
    hab = {"a": ItemHabits(decayed_use=1.0), "b": ItemHabits(decayed_use=4.0)}
    got = run([item("a"), item("b")], per, habits=hab, overlaps=[{"a": "a", "b": "b", "verdict": "duplicate"}])
    assert (one(got, "a").tier, one(got, "a").reasons[0].text) == ("review", "b does the same job and you use both")
    per["a"] = ItemEvidence(count=4, percentile=49)
    low = run([item("a"), item("b")], per, habits=hab, overlaps=[{"a": "a", "b": "b", "verdict": "duplicate"}])
    assert one(low, "a").tier == "redundant"


def test_wrapper() -> None:
    link = [{"a": "w", "b": "t", "verdict": "wrapper"}]
    items = [item("w"), item("t")]
    dead = run(items, overlaps=link)
    assert (one(dead, "w").tier, one(dead, "w").action, one(dead, "w").reasons[0].text) == (
        "redundant",
        "use_underlying",
        "Only hands off to t",
    )
    assert one(dead, "w").confidence == "high"
    assert one(run(items, overlaps=link, days=9), "w").confidence == "medium"
    reach = run(items, {"w": ItemEvidence(count=4, sessions_used=4)}, overlaps=link)
    assert (one(reach, "w").tier, one(reach, "w").reasons[0].text) == ("keep", "You reach t through it")
    assert (one(reach, "t").tier, one(reach, "t").reasons[0].text) == ("keep", "w calls it")
    both = run(items, {"w": ItemEvidence(count=4), "t": ItemEvidence(count=2)}, overlaps=link)
    assert one(both, "w").tier == "redundant"
    assert one(both, "t").tier == "keep"
    used_wrapped = run(items, {"t": ItemEvidence(count=2, sessions_used=2)}, overlaps=link)
    assert one(used_wrapped, "t").tier == "keep"


def test_overlap_partner_used() -> None:
    link = [{"a": "a", "b": "b", "verdict": "overlap"}]
    per = {"b": ItemEvidence(count=9, sessions_used=9, percentile=50)}
    got = run([item("a"), item("b")], per, overlaps=link)
    assert (one(got, "a").tier, one(got, "a").confidence, one(got, "a").reasons[0].text) == ("redundant", "medium", "You use b for this")
    flipped = run([item("a"), item("b")], {"a": ItemEvidence()} | {"b": per["b"]}, overlaps=[{"a": "b", "b": "a", "verdict": "overlap"}])
    assert one(flipped, "a").tier == "redundant"
    per["b"] = ItemEvidence(count=9, percentile=49)
    assert one(run([item("a"), item("b")], per, overlaps=link), "a").tier == "could_go"
    per["b"] = ItemEvidence(count=0, percentile=99)
    assert one(run([item("a"), item("b")], per, overlaps=link), "a").tier == "could_go"
    per["b"] = ItemEvidence(count=9, percentile=None)
    assert one(run([item("a"), item("b")], per, overlaps=link), "a").tier == "could_go"


def test_shadowed_mcp() -> None:
    conflict = [{"kind": "mcp_name", "ids": ["s"], "detail": "user copy shadowed by project scope"}]
    got = one(run([item("s", "mcp_server", None)], conflicts=conflict), "s", "mcp_server")
    assert (got.tier, got.confidence, got.saves, got.group) == ("redundant", "high", None, "look")
    assert got.reasons[0].text == "Never loaded: the project server with this name wins"
    plain = [{"kind": "mcp_name", "ids": ["s"], "detail": "x"}]
    assert "the local server" in one(run([item("s", "mcp_server", None)], conflicts=plain), "s", "mcp_server").reasons[0].text
    assert (
        one(run([item("s", "mcp_server", None)], conflicts=[{"kind": "mcp_name", "ids": ["z"], "detail": "x"}]), "s", "mcp_server").tier
        != "redundant"
    )
    assert one(run([item("s")], conflicts=conflict), "s").tier != "redundant"  # only MCP servers
    assert (
        one(run([item("s", "mcp_server", None)], conflicts=[{"kind": "trigger", "ids": ["s"], "detail": "x"}]), "s", "mcp_server").tier
        != "redundant"
    )


# --- off, pinned, untracked, guards --------------------------------------------------------------------------------


def test_off_and_pinned() -> None:
    off = one(run([item("a", disabled=True)]), "a")
    assert (off.tier, off.confidence, off.group, off.saves, off.label) == ("off", None, None, None, "Switched off")
    pinned = one(run([item("a")], pins=frozenset({"x:skill:a"})), "a")
    assert (pinned.tier, pinned.confidence, pinned.reasons[0].text, pinned.group) == ("keep", "high", "You pinned it.", None)


def test_untracked_kinds() -> None:
    hook = lambda name, **d: one(run([item(name, "hook", None)], **d), name, "hook").reasons[0].text  # noqa: E731
    assert hook("UserPromptSubmit:*", hook_bytes={"UserPromptSubmit:*": 1000}) == "Adds 1.0 KB before every prompt"
    assert hook("UserPromptSubmit:*", hook_bytes={"UserPromptSubmit:*": 999}) == "Adds 999 bytes before every prompt"
    assert hook("SessionStart:*", hook_bytes={"SessionStart:*": 2000}) == "Adds 2.0 KB at every session start"
    assert hook("Stop:*", hook_bytes={"Stop:*": 2000}) == "Adds 2.0 KB on every Stop"
    assert hook("Stop:*") == "Not judged from usage; its cost is unknown"
    cmd = one(run([item("c", "command", None)]), "c", "command")
    assert (cmd.tier, cmd.confidence, cmd.group, cmd.action) == ("untracked", None, "wait", "none")
    bare = one(run([item("p", "plugin", 900)]), "p", "plugin")
    assert bare.tier == "untracked"
    counted = one(run([item("p", "plugin", 900)], plugin_children={"p": 2}), "p", "plugin")
    assert counted.tier == "could_go"


def test_blast_radius_guard() -> None:
    per = {"a": ItemEvidence(referenced_by=("deploy-flow",))}
    got = one(run([item("a")], per), "a")
    assert (got.tier, got.action, got.saves, got.group, got.confidence) == ("review", "none", None, "wait", "medium")
    assert got.reasons[0].text == "deploy-flow calls it"
    assert len(got.reasons) == 2
    low = one(run([item("a", cost=49)], per), "a")  # already review: untouched
    assert low.reasons[0].code == "costs_little"
    kept = one(run([item("a")], {"a": ItemEvidence(referenced_by=("z",), count=3, sessions_used=3)}), "a")
    assert kept.tier == "keep"
    twin = twins(0, 3, 0.0, 2.0)
    assert one(twin, "a").tier == "redundant"


def test_trigger_conflict() -> None:
    conflict = [{"kind": "trigger", "ids": ["a", "b"]}]
    seen = one(run([item("a")], used(), conflicts=conflict), "a")
    assert seen.tier == "keep" and seen.reasons[-1].code == "trigger_conflict" and len(seen.reasons) == 2
    never = one(run([item("a")], conflicts=conflict), "a")
    assert never.tier == "could_go" and never.reasons[-1].code == "trigger_conflict"
    other = one(run([item("a")], conflicts=[{"kind": "trigger", "ids": ["z"], "detail": "x"}]), "a")
    assert len(other.reasons) == 1
    wrong_kind = one(run([item("a")], conflicts=[{"kind": "mcp_name", "ids": ["a"]}]), "a")
    assert len(wrong_kind.reasons) == 1
    # a kept Item that was never seen only exists as a twin winner
    win = twins(0, 0, 3.0, 0.0, conflicts=[{"kind": "trigger", "ids": ["a"]}])
    assert one(win, "a").tier == "review"


def test_confidence_penalties() -> None:
    hand = item("a", origin=None)
    assert one(run([hand]), "a").confidence == "medium"  # hand-written, no twin
    assert one(run([hand], days=25, sessions=40), "a").confidence == "medium"
    assert one(run([item("a")], days=25, sessions=40, skipped=0.06), "a").confidence == "medium"
    assert one(run([item("a")], days=25, sessions=40, skipped=0.05), "a").confidence == "high"
    assert one(run([item("a")], days=25, sessions=40, skipped=0.06), "a").risk == 2
    assert one(run([hand], days=25, sessions=40, skipped=0.06), "a").confidence == "low"
    assert one(run([item("a")], days=10, sessions=14), "a").tier == "too_early"
    assert one(run([item("a")], per={"a": ItemEvidence(purpose_class="occasional")}, days=30, sessions=14), "a").confidence == "low"
    assert one(run([item("a")], per={"a": ItemEvidence(purpose_class="occasional")}, days=30, sessions=15), "a").confidence == "medium"


def test_risk_and_group() -> None:
    assert one(run([item("a")], days=25, sessions=40), "a").risk == 1
    assert one(run([item("a", origin=None)], days=25, sessions=40), "a").risk == 2
    low = one(run([item("a", origin=None, desc="x")], {"a": ItemEvidence(vague=True)}), "a")
    assert (low.confidence, low.risk) == ("low", 2)
    assert one(run([item("a", cost=49)]), "a").risk == 1
    safe_edge = run([item("a", cost=50)], days=25, sessions=40)
    assert one(safe_edge, "a").group == "safe"
    assert one(run([item("a", cost=50)], days=24, sessions=40), "a").group == "look"
    assert v._group("could_go", "remove", "high", 49, False) == "look"
    assert v._group("review", "none", "low", None, False) == "wait"
    assert v._group("keep_rare", "none", "low", None, True) is None
    assert v._group("keep_rare", "none", "low", None, False) == "wait"


# --- plugins -------------------------------------------------------------------------------------------------------


def plugin_setup(counts: tuple[int, int, int], **k: Any) -> dict[str, Any]:
    kids = [item(f"k{i}", cost=300, plugin="p") for i in range(3)]
    per = {f"k{i}": ItemEvidence(count=c, sessions_used=c) for i, c in enumerate(counts)}
    return run([item("p", "plugin", 1000), *kids], per, plugin_children={"p": 3}, **k)


def test_plugin_none_used_rolls_up() -> None:
    got = plugin_setup((0, 0, 0))
    p = one(got, "p", "plugin")
    assert (p.tier, p.action, p.saves, p.confidence, p.group) == ("could_go", "disable_plugin", 1000, "medium", "look")
    assert p.reasons[0].text == "None of its 3 skills used in 40 active days; turning it off saves 1,000"
    kid = one(got, "k0")
    assert (kid.tier, kid.action, kid.saves, kid.reasons[0].text) == ("review", "none", None, "Part of p")


def test_plugin_sums_children_when_it_has_no_own_cost() -> None:
    kids = [item(f"k{i}", cost=300, plugin="p") for i in range(2)]
    got = run([item("p", "plugin", None), *kids], plugin_children={"p": 2})
    p = one(got, "p", "plugin")
    assert (p.saves, p.reasons[0].text) == (600, "None of its 2 skills used in 40 active days; turning it off saves 600")
    free = run([item("p", "plugin", None), item("k", cost=None, plugin="p")])
    assert one(free, "p", "plugin").reasons[0].code == "children_unclear"  # the child "costs little", so nothing says remove


def test_plugin_one_used_keeps() -> None:
    got = plugin_setup((4, 0, 0))
    p = one(got, "p", "plugin")
    assert (p.tier, p.action, p.saves, p.group) == ("keep", "none", None, None)
    assert p.reasons[0].text == "You use 1 of its 3 skills (k0)."
    assert p.reasons[1].text == "The other 2 cost 600 tokens; the plugin can't be split"
    assert one(got, "k1").tier == "review"
    all_used = one(plugin_setup((1, 1, 1)), "p", "plugin")
    assert len(all_used.reasons) == 1


def test_plugin_some_too_new_waits() -> None:
    kids = [item("k0", cost=300, plugin="p"), item("k1", cost=300, plugin="p")]
    per = {"k1": ItemEvidence(first_seen="2026-11-01")}
    got = run([item("p", "plugin", 1000), *kids], per)
    p = one(got, "p", "plugin")
    assert (p.tier, p.confidence, p.group, p.reasons[0].code) == ("review", "low", "wait", "children_unclear")
    assert one(got, "k0").reasons[0].text == "Part of p"


def test_plugin_own_early_verdict_is_kept() -> None:
    got = run([item("p", "plugin", 1000)], plugin_children={"p": 3}, days=5, sessions=5)
    assert one(got, "p", "plugin").tier == "too_early"


def test_plugin_child_low_confidence_lowers_plugin() -> None:
    kids = [item("k0", cost=300, plugin="p", origin=None, desc="x")]
    got = run([item("p", "plugin", 1000), *kids], {"k0": ItemEvidence(vague=False)}, days=25, sessions=40, skipped=0.06)
    assert one(got, "p", "plugin").confidence == "low"


def test_monotonic_in_active_days() -> None:
    order = ["too_early", "review", "could_go"]
    last = -1
    for days in (0, 5, 9, 10, 20, 30, 60, 120):
        tier = one(run([item("a")], days=days, sessions=days * 2), "a").tier
        assert order.index(tier) >= last
        last = order.index(tier)


def test_evidence_builder_fills_derived_fields() -> None:
    a = item("a", desc="drafts the quarterly summary for the finance team every period")
    data = {"items": [a, item("b", desc="mentions a plainly")]}
    base = Evidence(3, 3, 3, 1.0, {}, 0.0, {"a": ItemEvidence(sessions_used=2, days_used=1)})
    habits = Habits(3, 1, {"a": ItemHabits(all_time=7, trend="rising", percentile=60)})
    built = v.evidence(data, habits, base, frozenset({a["id"]}))
    ia = built.items["a"]
    assert (ia.purpose_class, ia.vague, ia.always_on, ia.pinned, ia.referenced_by) == ("rare", False, 400, True, ("b",))
    assert (ia.count, ia.trend, ia.percentile, ia.sessions_used, ia.days_used) == (7, "rising", 60, 2, 1)
    ib = built.items["b"]
    assert (ib.count, ib.pinned, ib.vague, ib.referenced_by) == (0, False, True, ())
    assert built.sessions == 3


def test_totals() -> None:
    shadow = [{"kind": "mcp_name", "ids": ["b"], "detail": "x"}]
    got = run(
        [item("a", cost=300), item("b", "mcp_server", None), item("c", cost=200)],
        {"c": ItemEvidence(vague=True)},
        days=25,
        sessions=40,
        conflicts=shadow,
    )
    assert v.totals(got) == {"low": 300, "high": 500, "unknown": 1, "safe_saves": 300, "look_saves": 200}


# --- exact shapes of every path (kills code, label, risk, group and text mutants) -------------------------------------


def shape(a: Any) -> tuple[Any, ...]:
    return (a.tier, a.label, a.confidence, a.reasons[0].code, a.action, a.risk, a.group, a.saves, a.recheck_after, a.reasons[0].text)


def test_exact_shapes() -> None:
    link = lambda verdict: [{"a": "a", "b": "b", "verdict": verdict}]  # noqa: E731
    per = {"a": ItemEvidence(count=4, percentile=50), "b": ItemEvidence(count=9, percentile=80)}
    hab = {"a": ItemHabits(decayed_use=1.0), "b": ItemHabits(decayed_use=4.0)}
    got = run([item("a"), item("b")], per, habits=hab, overlaps=link("duplicate"))
    assert shape(one(got, "a")) == (
        "review",
        "Review",
        "medium",
        "twin_both_used",
        "none",
        1,
        "wait",
        None,
        None,
        "b does the same job and you use both",
    )
    assert shape(one(twins(0, 3, 0.0, 2.0), "a")) == (
        "redundant", "Likely redundant", "high", "duplicate_loser", "remove_twin", 1, "safe", 400, None,
        "Does the same job as b; you used that 3 times, this one never",
    )  # fmt: skip
    hand = run(
        [item("a", origin=None), item("b")],
        {"b": ItemEvidence(count=3)},
        habits={"b": ItemHabits(decayed_use=2.0)},
        overlaps=link("duplicate"),
    )
    assert one(hand, "a").risk == 1  # a twin stays, so removing it can be undone
    assert shape(one(twins(0, 0, 3.0, 0.0), "a")) == (
        "keep",
        "Keep",
        "medium",
        "twin_loser",
        "none",
        1,
        None,
        None,
        None,
        "Its twin b could go",
    )
    dead = run([item("w"), item("t")], overlaps=[{"a": "w", "b": "t", "verdict": "wrapper"}])
    assert shape(one(dead, "w")) == (
        "redundant",
        "Likely redundant",
        "high",
        "wrapper",
        "use_underlying",
        1,
        "safe",
        400,
        None,
        "Only hands off to t",
    )
    handw = run([item("w", origin=None), item("t")], overlaps=[{"a": "w", "b": "t", "verdict": "wrapper"}])
    assert one(handw, "w").risk == 1
    reach = run([item("w"), item("t")], {"w": ItemEvidence(count=4)}, overlaps=[{"a": "w", "b": "t", "verdict": "wrapper"}])
    assert shape(one(reach, "w")) == ("keep", "Keep", "medium", "via_wrapper", "none", 1, None, None, None, "You reach t through it")
    assert shape(one(reach, "t")) == ("keep", "Keep", "medium", "wrapped", "none", 1, None, None, None, "w calls it")
    wrapped_used = run(
        [item("w"), item("t")],
        {"w": ItemEvidence(count=4), "t": ItemEvidence(count=1)},
        overlaps=[{"a": "w", "b": "t", "verdict": "wrapper"}],
    )
    assert one(wrapped_used, "t").reasons[0].code == "heavy_use"
    assert one(wrapped_used, "w").tier == "redundant"
    wrapped_dead = run([item("w"), item("t")], overlaps=[{"a": "w", "b": "t", "verdict": "wrapper"}])
    assert one(wrapped_dead, "t").reasons[0].code in ("never_seen", "referenced")
    over = run([item("a"), item("b")], {"b": ItemEvidence(count=9, percentile=50)}, overlaps=link("overlap"))
    assert shape(one(over, "a")) == (
        "redundant",
        "Likely redundant",
        "medium",
        "overlap_used",
        "remove",
        2,
        "look",
        400,
        None,
        "You use b for this",
    )
    hand_over = run([item("a", origin=None), item("b")], {"b": ItemEvidence(count=9, percentile=50)}, overlaps=link("overlap"))
    assert one(hand_over, "a").confidence == "medium"  # the partner is a twin: no hand-written penalty
    assert shape(one(run([item("a")], used(percentile=10, trend="fading")), "a")) == (
        "review", "Review", "low", "fading", "none", 1, "wait", None, None, "Used 6 times; in your bottom 10% and fading",
    )  # fmt: skip
    assert shape(one(run([item("a", disabled=True)]), "a")) == (
        "off",
        "Switched off",
        None,
        "off",
        "none",
        1,
        None,
        None,
        None,
        "Switched off; the scan still counts its cost.",
    )
    assert shape(one(run([item("a")], pins=frozenset({"x:skill:a"})), "a")) == (
        "keep",
        "Keep",
        "high",
        "pinned",
        "none",
        1,
        None,
        None,
        None,
        "You pinned it.",
    )
    vague = run([item("a", desc="notes helper")], {"a": ItemEvidence(vague=True)})
    assert shape(one(vague, "a")) == (
        "review",
        "Review",
        "low",
        "vague_description",
        "fix_description",
        2,
        "look",
        400,
        None,
        "Its description is 2 words, so Claude may never pick it",
    )
    assert shape(one(run([item("a", cost=10)]), "a")) == (
        "review",
        "Review",
        "low",
        "costs_little",
        "none",
        1,
        "wait",
        None,
        None,
        "Not used, but costs little; no rush",
    )
    assert shape(one(run([item("a")], days=5, sessions=5), "a")) == (
        "too_early",
        "Not enough history yet",
        "low",
        "too_early",
        "none",
        1,
        "wait",
        None,
        7,
        "Only 5 sessions over 5 active days; check back after ~7 more",
    )
    assert shape(one(run([item("a")], {"a": ItemEvidence(purpose_class="rare")}, days=34), "a"))[:10] == (
        "keep_rare", "Keep (rarely needed)", "low", "rare_purpose", "none", 1, "wait", None, 56,
        "Made for occasional work; 34 active days can't tell yet",
    )  # fmt: skip
    quarterly = item("a", desc="the quarterly thing here")
    assert (
        one(run([quarterly], {"a": ItemEvidence(purpose_class="rare")}, days=34), "a").reasons[0].text
        == "Made for quarterly work; 34 active days can't tell yet"
    )
    assert shape(one(run([item("a")], days=25, sessions=40), "a")) == (
        "could_go", "Could go", "high", "never_seen", "remove", 1, "safe", 400, None,
        "0 uses in 25 active days (40 sessions); costs 400 tokens every session",
    )  # fmt: skip
    one_use = used(count=1, sessions_used=1, purpose_class="rare")
    assert shape(one(run([item("a")], one_use), "a")) == (
        "keep_rare",
        "Keep",
        "medium",
        "rare_purpose",
        "none",
        1,
        None,
        None,
        None,
        "Used 1 times; made for occasional work",
    )


def test_guard_and_trigger_shapes() -> None:
    refs = {"a": ItemEvidence(referenced_by=("p", "q"))}
    assert shape(one(run([item("a")], refs, days=25, sessions=40), "a")) == (
        "review", "Review", "medium", "referenced", "none", 1, "wait", None, None, "p, q calls it",
    )  # fmt: skip
    assert [r.code for r in one(run([item("a")], refs, days=25, sessions=40), "a").reasons] == ["referenced", "never_seen"]
    per = {"a": ItemEvidence(referenced_by=("p",)), "b": ItemEvidence(count=3)}
    redundant = run([item("a"), item("b")], per, habits={"b": ItemHabits(decayed_use=2.0)},
                    overlaps=[{"a": "a", "b": "b", "verdict": "duplicate"}])  # fmt: skip
    assert one(redundant, "a").tier == "review"
    weak = {"a": ItemEvidence(referenced_by=("p",), purpose_class="occasional")}
    got = one(run([item("a", origin=None)], weak, days=30, sessions=14), "a")
    assert got.reasons[0].code == "referenced" and got.confidence == "low"
    conflict = [{"kind": "trigger", "ids": ["a"], "detail": "x"}]
    assert shape(one(run([item("a")], conflicts=conflict, days=25, sessions=40), "a"))[:4] == ("could_go", "Could go", "high", "never_seen")
    both_reasons = one(run([item("a")], refs, conflicts=conflict, days=25, sessions=40), "a")
    assert [r.code for r in both_reasons.reasons] == ["referenced", "never_seen", "trigger_conflict"]
    assert both_reasons.reasons[-1].text == "Shares trigger phrases with another Item"
    win = one(twins(0, 0, 3.0, 0.0, conflicts=conflict), "a")
    assert (win.tier, win.label, win.group, win.confidence, win.risk) == ("review", "Review", "wait", "medium", 1)
    assert [r.code for r in win.reasons] == ["twin_loser", "trigger_conflict"]


def test_plugin_shapes() -> None:
    got = plugin_setup((1, 0, 0))
    p = one(got, "p", "plugin")
    assert shape(p)[:9] == ("keep", "Keep", "medium", "plugin_partly_used", "none", 1, None, None, None)
    assert [r.code for r in p.reasons] == ["plugin_partly_used", "plugin_cannot_split"]
    assert one(got, "k1").tier == "review"
    unclear = one(
        run([item("p", "plugin", 1000), item("k0", plugin="p"), item("k1", plugin="p")], {"k1": ItemEvidence(first_seen="2026-11-01")}),
        "p",
        "plugin",
    )
    assert shape(unclear) == (
        "review",
        "Review",
        "low",
        "children_unclear",
        "none",
        1,
        "wait",
        None,
        None,
        "Some of its skills are too new to judge",
    )
    none_used = one(plugin_setup((0, 0, 0)), "p", "plugin")
    assert shape(none_used)[:5] == ("could_go", "Could go", "medium", "children_unused", "disable_plugin")
    assert (none_used.risk, none_used.reasons[0].code) == (2, "children_unused")
    kid = one(plugin_setup((0, 0, 0)), "k0")
    assert shape(kid) == ("review", "Review", "high", "part_of_plugin", "none", 1, "wait", None, None, "Part of p")
    costed = [
        item("p", "plugin", 1000),
        item("k0", plugin="p", cost=100),
        item("k1", plugin="p", cost=None),
        item("k2", plugin="p", cost=50),
    ]
    assert (
        one(run(costed, {"k0": ItemEvidence(count=2)}), "p", "plugin").reasons[1].text
        == "The other 2 cost 50 tokens; the plugin can't be split"
    )
    assert one(plugin_setup((0, 0, 1)), "p", "plugin").tier == "keep"


def test_misc_edges() -> None:
    assert v.purpose_class("x", "quarterly_thing") == "rare"
    assert v.purpose_class("x", "release-notes") == "rare"
    assert v.purpose_class("calls the RELEASE helper", "z") == "rare"
    data = {"items": [item("alpha"), item("b", desc="CALLS ALPHA now")]}
    assert v.referenced_by(data["items"][0], data) == ("b",)
    built = v.evidence({"items": [item("quarterly-x", desc="plain words")]}, Habits(1, 1), Evidence(1, 1, 1, 1.0, {}, 0.0))
    assert built.items["quarterly-x"].purpose_class == "rare"
    kb = run([item("h", "hook", None)], hook_bytes={"h": 10**7})
    assert one(kb, "h", "hook").reasons[0].text == "Adds 10000.0 KB on every h"
    # id order, not name order, breaks a full tie
    swapped = run([item("a", id="i2"), item("b", id="i1")], overlaps=[{"a": "a", "b": "b", "verdict": "duplicate"}])
    assert (swapped["i2"].tier, swapped["i1"].tier) == ("keep", "redundant")
    # a missing cost counts as free when comparing twins
    free = run([item("a", cost=None), item("b", cost=1)], overlaps=[{"a": "a", "b": "b", "verdict": "duplicate"}])
    assert one(free, "b").tier == "redundant"
    ev = Evidence(5, 5, 5, 0.0, {}, 0.0, {})
    assert v.assess({"items": [item("a")]}, ev, Habits(5, 1), frozenset(), TODAY)["x:skill:a"].recheck_after == 10
    pace = Evidence(5, 10, 10, 1.0, {}, 0.0, {})
    assert v.assess({"items": [item("a")]}, pace, Habits(10, 1), frozenset(), TODAY)["x:skill:a"].recheck_after == 10


def test_remaining_edges() -> None:
    assert v.purpose_class("x", "new-project") == "occasional"
    assert (
        one(run([item("a", desc="plain words")], {"a": ItemEvidence(purpose_class="rare")}, days=34), "a")
        .reasons[0]
        .text.startswith("Made for occasional")
    )
    named = item("quarterly-x", desc="plain words")
    named_run = run([named], {"quarterly-x": ItemEvidence(purpose_class="rare")}, days=34)
    assert one(named_run, "quarterly-x").reasons[0].text == "Made for quarterly work; 34 active days can't tell yet"
    seen = run([named], {"quarterly-x": ItemEvidence(purpose_class="rare", count=2, sessions_used=2)})
    assert one(seen, "quarterly-x").reasons[0].text == "Used 2 times; made for quarterly work"
    link = [{"a": "w", "b": "t", "verdict": "wrapper"}]
    both = run([item("w"), item("t")], {"w": ItemEvidence(count=4), "t": ItemEvidence(count=2)}, overlaps=link)
    assert one(both, "w").confidence == "medium"
    low = {"a": ItemEvidence(referenced_by=("p",), purpose_class="occasional")}
    assert one(run([item("a", origin=None)], low, days=60, sessions=14), "a").confidence == "low"
    two = plugin_setup((2, 3, 0))
    assert one(two, "p", "plugin").reasons[0].text == "You use 2 of its 3 skills (k0, k1)."
    kids = [item("p", "plugin", 1000), item("k0", plugin="p"), item("k1", plugin="p"), item("t")]
    per = {"t": ItemEvidence(count=3)}
    dup = run(kids, per, habits={"t": ItemHabits(decayed_use=2.0)}, overlaps=[{"a": "k0", "b": "t", "verdict": "duplicate"}])
    assert one(dup, "k0").reasons[0].code == "duplicate_loser" or one(dup, "k0").reasons[0].code == "part_of_plugin"
    assert (one(dup, "p", "plugin").tier, one(dup, "k0").reasons[0].code, one(dup, "k1").reasons[0].code) == (
        "could_go",
        "part_of_plugin",
        "part_of_plugin",
    )
