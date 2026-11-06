"""Exact values for assessment.py's adapters: defaults, keys, ordering and error edges, so no field can drift unnoticed."""

import math

from constellation import assessment as A
from constellation import habits
from constellation.redact import redact
from constellation.usage import mac
from constellation.verdict_types import Assessment, Evidence, ItemEvidence, Reason

SALT = "cd" * 32
TODAY = "2026-11-10"


def it(id_, kind, name, **extra):
    return {"id": id_, "kind": kind, "name": name, "description": "d " + name, **extra}


def test_scope_defaults_to_project_and_reads_user_and_local():
    assert A._scope({"id": "x"}) == "project"
    assert A._scope({"id": "x:mcp_server:user/s"}) == "user"
    assert A._scope({"id": "x:mcp_server:local/1/s"}) == "local"
    assert A._scope({"id": "x:mcp_server:other/s"}) == "project"


def test_days_is_whole_days_and_zero_when_unparseable_or_reversed():
    assert A._days("2026-11-01", "2026-11-01") == 0
    assert A._days("2026-11-01", "2026-11-04") == 3
    assert A._days("2026-11-04", "2026-11-01") == 0
    assert A._days("junk", "2026-11-01") == 0
    assert A._days("2026-11-01", "junk") == 0


def test_skipped_share_is_skipped_over_files_plus_skipped():
    assert A._skipped({}) == 0.0
    assert A._skipped({"usage_window": None}) == 0.0
    assert A._skipped({"usage_window": {"files": 6, "skipped": 2}}) == 0.25
    assert A._skipped({"usage_window": {"files": 0, "skipped": 3}}) == 1.0
    assert A._skipped({"usage_window": {"files": 4, "skipped": 0}}) == 0.0
    assert A._skipped({"usage_window": {"files": 4}}) == 0.0
    assert A._skipped({"usage_window": {"skipped": 1}}) == 1.0
    assert A._skipped({"usage_window": {"files": 0, "skipped": 0}}) == 0.0


def test_keys_qualify_only_the_shared_names():
    items = [it("x", "skill", "n"), it("y", "skill", "n"), it("solo", "skill", "solo"), it("a:mcp_server:user/s", "mcp_server", "srv")]
    assert A._keys(items) == {"x": "n (skill) [x]", "y": "n (skill) [y]", "solo": "solo", "a:mcp_server:user/s": "srv"}
    mixed = [it("k", "skill", "n"), it("u:mcp_server:user/s", "mcp_server", "n"), it("l:mcp_server:local/s", "mcp_server", "n")]
    assert A._keys(mixed) == {"k": "n (skill)", "u:mcp_server:user/s": "n (user)", "l:mcp_server:local/s": "n (local)"}


def test_tokens_accepts_only_finite_numbers():
    assert A._tokens(5) == 5 and A._tokens(2.5) == 2.5 and A._tokens(0) == 0
    for bad in (None, True, "5", math.nan, math.inf, -math.inf):
        assert A._tokens(bad) is None


FULL = {
    "items": [
        it("h:1", "hook", "Stop:*"),
        it("pl", "plugin", "pack", origin="user"),
        it("s:a", "skill", "alpha", origin="pl", scope="project", disabled=True),
        it("s:b", "skill", "beta"),
        it("s:t", "skill", "tee"),
        it("z:mcp_server:local/s", "mcp_server", "srv"),
        it("m:mcp_server:proj/s", "mcp_server", "srv"),
        it("a:mcp_server:user/s", "mcp_server", "srv"),
    ],
    "costs": {"s:a": {"always_on": 10}, "s:b": {"always_on": math.nan}, "pl": None},
    "relations": [
        {"kind": "contains", "source": "pl", "target": "s:a"},
        {"kind": "contains", "source": "pl", "target": "s:b"},
        {"kind": "contains", "source": "s:b", "target": "s:t"},
        {"kind": "triggers", "source": "s:b", "target": "s:t"},
        {"kind": "triggers", "source": "s:a", "target": "s:t"},
        {"kind": "triggers", "source": "nope", "target": "s:t"},
        {"kind": "contains", "source": "s:a", "target": "s:a"},
    ],
    "conflicts": [
        {"kind": "mcp_name", "item_ids": ["a:mcp_server:user/s", "z:mcp_server:local/s", "m:mcp_server:proj/s", "gone"], "reason": "r"},
        {"kind": "mcp_name", "item_ids": ["gone"], "reason": "r"},
        {"kind": "trigger", "item_ids": ["s:a", "s:b", "gone"], "reason": "both fire"},
        {"kind": "other", "item_ids": ["s:a"], "reason": "x"},
    ],
    "overlaps": [
        {"a_id": "s:a", "b_id": "s:b", "verdict": "duplicate"},
        {"a_id": "s:a", "b_id": "s:t", "verdict": "distinct"},
        {"a_id": "s:a", "b_id": "gone", "verdict": "duplicate"},
        {"a_id": "gone", "b_id": "s:a", "verdict": "duplicate"},
    ],
    "hook_weights": {"h:1": {"bytes": 5}, "s:a": {"bytes": None}, "s:b": "junk", "gone": {"bytes": 9}},
}


def row(id_, kind, name, **extra):
    base = {"id": id_, "kind": kind, "name": name, "match": name, "description": "d " + name, "origin": None, "always_on": None}
    return {"callers": [], "scope": "global", **base, **extra}


def test_adapt_renames_items_and_passes_only_what_loads():
    out = A.adapt(FULL, A._keys(FULL["items"]))
    assert out["items"] == [
        row("h:1", "hook", "Stop:*"),
        row("pl", "plugin", "pack", origin="user"),
        row("s:a", "skill", "alpha", origin="pl", scope="project", disabled=True, always_on=10, plugin="pack"),
        row("s:b", "skill", "beta", plugin="pack"),
        row("s:t", "skill", "tee", callers=["alpha", "beta"]),
        row("z:mcp_server:local/s", "mcp_server", "srv (local)", match="srv", description="d srv"),
        row("m:mcp_server:proj/s", "mcp_server", "srv (project)", match="srv", description="d srv"),
        row("a:mcp_server:user/s", "mcp_server", "srv (user)", match="srv", description="d srv"),
    ]
    assert out["conflicts"] == [
        {"kind": "mcp_name", "ids": ["srv (project)"], "detail": "project copy shadowed by local scope"},
        {"kind": "mcp_name", "ids": ["srv (user)"], "detail": "user copy shadowed by local scope"},
        {"kind": "trigger", "ids": ["alpha", "beta"], "detail": "both fire"},
    ]
    assert out["overlaps"] == [{"a": "alpha", "b": "beta", "verdict": "duplicate"}]
    assert out["plugin_children"] == {"pack": 2}
    assert out["hook_bytes"] == {"Stop:*": 5}
    assert set(out) == {"items", "overlaps", "conflicts", "plugin_children", "hook_bytes"}


def test_adapt_tolerates_a_scan_with_only_items():
    data = {"items": FULL["items"][:3]}
    out = A.adapt(data, A._keys(data["items"]))
    assert out["items"] == [
        row("h:1", "hook", "Stop:*"),
        row("pl", "plugin", "pack", origin="user"),
        row("s:a", "skill", "alpha", origin="pl", scope="project", disabled=True),
    ]
    assert (out["overlaps"], out["conflicts"], out["plugin_children"], out["hook_bytes"]) == ([], [], {}, {})


def test_two_copies_of_one_scope_are_ranked_by_id():
    items = [it("b:mcp_server:user/s", "mcp_server", "s"), it("a:mcp_server:user/s", "mcp_server", "s")]
    data = {"items": items, "conflicts": [{"kind": "mcp_name", "item_ids": [i["id"] for i in items], "reason": "r"}]}
    out = A.adapt(data, A._keys(items))["conflicts"]
    assert out == [{"kind": "mcp_name", "ids": ["s (user) [b:mcp_server:user/s]"], "detail": "user copy shadowed by user scope"}]


LEDGER = {
    "salt": SALT,
    "co": {},
    "days": {
        "2026-11-01": {"sessions": 2, "projects": {"P1": 2}},
        "2026-11-03": {"sessions": 3, "projects": {"P1": 1, "P2": 2}},
        "2026-11-20": {"sessions": 9, "projects": {"P3": 9}},
    },
    "items": {
        mac(SALT, "s:a", 12): {
            "first_seen": "2026-11-01",
            "days": {
                "2026-11-01": {"n": 1, "s": 1, "p": {"P1": 1}},
                "2026-11-03": {"n": 2, "s": 2, "p": {"P2": 2}},
                "2026-11-04": {"n": 0, "s": 0, "p": {}},
                "2026-11-20": {"n": 5, "s": 5, "p": {"P3": 5}},
            },
        },
        mac(SALT, "s:b", 12): {
            "first_seen": "2026-11-03",
            "days": {
                "2026-11-03": {"n": 1, "s": 1, "p": {"P1": 1}},
                "2026-11-02": {"n": 0, "s": 0, "p": {}},
                TODAY: {"n": 1, "s": 4, "p": {}},
            },
        },
    },
}
LEDGER_SCAN = {
    "items": [it("h:1", "hook", "Stop:*"), it("pl", "plugin", "pack"), it("s:a", "skill", "alpha", changed_on="2026-10-01"),
              it("s:b", "skill", "beta"), it("s:c", "skill", "cee")],
    "relations": [{"kind": "contains", "source": "pl", "target": t} for t in ("s:a", "s:b", "s:c")]
    + [{"kind": "triggers", "source": "s:a", "target": "s:b"}],
    "usage_window": {"files": 6, "skipped": 2},
}  # fmt: skip


def test_from_ledger_counts_only_real_past_use_and_hides_the_first_watched_day():
    h, base = A._from_ledger(LEDGER_SCAN, LEDGER, TODAY, A._keys(LEDGER_SCAN["items"]))
    assert (base.sessions, base.active_days, base.span_days, base.sessions_per_day, base.skipped_share) == (5, 2, 3, 2.5, 0.25)
    assert base.projects == {"P1": ("2026-11-03", 3), "P2": ("2026-11-03", 2)}
    assert base.items == {
        "alpha": ItemEvidence(sessions_used=3, days_used=2, last_used="2026-11-03", idle_active_days=0, changed_on="2026-10-01"),
        "beta": ItemEvidence(sessions_used=5, days_used=2, last_used=TODAY, idle_active_days=0, first_seen="2026-11-03"),
        "cee": ItemEvidence(first_seen=TODAY),
    }
    assert (h.active_days, h.projects_active) == (2, 2) and sorted(h.items) == ["alpha", "beta", "cee"]
    assert h.items["cee"].prior_from == "group"  # the plugin's children are its group


def test_from_ledger_with_no_days_says_so():
    ledger = {"salt": SALT, "co": {}, "days": {}, "items": {}}
    h, base = A._from_ledger({"items": LEDGER_SCAN["items"]}, ledger, TODAY, A._keys(LEDGER_SCAN["items"]))
    assert base == Evidence(
        0, 0, 0, 0.0, {}, 0.0, {k: ItemEvidence(changed_on=c) for k, c in (("alpha", "2026-10-01"), ("beta", None), ("cee", None))}
    )
    assert (h.active_days, h.projects_active) == (0, 0)


def test_from_scan_uses_the_saved_counts_and_caps_them_by_the_window():
    items = [
        it("h:1", "hook", "Stop:*"),
        it("s:a", "skill", "alpha", changed_on="2026-10-01"),
        it("s:b", "skill", "beta"),
        it("s:x", "skill", "ex"),
        it("s:y", "skill", "why"),
        it("s:z", "skill", "zed"),
        it("m:1", "mcp_server", "srv"),
        it("s:q", "skill", "nousage"),
    ]
    data = {
        "items": items,
        "usage": {
            "s:a": {"count": 3, "last_used": "2026-11-08T09:00:00"},
            "s:b": {"count": 0, "last_used": None},
            "s:y": {"count": 9, "last_used": "2026-11-10"},
            "s:z": {"count": 1, "last_used": None},
            "m:1": {"count": 2, "last_used": "2026-11-01"},
            "h:1": {"count": 4, "last_used": None},
        },
        "usage_by_project": {
            "s:x": {"p1": {"count": 2, "last_used": "2026-11-03T10:00"}, "p2": {"count": 3, "last_used": None}},
            "s:a": {"p1": {"count": 50, "last_used": "2026-11-09"}},
            "s:y": {"p1": {"count": 6}, "p2": {"count": 2}, "p3": {"count": 0}, "p4": {"count": 1}},
            "s:q": {},
            "s:z": {"p1": {"count": 1}},
        },
        "usage_window": {"first": "2026-11-01", "last": "2026-11-10", "sessions": 4, "files": 6, "skipped": 2},
        "projects": {"p1": 1, "p2": 2},
    }
    h, base = A._from_scan(data, A._keys(items))
    assert base == Evidence(
        4, 4, 10, 1.0, {}, 0.25,
        {
            "alpha": ItemEvidence(sessions_used=3, days_used=3, last_used="2026-11-08", idle_active_days=2, changed_on="2026-10-01"),
            "beta": ItemEvidence(),
            "ex": ItemEvidence(sessions_used=4, days_used=4, last_used="2026-11-03", idle_active_days=7),
            "srv": ItemEvidence(sessions_used=2, days_used=2, last_used="2026-11-01", idle_active_days=9),
            "why": ItemEvidence(sessions_used=4, days_used=4, last_used="2026-11-10", idle_active_days=0),
            "zed": ItemEvidence(sessions_used=1, days_used=1),
        },
    )  # fmt: skip
    assert (h.active_days, h.projects_active) == (4, 2)
    got = {
        k: (v.decayed_use, v.all_time, v.percentile, v.idle_active_days, v.projects_used, v.top_project_share) for k, v in h.items.items()
    }
    assert got == {
        "alpha": (3.0, 3, 40, 2, 1, 1.0),
        "beta": (0.0, 0, 0, None, 0, 0.0),
        "ex": (5.0, 5, 60, 7, 2, 0.6),
        "srv": (2.0, 2, 0, 9, 0, 0.0),
        "why": (9.0, 9, 80, 0, 3, 6 / 9),
        "zed": (1.0, 1, 20, None, 1, 1.0),
    }


def test_from_scan_percentile_rounds_down_to_whole_numbers():
    items = [it(f"s:{n}", "skill", f"n{n}") for n in (1, 2, 3)]
    data = {"items": items, "usage": {f"s:{n}": {"count": n} for n in (1, 2, 3)}}
    h, _ = A._from_scan(data, A._keys(items))
    assert [h.items[f"n{n}"].percentile for n in (1, 2, 3)] == [0, 33, 66]
    assert all(type(v.percentile) is int for v in h.items.values())


def test_from_scan_without_a_window_or_usage_is_empty_and_partial_windows_have_no_span():
    items = [it("s:a", "skill", "alpha", changed_on="2026-10-01")]
    h, base = A._from_scan({"items": items}, A._keys(items))
    assert base == Evidence(0, 0, 0, 0.0, {}, 0.0, {}) and (h.active_days, h.projects_active, h.items) == (0, 0, {})
    data = {"items": items, "usage": {"s:a": {"count": 3}}, "usage_window": {"files": 5, "first": "2026-11-01"}}
    h, base = A._from_scan(data, A._keys(items))
    assert base == Evidence(5, 0, 0, 0.0, {}, 0.0, {"alpha": ItemEvidence(sessions_used=3, changed_on="2026-10-01")})
    assert h.items["alpha"].percentile == 0 and h.items["alpha"].idle_active_days is None
    # a same-day window is one day long
    same = {**data, "usage_window": {"files": 5, "first": "2026-11-01", "last": "2026-11-01"}}
    assert A._from_scan(same, A._keys(items))[1].span_days == 1
    assert (
        A._from_scan({**same, "usage_window": {"sessions": 2, "first": "2026-11-01", "last": "2026-11-01"}}, A._keys(items))[1].sessions
        == 2
    )


def test_public_redacts_reason_text_and_keeps_code():
    a = Assessment(
        "i", "keep", "Keep", "high", (Reason("c1", "see /Users/someone/x.md"), Reason("c2", "plain")), "none", None, 1, None, None
    )
    out = A.public(a)
    assert out["reasons"] == [{"code": "c1", "text": redact("see /Users/someone/x.md")}, {"code": "c2", "text": "plain"}]
    assert out["tier"] == "keep" and out["id"] == "i"


def _compute_scan(**extra):
    items = [it("s:a", "skill", "alpha"), it("s:b", "skill", "beta")]
    return {"items": items, **extra}


def _ledger_for(tmp_path, setup):
    day_rows = {f"2026-10-{n:02d}": {"sessions": 2, "projects": {}} for n in range(1, 29)}
    record = {"first_seen": "2026-10-01", "days": {k: {"n": 1, "s": 1, "p": {}} for k in day_rows}}
    habits.save(
        tmp_path / "h.json",
        {
            setup: {
                "salt": SALT,
                "days": day_rows,
                "items": {mac(SALT, "s:a", 12): record, mac(SALT, "s:b", 12): {"first_seen": "2026-11-07", "days": {}}},
                "co": {},
            }
        },
    )
    return tmp_path / "h.json"


def test_compute_reads_the_ledger_of_this_setup_only(tmp_path):
    path = _ledger_for(tmp_path, "XXXX")
    assert A.compute(_compute_scan(), path, tmp_path / "p.json", TODAY).ledger is False  # no setup key: no ledger
    assert A.compute(_compute_scan(setup="XXXX"), path, tmp_path / "p.json", TODAY).ledger is True
    assert A.compute(_compute_scan(setup="other"), path, tmp_path / "p.json", TODAY).ledger is False


def test_compute_passes_pins_and_today_to_the_engine(tmp_path):
    from constellation import pins

    path = _ledger_for(tmp_path, "s1")
    pins.add(tmp_path / "p.json", "s:a", TODAY)
    found = A.compute(_compute_scan(setup="s1"), path, tmp_path / "p.json", TODAY)
    assert found.evidence.items["s:a"].pinned is True and found.evidence.items["s:b"].pinned is False
    assert found.assessments["s:b"].reasons[0].text == "Added 3 days ago"  # beta was first seen on 11-07, today is 11-10
    assert found.assessments["s:b"].tier == "too_early"


def test_from_ledger_reports_the_typical_gap_between_use_days():
    days = {f"2026-11-0{n}": {"sessions": 1, "projects": {}} for n in range(1, 6)}
    used = {d: {"n": 1, "s": 1, "p": {}} for d in ("2026-11-01", "2026-11-03", "2026-11-05")}
    ledger = {"salt": SALT, "co": {}, "days": days, "items": {mac(SALT, "s:a", 12): {"first_seen": "2026-11-01", "days": used}}}
    items = [it("s:a", "skill", "alpha")]
    _, base = A._from_ledger({"items": items}, ledger, "2026-11-05", A._keys(items))
    assert base.items["alpha"].mean_gap == 2.0 and base.items["alpha"].idle_active_days == 0
