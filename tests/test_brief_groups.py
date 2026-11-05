import json
from pathlib import Path

from constellation.brief import BUDGET_DAYS, build_brief
from constellation.suggestions import suggest
from constellation.verdict_types import Assessment, Evidence, ItemEvidence, Reason

FIX = Path(__file__).parent / "fixtures" / "assess"
P = "claude-code:"


def _setup():
    setup = json.loads((FIX / "setup.json").read_text())
    expected = json.loads((FIX / "expected.json").read_text())
    ids = {i["name"]: i["id"] for i in setup["items"]}
    data = {
        "items": [{k: v for k, v in i.items() if k != "always_on"} for i in setup["items"]],
        "costs": {i["id"]: {"always_on": i["always_on"]} for i in setup["items"] if i["always_on"] is not None},
        "overlaps": [{"a_id": ids[o["a"]], "b_id": ids[o["b"]], "verdict": o["verdict"], "reason": "r"} for o in setup["overlaps"]],
        "relations": [],
    }
    assessments = {a["id"]: Assessment(**{**a, "reasons": tuple(Reason(**r) for r in a["reasons"])}) for a in expected["assessments"]}
    ev = setup["evidence"]
    evidence = Evidence(ev["sessions"], ev["active_days"], ev["span_days"], ev["sessions_per_day"], {}, ev["skipped_share"])
    return data, assessments, evidence, expected["brief"]


def test_fixture_groups_range_and_ranking():
    data, assessments, evidence, want = _setup()
    got = build_brief(data, assessments, evidence)
    names = lambda g: [(r["removes"] or r["item_ids"][0]).split(":")[-1] for r in got[g]["rows"]]  # noqa: E731
    assert names("safe") == ["tune-spacing", "changelog-draft"]  # 610/1 then 380/1
    assert names("look") == ["pdf-tools", "repo-map", "lint-fix", "scratch-notes", "search"]  # 950, 260, 100, 45, unknown last
    assert got["safe"]["saves"] == want["safe_saves"] and got["look"]["saves"] == want["look_saves"]
    assert got["range"]["low"] == want["range"]["low"] and got["range"]["high"] == want["range"]["high"]
    assert got["range"]["unknown"] == want["range"]["unknown"] == got["look"]["unknown"] == 1
    assert got["range"]["per_day"] == (1600, 5900)  # 990 and 3700 times 1.6 sessions a day, to the nearest 100
    assert got["evidence"] == {"sessions": 52, "active_days": 34, "span_days": 52, "sessions_per_day": 1.6}
    assert got["scope"]["caveat"]


def test_safe_rank_is_savings_over_risk_then_savings():
    data, assessments, evidence, _ = _setup()
    got = build_brief(data, assessments, evidence)
    assert [r["saves"] for r in got["safe"]["rows"]] == [610, 380]
    rows = got["safe"]["rows"]
    assert rows[0]["removes"] == P + "skill:tune-spacing" and rows[0]["kind"] == "remove_unused"


def test_wait_group_has_summary_and_no_removal():
    data, assessments, evidence, _ = _setup()
    wait = build_brief(data, assessments, evidence)["wait"]
    assert wait["summary"] == [
        {"code": "hook_weight", "count": 1, "recheck_after": None},
        {"code": "rare_purpose", "count": 1, "recheck_after": 56},
        {"code": "too_early", "count": 1, "recheck_after": None},
    ]
    assert all(r["removes"] is None and r["kind"] == "wait" for r in wait["rows"])


def test_keep_tiers_are_not_listed():
    data, assessments, evidence, _ = _setup()
    got = build_brief(data, assessments, evidence)
    listed = {r["item_ids"][0] for g in ("safe", "look") for r in got[g]["rows"]} | {r["item_ids"][0] for r in got["wait"]["rows"]}
    assert P + "agent:git-helper" not in listed and P + "skill:release-notes" not in listed


def test_ids_unchanged_for_unchanged_kinds():
    data, assessments, evidence, _ = _setup()
    got = build_brief(data, assessments, evidence)
    twin = got["safe"]["rows"][1]
    assert twin["kind"] == "remove_duplicate"
    assert twin["item_ids"] == sorted([P + "skill:changelog-draft", P + "skill:release-notes"])
    assert twin["removes"] == P + "skill:changelog-draft"
    old = {s.id for s in suggest({**data, "usage": {}, "usage_window": {"files": 1, "first": None, "last": None, "skipped": 0}})}
    assert twin["id"] in old


def test_plugin_parts_are_counted_once_through_the_plugin():
    data, assessments, evidence, _ = _setup()
    child = P + "skill:tune-spacing"
    data["relations"] = [{"kind": "contains", "source": P + "plugin:pdf-tools", "target": child}]
    got = build_brief(data, assessments, evidence)
    assert got["safe"]["saves"] == 380  # tune-spacing sits inside the disabled plugin, so it is not counted twice
    assert got["range"]["high"] == 380 + 2710


def test_unknown_pace_gives_zero_per_day_and_no_group_means_no_row():
    data, assessments, evidence, _ = _setup()
    evidence = Evidence(0, 0, 0, 0.0, {}, 0.0)
    got = build_brief(data, assessments, evidence)
    assert got["range"]["per_day"] == (0, 0)
    assert build_brief(data, {}, evidence)["range"] == {"low": 0, "high": 0, "per_day": (0, 0), "unknown": 0}


def test_tie_on_rank_breaks_by_name_then_id():
    data, _, evidence, _ = _setup()
    r = (Reason("never_seen", "x"),)
    mk = lambda id_: Assessment(id_, "could_go", "Could go", "high", r, "remove", 100, 1, "safe", None)  # noqa: E731
    ids = [P + "skill:tune-spacing", P + "skill:repo-map", P + "skill:lint-fix"]
    got = build_brief(data, {i: mk(i) for i in ids}, evidence)
    assert [r["item_ids"][0] for r in got["safe"]["rows"]] == [ids[2], ids[1], ids[0]]  # by name


def test_risk_outweighs_a_slightly_larger_saving():
    data, _, evidence, _ = _setup()
    r = (Reason("never_seen", "x"),)
    a = Assessment(P + "skill:lint-fix", "could_go", "Could go", "high", r, "remove", 100, 1, "safe", None)
    b = Assessment(P + "skill:repo-map", "could_go", "Could go", "high", r, "remove", 150, 2, "safe", None)
    got = build_brief(data, {a.id: a, b.id: b}, evidence)
    assert [x["item_ids"][0] for x in got["safe"]["rows"]] == [a.id, b.id]  # 100/1 beats 150/2


def test_move_rows_carry_the_project_label():
    data, assessments, evidence, _ = _setup()
    data["usage_by_project"] = {P + "skill:repo-map": {"proj": {"count": 9}}}
    data["projects"] = {"proj": "my-repo"}
    row = next(r for r in build_brief(data, assessments, evidence)["look"]["rows"] if r["kind"] == "move_to_project")
    assert (row["project"], row["project_label"]) == ("proj", "my-repo")


def test_reasons_are_redacted_and_carried():
    data, assessments, evidence, _ = _setup()
    secret = "".join(["ghp_", "aB3dE5gH" * 4, "7jK9"])
    data["items"][3]["name"] = secret
    out = json.dumps(build_brief(data, assessments, evidence))
    assert secret not in out
    row = build_brief(data, assessments, evidence)["safe"]["rows"][0]
    assert row["reasons"][0]["code"] == "never_seen" and row["tier"] == "could_go" and row["confidence"] == "high"


def test_budget_line_counts_skills_used_in_the_last_30_active_days():
    data, assessments, evidence, _ = _setup()
    skill = lambda n: P + "skill:" + n  # noqa: E731
    ev = {
        skill("release-notes"): ItemEvidence(count=3, idle_active_days=BUDGET_DAYS - 1),  # 420 tokens, recent
        skill("repo-map"): ItemEvidence(count=9),  # 520, no idle gap: used today
        skill("lint-fix"): ItemEvidence(count=6, idle_active_days=BUDGET_DAYS),  # 200, too long ago
        skill("tune-spacing"): ItemEvidence(count=0),  # 610, never
    }
    evidence = Evidence(52, 34, 52, 1.6, {}, 0.0, ev)
    data["items"][2]["disabled"] = True  # changelog-draft (380) is switched off and not paid
    b = build_brief(data, assessments, evidence)["budget"]
    assert b == {"kind": "skill", "tokens": 420 + 610 + 520 + 200 + 90 + 450 + 700, "used_tokens": 940, "used_share": 0.31, "days": 30}
    data["costs"] = {}
    assert build_brief(data, assessments, evidence)["budget"] is None


def _a(id_, action, saves, risk=1, group="safe", code="never_seen", recheck=None):
    return Assessment(id_, "could_go", "Could go", "high", (Reason(code, "why"),), action, saves, risk, group, recheck)


def test_row_ids_follow_the_matching_overlap_only():
    data, _, evidence, _ = _setup()
    x, y, w, u = (P + n for n in ("skill:lint-fix", "skill:repo-map", "skill:scratch-notes", "skill:db-migrate"))
    data["overlaps"] = [
        {"a_id": "q", "b_id": "r", "verdict": "duplicate", "reason": "r"},  # unrelated pair
        {"a_id": y, "b_id": x, "verdict": "wrapper", "reason": "r"},  # y calls x
        {"a_id": x, "b_id": w, "verdict": "duplicate", "reason": "r"},
        {"a_id": u, "b_id": w, "verdict": "wrapper", "reason": "r"},
    ]
    rows = lambda *a: {r["removes"]: r["item_ids"] for r in build_brief(data, {i.id: i for i in a}, evidence)["safe"]["rows"]}  # noqa: E731
    assert rows(_a(x, "remove_twin", 5)) == {x: sorted([x, w])}
    assert rows(_a(w, "remove_twin", 5)) == {w: sorted([x, w])}
    assert rows(_a(y, "use_underlying", 5)) == {y: [y, x]}
    assert rows(_a(x, "use_underlying", 5)) == {x: [x]}  # x is only the wrapped side
    assert rows(_a(x, "remove", 5)) == {x: [x]}  # a plain removal ignores overlaps
    assert rows(_a(u, "remove_twin", 5)) == {u: [u]}  # only a wrapper overlap involves it
    assert rows(_a(w, "use_underlying", 5)) == {w: [w]}  # only a duplicate overlap involves it


def test_wait_summary_orders_by_count_then_code_and_takes_the_longest_recheck():
    data, _, evidence, _ = _setup()
    ids = [P + n for n in ("skill:lint-fix", "skill:repo-map", "skill:scratch-notes", "skill:db-migrate")]
    waits = [
        _a(ids[0], "none", None, group="wait", code="b_code", recheck=5),
        _a(ids[1], "none", None, group="wait", code="b_code", recheck=12),
        _a(ids[2], "none", None, group="wait", code="a_code"),
        _a(ids[3], "none", None, group="wait", code="c_code"),
    ]
    summary = build_brief(data, {a.id: a for a in waits}, evidence)["wait"]["summary"]
    assert summary == [
        {"code": "b_code", "count": 2, "recheck_after": 12},
        {"code": "a_code", "count": 1, "recheck_after": None},
        {"code": "c_code", "count": 1, "recheck_after": None},
    ]


def test_rank_ties_prefer_larger_savings_and_unknowns_follow_name_not_risk():
    data, _, evidence, _ = _setup()
    lint, repo, scratch, db = (P + n for n in ("skill:lint-fix", "skill:repo-map", "skill:scratch-notes", "skill:db-migrate"))
    got = build_brief(data, {a.id: a for a in (_a(lint, "remove", 100), _a(repo, "remove", 200, risk=2))}, evidence)
    assert [r["item_ids"][0] for r in got["safe"]["rows"]] == [repo, lint]  # same saving per risk: more saved first
    got = build_brief(data, {a.id: a for a in (_a(lint, "remove", None, risk=2), _a(scratch, "remove", None, risk=1))}, evidence)
    assert [r["item_ids"][0] for r in got["safe"]["rows"]] == [lint, scratch]  # no saving to weigh: name order


def test_row_and_group_fields_are_complete():
    data, assessments, evidence, _ = _setup()
    got = build_brief(data, assessments, evidence)
    row = got["safe"]["rows"][0]
    assert row["reason"].startswith("tune-spacing (skill): 0 uses in 34 active days")
    assert row["reasons"] == [{"code": "never_seen", "text": "0 uses in 34 active days (52 sessions); costs 610 tokens every session"}]
    assert got["safe"]["unknown"] == 0 and got["look"]["unknown"] == 1
    assert row["saves"] == 610 and set(row) == {"id", "kind", "item_ids", "removes", "reason", "saves", "tier", "confidence", "reasons"}


def test_plugin_dedupe_ignores_other_relations_and_other_parents():
    data, assessments, evidence, _ = _setup()
    t = P + "skill:tune-spacing"
    data["relations"] = [
        {"kind": "wraps", "source": P + "plugin:pdf-tools", "target": t},  # not containment
        {"kind": "contains", "source": "someone-else", "target": t},  # parent is not being disabled
    ]
    assert build_brief(data, assessments, evidence)["safe"]["saves"] == 990


def test_a_single_use_still_counts_as_used_for_the_budget():
    data, assessments, _, _ = _setup()
    ev = {P + "skill:repo-map": ItemEvidence(count=1)}
    assert build_brief(data, assessments, Evidence(1, 1, 1, 1.0, {}, 0.0, ev))["budget"]["used_tokens"] == 520
