import json
import os
import stat
from dataclasses import asdict
from datetime import date, timedelta

import pytest
from fakes import write_skill
from test_usage import tool
from test_usage_fresh import put

from constellation import habits
from constellation.claude_code import read_items
from constellation.models import UsageWindow
from constellation.usage import Fresh, mac

SALT = "ab" * 32
TODAY = "2026-11-05"


def H(id_):
    return mac(SALT, id_, 12)


def ledger(days=None, items=None, co=None):
    return {"salt": SALT, "days": days or {}, "items": items or {}, "co": co or {}}


def fresh(sessions=None, projects=None, items=None, co=None):
    return Fresh(sessions or {}, projects or {}, items or {}, co or [])


def window(first=None, last=None):
    return UsageWindow(1, first, last, 0, 1)


def day(sessions, **projects):
    return {"sessions": sessions, "projects": projects}


def cell(n, s, **p):
    return {"n": n, "s": s, "p": p}


def pair(a, b):
    return "|".join(sorted((H(a), H(b))))


def merge(old, new, win, ids=(), today=TODAY):
    return habits.merge(old, new, win, list(ids), today)


# merge: days and items


def test_a_new_item_is_first_seen_today_with_no_days():
    got = merge(ledger(), fresh(), window(), ["a"])
    assert got == ledger(items={H("a"): {"first_seen": TODAY, "days": {}}})


def test_first_seen_is_the_earlier_of_today_and_its_first_use_and_never_a_future_day():
    new = fresh(
        {"2026-10-01": 1, "2026-11-09": 1},
        {"2026-10-01": {}, "2026-11-09": {}},
        {"a": {"2026-10-01": (1, 1, {}), "2026-11-09": (1, 1, {})}},
    )
    got = merge(ledger(), new, window("2026-10-01", "2026-11-09"), ["a"])
    assert got["items"][H("a")] == {"first_seen": "2026-10-01", "days": {"2026-10-01": cell(1, 1)}}
    old = ledger(items={H("a"): {"first_seen": "2026-08-01", "days": {}}})
    assert merge(old, fresh(), window(), ["a"])["items"][H("a")]["first_seen"] == "2026-08-01"


def test_days_inside_the_window_are_replaced_the_first_day_takes_the_maximum_and_outside_days_stay():
    old = ledger(
        days={
            "2026-09-01": day(4, p=1),
            "2026-10-01": day(5, p=1, q=3),
            "2026-10-02": day(9, p=9),
            "2026-10-05": day(8),
            "2026-10-06": day(7),
            "2026-10-07": day(6, p=6),
        },
        items={
            H("a"): {
                "first_seen": "2026-09-01",
                "days": {
                    "2026-09-01": cell(1, 1, x=1),
                    "2026-10-01": cell(1, 4, x=1),
                    "2026-10-03": cell(5, 5),
                    "2026-10-06": cell(6, 6),
                    "2026-10-07": cell(2, 2),
                },
            }
        },
    )
    new = fresh(
        {"2026-10-01": 2, "2026-10-02": 2, "2026-10-06": 1, "2026-11-09": 4},
        {"2026-10-01": {"p": 2, "q": 1}, "2026-10-02": {"p": 1}, "2026-10-06": {}, "2026-11-09": {"p": 4}},
        {"a": {"2026-10-01": (3, 2, {"x": 2, "y": 1}), "2026-10-06": (1, 1, {}), "2026-11-09": (9, 9, {})}},
    )
    got = merge(old, new, window("2026-10-01", "2026-10-06"), ["a"])
    assert got["days"] == {
        "2026-09-01": day(4, p=1),
        "2026-10-01": day(5, p=2, q=3),
        "2026-10-02": day(2, p=1),
        "2026-10-06": day(1),
        "2026-10-07": day(6, p=6),
    }
    assert got["items"][H("a")]["days"] == {
        "2026-09-01": cell(1, 1, x=1),
        "2026-10-01": cell(3, 4, x=2, y=1),
        "2026-10-06": cell(1, 1),
        "2026-10-07": cell(2, 2),
    }


def test_a_rescan_of_the_same_transcripts_changes_nothing():
    new = fresh(
        {"2026-10-01": 2, "2026-10-02": 1},
        {"2026-10-01": {"p": 2}, "2026-10-02": {"p": 1}},
        {"a": {"2026-10-01": (3, 2, {"p": 3}), "2026-10-02": (1, 1, {"p": 1})}},
        [("2026-10-02", ("a", "b")), ("2026-10-02", ("a", "b"))],
    )
    win = window("2026-10-01", "2026-10-02")
    once = merge(ledger(), new, win, ["a", "b"])
    assert merge(once, new, win, ["a", "b"]) == once
    assert once["items"][H("a")]["days"]["2026-10-01"] == cell(3, 2, p=3) and once["co"] == {pair("a", "b"): {"2026-10": 2}}


def test_no_transcripts_keep_every_old_day_and_still_add_new_items():
    old = ledger(days={"2026-10-01": day(3)}, items={H("a"): {"first_seen": "2026-09-01", "days": {"2026-10-01": cell(1, 1)}}})
    got = merge(old, fresh(), window(), ["a", "b"])
    assert got["days"] == old["days"] and got["items"][H("a")] == old["items"][H("a")] and got["items"][H("b")]["first_seen"] == TODAY


def test_retention_drops_old_days_and_unseen_items_but_never_a_current_item():
    cutoff = (date.fromisoformat(TODAY) - timedelta(days=400)).isoformat()
    before = (date.fromisoformat(cutoff) - timedelta(days=1)).isoformat()
    old = ledger(
        days={cutoff: day(1), before: day(1)},
        items={
            H("keeps-days"): {"first_seen": before, "days": {cutoff: cell(1, 1), before: cell(1, 1)}},
            H("keeps-seen"): {"first_seen": cutoff, "days": {}},
            H("gone"): {"first_seen": before, "days": {before: cell(1, 1)}},
            H("current"): {"first_seen": before, "days": {}},
        },
    )
    got = merge(old, fresh(), window(), ["current"])
    assert cutoff == "2025-10-01"
    assert got["days"] == {cutoff: day(1)}
    assert got["items"] == {
        H("keeps-days"): {"first_seen": before, "days": {cutoff: cell(1, 1)}},
        H("keeps-seen"): {"first_seen": cutoff, "days": {}},
        H("current"): {"first_seen": before, "days": {}},
    }


# merge: co-use pairs


def sessions(*pairs_):
    return [(d, tuple(ids)) for d, ids in pairs_]


def test_co_use_counts_months_keeps_pairs_of_two_sessions_and_sorts_hashes():
    new = fresh(co=sessions(("2026-10-02", "ab"), ("2026-11-01", "ab"), ("2026-11-02", "ac"), ("2026-11-09", "ab")))
    got = merge(ledger(), new, window("2026-10-01", "2026-11-02"), ["a", "b", "c"])
    assert got["co"] == {pair("a", "b"): {"2026-10": 1, "2026-11": 1}}  # a+c is one session: dropped; 11-09 is in the future


def test_co_months_after_the_first_are_recomputed_the_first_takes_the_maximum_and_older_stay():
    old = ledger(
        items={H("a"): {"first_seen": TODAY, "days": {}}, H("b"): {"first_seen": TODAY, "days": {}}},
        co={pair("a", "b"): {"2026-08": 4, "2026-09": 3, "2026-10": 5, "2026-11": 9, "2026-12": 2}},
    )
    new = fresh(co=sessions(("2026-09-20", "ab"), ("2026-10-20", "ab"), ("2026-10-21", "ab")))
    got = merge(old, new, window("2026-09-10", "2026-11-03"), ["a", "b"])
    assert got["co"] == {pair("a", "b"): {"2026-08": 4, "2026-09": 3, "2026-10": 2, "2026-12": 2}}


def test_co_pairs_are_capped_largest_first_and_need_both_items_kept_and_recent_months(monkeypatch):
    monkeypatch.setattr(habits, "CO_PAIRS", 2)
    old = ledger(
        items={H(i): {"first_seen": TODAY, "days": {}} for i in "abcd"},
        co={
            pair("a", "b"): {"2026-10": 2},
            pair("a", "c"): {"2026-10": 3},
            pair("c", "d"): {"2026-09": 2, "2026-10": 2},
            pair("a", "z"): {"2026-10": 9},  # z is not kept
            pair("b", "c"): {"2025-09": 7, "2025-10": 1},  # only the second month is within retention: 1 session
        },
    )
    got = merge(old, fresh(), window(), ["a", "b", "c", "d"])
    assert got["co"] == {pair("c", "d"): {"2026-09": 2, "2026-10": 2}, pair("a", "c"): {"2026-10": 3}}


def test_co_ties_in_the_cap_are_broken_by_key(monkeypatch):
    monkeypatch.setattr(habits, "CO_PAIRS", 1)
    old = ledger(
        items={H(i): {"first_seen": TODAY, "days": {}} for i in "abc"},
        co={pair("a", "b"): {"2026-10": 2}, pair("a", "c"): {"2026-10": 2}},
    )
    got = merge(old, fresh(), window(), ["a", "b", "c"])
    assert list(got["co"]) == [min(pair("a", "b"), pair("a", "c"))]


# profile


def spread(n, today=TODAY):
    """n consecutive days ending today, one session each."""
    return {(date.fromisoformat(today) - timedelta(days=i)).isoformat(): day(1) for i in range(n)}


def ago(n):
    return (date.fromisoformat(TODAY) - timedelta(days=n)).isoformat()


def profile(led, kinds, groups=None):
    return habits.profile(led, TODAY, kinds, groups)


def with_items(days, **items):
    return ledger(days=days, items={H(i): {"first_seen": "2025-01-01", "days": cells} for i, cells in items.items()})


def test_trend_compares_rates_per_active_day_of_the_last_30_against_the_90_before():
    # recent: ago(0..29), before: ago(30..119), older: ago(120)
    led = with_items(
        spread(121),
        fade=({ago(40): cell(3, 1), ago(41): cell(0, 0)}),
        fade_thin={ago(40): cell(2, 1)},
        edge={ago(40): cell(9, 1), ago(0): cell(1, 1)},
        rise={ago(40): cell(1, 1), ago(1): cell(4, 1)},
        rise_edge={ago(40): cell(2, 1), ago(1): cell(2, 1)},
        fade_ten={ago(40): cell(10, 1), ago(1): cell(1, 1)},
        rise_three={ago(40): cell(3, 1), ago(1): cell(4, 1)},
        old={ago(120): cell(5, 1)},
        never={},
    )
    got = profile(led, {i: "skill" for i in ("fade", "fade_thin", "edge", "rise", "rise_edge", "old", "never", "fade_ten", "rise_three")})
    trends = {i: h.trend for i, h in got.items.items()}
    assert trends == {
        "fade": "fading",
        "fade_thin": "steady",
        "edge": "steady",
        "rise": "rising",
        "rise_edge": "steady",
        "old": "steady",
        "never": None,
        "fade_ten": "fading",
        "rise_three": "rising",
    }


def test_trend_needs_both_windows_and_new_beats_the_rest():
    led = with_items(spread(20), young={ago(3): cell(5, 1)}, fresh_item={ago(3): cell(5, 1)})
    led["items"][H("fresh_item")]["first_seen"] = ago(30)
    led["items"][H("young")]["first_seen"] = ago(31)
    got = profile(led, {"young": "skill", "fresh_item": "skill", "unused": "skill"})
    assert (got.items["young"].trend, got.items["fresh_item"].trend, got.items["unused"].trend) == ("steady", "new", None)
    led["items"][H("unused")] = {"first_seen": TODAY, "days": {}}
    assert profile(led, {"unused": "skill"}).items["unused"].trend == "new"


def test_decayed_use_halves_every_60_days_and_ignores_the_future_and_unknown_items():
    led = with_items(
        {}, a={TODAY: cell(5, 2), ago(60): cell(1, 4), ago(120): cell(1, 4), "2026-11-09": cell(1, 99)}, other={TODAY: cell(1, 1)}
    )
    got = profile(led, {"a": "skill"})
    assert set(got.items) == {"a"}
    assert got.items["a"].decayed_use == 5.0 and got.items["a"].all_time == 7


def test_percentile_is_rank_among_the_same_kind_with_ties_sharing_the_lower_rank():
    led = with_items({}, a={TODAY: cell(1, 4)}, b={TODAY: cell(1, 1)}, c={TODAY: cell(1, 1)}, d={TODAY: cell(1, 9)})
    got = profile(led, {"a": "skill", "b": "skill", "c": "skill", "d": "agent", "e": "skill"})
    assert {i: h.percentile for i, h in got.items.items()} == {"a": 75, "b": 25, "c": 25, "d": 0, "e": 0}


def test_projects_used_and_the_top_share():
    led = with_items({}, a={ago(1): cell(4, 1, x=3, y=1), ago(2): cell(2, 1, x=1, z=0)}, b={}, c={ago(1): cell(1, 1)})
    got = profile(led, {"a": "skill", "b": "skill", "c": "skill"}).items
    assert (got["a"].projects_used, got["a"].top_project_share) == (2, 4 / 5)
    assert (got["b"].projects_used, got["b"].top_project_share) == (0, 0.0)
    assert (got["c"].projects_used, got["c"].top_project_share) == (0, 0.0)


def test_active_days_and_projects_active_in_the_last_30_days():
    led = ledger(days={ago(31): day(1, old=1), ago(30): day(1, edge=1), ago(1): day(2, edge=1, new=1), "2026-11-09": day(1, future=1)})
    got = profile(led, {})
    assert (got.active_days, got.projects_active) == (3, 2)


def test_co_use_partners_need_lift_two_and_three_sessions_each():
    uses = {"a": 3, "b": 4, "c": 5, "d": 2, "e": 3, "f": 5, "g": 3}
    days = {f"2026-11-0{n}": day(2) for n in range(1, 6)}  # 10 sessions
    led = ledger(days=days, items={H(i): {"first_seen": "2025-01-01", "days": {"2026-11-01": cell(s, s)}} for i, s in uses.items()})
    led["co"] = {
        pair("a", "b"): {"2026-11": 3},  # 3*10/(3*4) = 2.5
        pair("a", "c"): {"2026-11": 1},  # 0.67
        pair("a", "d"): {"2026-11": 2},  # d has 2 sessions
        pair("a", "e"): {"2026-10": 1, "2026-11": 2},  # 3.33
        pair("a", "f"): {"2026-11": 3},  # exactly 2.0
        pair("a", "x"): {"2026-11": 3},  # x is not tracked
        pair("g", "c"): {"2026-11": 1},  # 0.67
    }
    got = profile(led, {i: "skill" for i in uses}).items
    assert got["a"].co_used == (("e", 3.33), ("b", 2.5), ("f", 2.0))
    assert got["b"].co_used == (("a", 2.5),) and got["d"].co_used == () and got["c"].co_used == ()


# file IO


def valid():
    return ledger(
        days={"2026-10-01": day(2, aaaaaa=1)},
        items={H("a"): {"first_seen": "2026-10-01", "days": {"2026-10-01": cell(2, 1, aaaaaa=2)}}},
        co={pair("a", "b"): {"2026-10": 2}},
    )


def test_save_then_load_round_trips_with_a_private_file_in_a_private_directory(tmp_path):
    path = tmp_path / "cache" / "habits.json"
    habits.save(path, {"setup": valid()})
    assert habits.load(path) == ({"setup": valid()}, None)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600 and stat.S_IMODE(os.stat(path.parent).st_mode) == 0o700
    os.chmod(path.parent, 0o755)
    habits.save(path, {})
    assert stat.S_IMODE(os.stat(path.parent).st_mode) == 0o700 and os.listdir(path.parent) == ["habits.json"]


def test_a_failed_save_leaves_the_old_file_and_no_temporary_file(tmp_path, monkeypatch):
    path = tmp_path / "habits.json"
    habits.save(path, {"setup": valid()})
    monkeypatch.setattr(os, "replace", lambda *a: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError):
        habits.save(path, {})
    assert os.listdir(tmp_path) == ["habits.json"] and "setup" in json.loads(path.read_text())["setups"]


def test_a_missing_file_is_empty_without_a_warning(tmp_path):
    assert habits.load(tmp_path / "none.json") == ({}, None)


@pytest.mark.parametrize(
    "text", ["", "{", "[]", "null", '{"version": 2, "setups": {}}', '{"version": 1}', '{"version": 1, "setups": []}', "[" * 100000]
)
def test_an_unreadable_file_starts_over_with_a_warning(tmp_path, text):
    path = tmp_path / "habits.json"
    path.write_text(text)
    assert habits.load(path) == ({}, "habit ledger could not be read; starting it over")


def test_a_directory_in_place_of_the_file_is_unreadable_not_a_crash(tmp_path):
    assert habits.load(tmp_path)[1] == "habit ledger could not be read; starting it over"


def broken(change):
    def apply(r):
        change(r)
        return r

    return apply


BAD = {
    "extra key": lambda r: r.update(more=1),
    "short salt": lambda r: r.update(salt="ab" * 31),
    "non-hex salt": lambda r: r.update(salt="zz" * 32),
    "upper-case X salt": lambda r: r.update(salt="XX" * 32),
    "salt type": lambda r: r.update(salt=5),
    "days list": lambda r: r.update(days=[]),
    "day text": lambda r: r["days"].update({"20261001": day(1)}),
    "day not a day": lambda r: r["days"].update({"2026-13-01": day(1)}),
    "day type": lambda r: r["days"].update({"2026-10-02": 5}),
    "day keys": lambda r: r["days"]["2026-10-01"].update(more=1),
    "sessions negative": lambda r: r["days"]["2026-10-01"].update(sessions=-1),
    "sessions bool": lambda r: r["days"]["2026-10-01"].update(sessions=True),
    "projects value": lambda r: r["days"]["2026-10-01"]["projects"].update(p=1.5),
    "projects negative": lambda r: r["days"]["2026-10-01"]["projects"].update(p=-1),
    "projects list": lambda r: r["days"]["2026-10-01"].update(projects=[]),
    "items list": lambda r: r.update(items=[]),
    "item type": lambda r: r["items"].update(x=5),
    "item keys": lambda r: r["items"][H("a")].update(more=1),
    "first_seen": lambda r: r["items"][H("a")].update(first_seen="soon"),
    "item days list": lambda r: r["items"][H("a")].update(days=[]),
    "cell day": lambda r: r["items"][H("a")]["days"].update({"x": cell(1, 1)}),
    "cell keys": lambda r: r["items"][H("a")]["days"]["2026-10-01"].update(more=1),
    "cell n": lambda r: r["items"][H("a")]["days"]["2026-10-01"].update(n="2"),
    "cell s negative": lambda r: r["items"][H("a")]["days"]["2026-10-01"].update(s=-1),
    "cell p": lambda r: r["items"][H("a")]["days"]["2026-10-01"].update(p={"x": "1"}),
    "co list": lambda r: r.update(co=[]),
    "co value": lambda r: r["co"].update(k=5),
    "co count": lambda r: r["co"][pair("a", "b")].update({"2026-10": "2"}),
    "co month": lambda r: r["co"][pair("a", "b")].update({"2026-13": 2}),
}


@pytest.mark.parametrize("name", BAD)
def test_a_malformed_record_is_dropped_with_a_warning_and_the_others_are_kept(tmp_path, name):
    bad = valid()
    BAD[name](bad)
    path = tmp_path / "habits.json"
    path.write_text(json.dumps({"version": 1, "setups": {"good": valid(), "bad": bad}}))
    assert habits.load(path) == ({"good": valid()}, "part of the habit ledger could not be read; starting that part over")


def test_a_valid_record_with_a_non_string_key_cannot_exist_in_json_and_new_ledgers_are_random_and_valid():
    one, two = habits.new(), habits.new()
    assert habits._valid(one) and one["salt"] != two["salt"] and len(one["salt"]) == 64
    assert one["days"] == one["items"] == one["co"] == {}


# update: end to end on invented transcripts


@pytest.fixture
def config(tmp_path):
    root = tmp_path / "cfg"
    write_skill(root, "tdd", "invented")
    write_skill(root, "other", "invented")
    put(root, "secret-project-folder", "sess-one.jsonl", [tool(id_="a1"), tool(value="other", id_="a2"), tool(id_="a3", day="2026-11-03")])
    return root


def run(config, path, today=TODAY):
    items, _, relations, _ = read_items(config)
    return habits.update(path, config, items, relations, today)


def load_one(path):
    (record,) = habits.load(path)[0].values()
    return record


def test_update_writes_hashed_counts_only_and_a_rescan_changes_nothing(config, tmp_path):
    path = tmp_path / "cache" / "habits.json"
    assert run(config, path) == []
    first = path.read_text()
    text = first.lower()
    for marker in ("tdd", "other", "secret", "claude-code", "sess-one", str(tmp_path), "skill"):
        assert marker not in text
    record = load_one(path)
    assert record["days"]["2026-11-02"]["sessions"] == 1 and len(record["items"]) == 2
    assert run(config, path) == []
    assert path.read_text() == first
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_history_survives_the_transcripts_being_deleted_and_the_salt_stays(config, tmp_path):
    path = tmp_path / "habits.json"
    run(config, path)
    salt = load_one(path)["salt"]
    (config / "projects" / "secret-project-folder" / "sess-one.jsonl").unlink()
    put(config, "secret-project-folder", "sess-two.jsonl", [tool(id_="b1", day="2026-11-04")])
    run(config, path)
    record = load_one(path)
    assert record["salt"] == salt
    assert sorted(record["days"]) == ["2026-11-02", "2026-11-03", "2026-11-04"]


def test_a_corrupt_file_warns_and_starts_over_and_an_unwritable_one_warns(config, tmp_path):
    path = tmp_path / "habits.json"
    path.write_text("garbage")
    assert run(config, path) == ["habit ledger could not be read; starting it over"]
    assert len(load_one(path)["items"]) == 2
    blocked = tmp_path / "file"
    blocked.write_text("x")
    (warning,) = run(config, blocked / "habits.json")  # the lock file cannot be made under a file either
    assert warning.startswith("could not save habit ledger: ")
    assert str(tmp_path) not in warning


def test_ledgers_of_two_setups_share_the_file_with_separate_salts(config, tmp_path):
    path = tmp_path / "habits.json"
    run(config, path)
    other = tmp_path / "other-cfg"
    write_skill(other, "tdd", "invented")
    run(other, path)
    records = habits.load(path)[0]
    assert len(records) == 2 and len({r["salt"] for r in records.values()}) == 2


# CLI and file mtime


@pytest.fixture
def cli(tmp_path, monkeypatch):
    monkeypatch.setattr("constellation.cli._local_embedder", lambda: None)

    def scan(*extra):
        from fakes import FakeEmbedder

        from constellation.cli import main

        return main(["scan", str(tmp_path / "cfg"), "--out", str(tmp_path / "scan.json"), "--offline", *extra], embedder=FakeEmbedder({}))

    return scan


def test_scan_records_habits_unless_habits_or_usage_is_off(config, cli):
    assert cli("--no-habits") == 0 and not habits.DEFAULT_CACHE.exists()
    assert cli("--no-usage") == 0 and not habits.DEFAULT_CACHE.exists()
    assert cli("--no-history") == 0 and not habits.DEFAULT_CACHE.exists()  # no history means no ledger either
    assert cli() == 0
    assert len(load_one(habits.DEFAULT_CACHE)["items"]) == 2
    assert stat.S_IMODE(os.stat(habits.DEFAULT_CACHE).st_mode) == 0o600


def test_scan_prints_a_ledger_warning_and_still_succeeds(config, cli, capsys):
    habits.DEFAULT_CACHE.parent.mkdir(parents=True, exist_ok=True)
    habits.DEFAULT_CACHE.write_text("garbage")
    assert cli() == 0
    assert "habit ledger could not be read; starting it over" in capsys.readouterr().err


def test_files_carry_the_day_they_were_last_modified_without_being_read(tmp_path):
    from constellation.snapshot import snapshot

    write_skill(tmp_path, "tdd", "invented")
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "helper.md").write_text("---\nname: helper\ndescription: invented\n---\n")
    (tmp_path / "commands").mkdir()
    (tmp_path / "commands" / "go.md").write_text("---\ndescription: invented\n---\n")
    stamps = {
        "skills/tdd/SKILL.md": 1759406400,
        "agents/helper.md": 1759406400 + 86400,
        "commands/go.md": 1759406400 - 86400,
    }  # 2025-10-02 12:00 UTC
    for name, stamp in stamps.items():
        os.utime(tmp_path / name, (stamp, stamp))
    items, _, _, _ = read_items(tmp_path)
    assert {i.name: i.changed_on for i in items} == {"tdd": "2025-10-02", "helper": "2025-10-03", "go": "2025-10-01"}
    from constellation import scan

    assert "changed_on" not in json.dumps(snapshot(asdict(scan(tmp_path))))


# survivors of the first mutation run


def test_zero_counts_are_valid():
    record = valid()
    record["days"]["2026-10-01"] = day(0, aaaaaa=0)
    record["items"][H("a")]["days"]["2026-10-01"] = cell(0, 0, aaaaaa=0)
    assert habits._valid(record)


def test_a_day_equal_to_today_counts_and_a_future_day_anywhere_in_the_list_is_skipped():
    new = fresh(
        {TODAY: 1},
        {TODAY: {}},
        {"a": {TODAY: (1, 1, {})}},
        [("2026-11-09", ("a", "b")), (TODAY, ("a", "b")), (TODAY, ("a", "b"))],
    )
    got = merge(ledger(), new, window(TODAY, TODAY), ["a", "b"])
    assert TODAY in got["days"] and TODAY in got["items"][H("a")]["days"] and got["co"] == {pair("a", "b"): {"2026-11": 2}}


def test_keys_on_only_one_side_survive_a_first_day_maximum():
    old = ledger(days={"2026-10-01": day(1, only_old=2)})
    new = fresh({"2026-10-01": 1}, {"2026-10-01": {"only_new": 3}})
    assert merge(old, new, window("2026-10-01", "2026-10-01"))["days"]["2026-10-01"] == day(1, only_old=2, only_new=3)
    assert habits._max({"a": 0, "c": 0}, {"b": 0, "c": 0}) == {"a": 0, "b": 0, "c": 0}


def test_the_retention_month_itself_is_kept_for_co_use():
    old = ledger(
        items={H("a"): {"first_seen": TODAY, "days": {}}, H("b"): {"first_seen": TODAY, "days": {}}},
        co={pair("a", "b"): {"2025-09": 7, "2025-10": 2}},
    )
    assert merge(old, fresh(), window(), ["a", "b"])["co"] == {pair("a", "b"): {"2025-10": 2}}


def test_percentile_is_an_integer_and_exact():
    led = with_items({}, a={TODAY: cell(1, 4)}, b={TODAY: cell(1, 1)}, c={TODAY: cell(1, 1)})
    got = profile(led, {"a": "skill", "b": "skill", "c": "skill"}).items
    assert got["a"].percentile == 66 and type(got["a"].percentile) is int


def test_decayed_use_is_rounded_to_six_places():
    got = profile(with_items({}, a={ago(30): cell(1, 2)}), {"a": "skill"}).items["a"]
    assert got.decayed_use == 1.414214


def test_equal_lift_partners_are_listed_by_id():
    days = {f"2026-11-0{n}": day(2) for n in range(1, 6)}
    led = ledger(days=days, items={H(i): {"first_seen": "2025-01-01", "days": {"2026-11-01": cell(3, 3)}} for i in ("a", "h", "e")})
    led["co"] = {pair("a", "h"): {"2026-11": 3}, pair("a", "e"): {"2026-11": 3}}
    assert [p for p, _ in profile(led, {"a": "skill", "e": "skill", "h": "skill"}).items["a"].co_used] == ["e", "h"]


def test_save_writes_its_temporary_file_beside_the_target(tmp_path, monkeypatch):
    seen = []
    real = os.replace
    monkeypatch.setattr(os, "replace", lambda src, dst: (seen.append(src), real(src, dst)))
    habits.save(tmp_path / "habits.json", {})
    assert os.path.dirname(seen[0]) == str(tmp_path) and os.path.basename(seen[0]).startswith(".habits-")


def test_only_tracked_kinds_get_a_record_even_when_unused(config, tmp_path):
    (config / "commands").mkdir()
    (config / "commands" / "go.md").write_text("---\ndescription: invented\n---\n")
    write_skill(config, "idle", "invented")
    run(config, tmp_path / "habits.json")
    record = load_one(tmp_path / "habits.json")
    assert set(record["items"]) == {mac(record["salt"], f"claude-code:skill:{n}", 12) for n in ("tdd", "other", "idle")}


# the learner: posterior, gaps, priors, dependencies, project shares


@pytest.mark.parametrize(
    ("used", "total", "prior", "want"),
    [
        (0, 0, 0.5, (0.5, 0.0251, 0.9749)),
        (3, 4, 0.5, (0.6667, 0.3736, 0.9598)),
        (0, 100, 0.5, (0.0098, 0.0, 0.0258)),
        (100, 100, 0.5, (0.9902, 0.9742, 1.0)),
        (0, 10, 0.3, (0.05, 0.0, 0.1494)),
        (6, 5, 0.5, (0.875, 0.6937, 1.0)),  # more uses than sessions cannot make the failure count negative
    ],
)
def test_the_posterior_widens_with_little_history_and_stays_within_zero_and_one(used, total, prior, want):
    assert habits._beta(used, total, prior) == want


def test_little_history_gives_a_wide_interval_and_much_history_a_narrow_one():
    few = profile(with_items({TODAY: day(2)}, a={TODAY: cell(1, 1)}), {"a": "skill"}).items["a"]
    many = profile(with_items({TODAY: day(200)}, a={TODAY: cell(100, 100)}), {"a": "skill"}).items["a"]
    assert (few.use_prob, few.prob_low, few.prob_high) == pytest.approx((0.5, 0.1322, 0.8678), abs=1e-4)
    assert many.prob_high - many.prob_low < 0.15 < few.prob_high - few.prob_low
    assert (many.prior_prob, many.prior_from) == (None, None)


def gaps(spread_days, use):
    led = with_items(spread_days, x={d: cell(1, 1) for d in use})
    item = profile(led, {"x": "skill"}).items["x"]
    return item.typical_gap, item.idle_active_days, item.overdue


def test_overdue_needs_idle_time_beyond_three_typical_gaps_counted_in_active_days():
    use = lambda *idx, n: [ago(n - 1 - i) for i in idx]  # noqa: E731  (positions in an n-day history)
    assert gaps(spread(11), use(0, 2, 4, n=11)) == (2.0, 6, False)  # idle 6 is not more than 3 * 2
    assert gaps(spread(12), use(0, 2, 4, n=12)) == (2.0, 7, True)
    assert gaps(spread(30), use(0, 2, n=30)) == (None, 27, False)  # two use days: no typical gap, so never overdue
    assert gaps(spread(30), use(0, 2, 5, 6, n=30))[0] == 2.0  # median of 2, 3, 1
    assert gaps(spread(5), []) == (None, None, False)


def test_quiet_days_are_not_idleness():
    sparse = {ago(40): day(1), ago(30): day(1), ago(20): day(1), ago(1): day(1)}
    assert gaps(sparse, [ago(40), ago(30), ago(20)]) == (1.0, 1, False)


def prior_ledger():
    led = ledger(days={TODAY: day(10)})
    for name, s in (("a", 5), ("b", 1), ("c", 3)):
        led["items"][H(name)] = {"first_seen": "2025-01-01", "days": {TODAY: cell(s, s)}}
    return led


def test_an_item_without_history_borrows_a_prior_from_its_group_then_its_kind_and_says_so():
    kinds = {"a": "skill", "b": "skill", "c": "skill", "d": "skill", "e": "agent", "f": "skill"}
    got = profile(prior_ledger(), kinds, {"d": "plug", "b": "plug", "c": "plug"}).items
    assert (got["d"].prior_prob, got["d"].prior_from) == (0.2, "group")  # (0.1 + 0.3) / 2
    assert (got["f"].prior_prob, got["f"].prior_from) == (0.3, "kind")  # (0.5 + 0.1 + 0.3) / 3
    assert (got["e"].prior_prob, got["e"].prior_from) == (None, None)  # no agent has history: uniform
    assert got["f"].use_prob == pytest.approx(0.05, abs=1e-4) and got["e"].use_prob == pytest.approx(0.0833, abs=1e-4)
    assert got["a"].prior_prob is None  # an Item with history is judged on its own evidence


def test_a_group_with_one_neighbour_is_too_small_and_the_kind_is_used():
    kinds = {"a": "skill", "b": "skill", "c": "skill", "d": "skill"}
    got = profile(prior_ledger(), kinds, {"d": "plug", "a": "plug"}).items
    assert (got["d"].prior_prob, got["d"].prior_from) == (0.3, "kind")
    thin = profile(prior_ledger(), {"a": "skill", "b": "skill", "d": "skill"}).items["d"]
    assert (thin.prior_prob, thin.prior_from) == (0.3, "kind")  # two neighbours is enough
    one = profile(prior_ledger(), {"a": "skill", "d": "skill"}).items["d"]
    assert (one.prior_prob, one.prior_from) == (None, None)  # one is not


def test_one_way_dependencies_need_nine_in_ten_sessions_and_three_shared():
    sessions_ = {"x": 10, "y": 9, "z": 8, "w": 3, "v": 2, "u": 12}
    led = ledger(
        days={TODAY: day(20)}, items={H(i): {"first_seen": "2025-01-01", "days": {TODAY: cell(s, s)}} for i, s in sessions_.items()}
    )
    led["co"] = {
        pair("x", "u"): {"2026-11": 9},
        pair("y", "u"): {"2026-11": 8},
        pair("w", "u"): {"2026-11": 3},
        pair("v", "u"): {"2026-11": 2},
    }
    got = profile(led, {i: "skill" for i in sessions_}).items
    assert got["x"].needs == (("u", 0.9),)  # 9 of 10: exactly the share
    assert got["y"].needs == ()  # 8 of 9 is below it
    assert got["w"].needs == (("u", 1.0),)  # three shared sessions is enough
    assert got["v"].needs == ()  # two is not
    assert got["u"].needs == ()  # u does not need its dependants


def test_project_shares_are_hashed_largest_first_with_ties_by_hash():
    led = with_items({}, a={ago(1): cell(4, 1, zz=3, aa=1), ago(2): cell(3, 1, mm=3)}, b={})
    got = profile(led, {"a": "skill", "b": "skill"}).items
    assert got["a"].project_shares == (("mm", 0.4286), ("zz", 0.4286), ("aa", 0.1429))
    assert got["b"].project_shares == ()


def test_profile_of_500_items_is_fast():
    import time

    days = {ago(i): day(3) for i in range(0, 120, 2)}
    items = {H(f"i{n}"): {"first_seen": "2025-01-01", "days": {ago(i): cell(2, 1, p=2) for i in range(n % 7, 120, 7)}} for n in range(500)}
    led = ledger(days=days, items=items)
    start = time.perf_counter()
    got = profile(led, {f"i{n}": "skill" for n in range(500)})
    assert len(got.items) == 500 and time.perf_counter() - start < 0.5


# survivors of the second mutation run


def test_history_beyond_the_recent_window_still_means_no_borrowed_prior():
    led = prior_ledger()
    led["days"] = {**spread(60), TODAY: day(10)}
    led["items"][H("d")] = {"first_seen": "2025-01-01", "days": {ago(50): cell(1, 1)}}
    got = profile(led, {"a": "skill", "b": "skill", "c": "skill", "d": "skill"}).items["d"]
    assert (got.prior_prob, got.prior_from) == (None, None)
    assert got.all_time == 1 and got.use_prob == 0.0286  # uniform prior, not the neighbours' mean


def test_an_item_with_history_uses_the_uniform_prior():
    kinds = {"a": "skill", "b": "skill", "c": "skill"}
    assert profile(prior_ledger(), kinds).items["a"].use_prob == 0.5  # (1 + 5) / (2 + 10), not its neighbours' mean


def test_zero_count_days_are_not_use_days():
    led = with_items(spread(10), x={ago(9): cell(1, 1), ago(7): cell(1, 1), ago(5): cell(1, 1), ago(1): cell(0, 0)})
    item = profile(led, {"x": "skill"}).items["x"]
    assert (item.typical_gap, item.idle_active_days) == (2.0, 5)


def test_old_sessions_weigh_less_in_the_denominator():
    led = ledger(days={TODAY: day(2), ago(60): day(2)}, items={H("a"): {"first_seen": "2025-01-01", "days": {TODAY: cell(1, 1)}}})
    assert profile(led, {"a": "skill"}).items["a"].use_prob == 0.4  # 1 use in 2 + 1 weighted sessions, prior 0.5


def test_dependencies_ignore_unknown_partners_round_to_two_places_and_sort_by_share_then_id():
    uses = {"x": 15, "p": 20, "q": 20, "r": 20, "s": 20}
    led = ledger(days={TODAY: day(30)}, items={H(i): {"first_seen": "2025-01-01", "days": {TODAY: cell(s, s)}} for i, s in uses.items()})
    led["co"] = {
        pair("x", "unknown"): {"2026-11": 15},
        pair("x", "q"): {"2026-11": 15},
        pair("x", "p"): {"2026-11": 14},
        pair("x", "s"): {"2026-11": 14},
        pair("x", "r"): {"2026-11": 14},
    }
    got = profile(led, {i: "skill" for i in uses}).items["x"]
    assert got.needs == (("q", 1.0), ("p", 0.93), ("r", 0.93), ("s", 0.93))


def test_the_file_is_written_with_sorted_keys(tmp_path):
    habits.save(tmp_path / "h.json", {"b": ledger(), "a": ledger()})
    text = (tmp_path / "h.json").read_text()
    assert text.index('"a"') < text.index('"b"') and text.index('"co"') < text.index('"days"') < text.index('"items"') < text.index(
        '"salt"'
    )


def test_the_borrowed_prior_is_rounded_to_four_places():
    led = ledger(
        days={TODAY: day(10)},
        items={H(i): {"first_seen": "2025-01-01", "days": {TODAY: cell(s, s)}} for i, s in (("a", 1), ("b", 1), ("c", 2))},
    )
    got = profile(led, {i: "skill" for i in "abcd"}).items["d"]
    assert got.prior_prob == 0.1333


# privacy review fixes


def test_a_clock_far_ahead_does_not_wipe_the_ledger():
    old = ledger(days={"2026-09-01": day(3), "2026-10-02": day(2)})
    new = fresh({"2026-10-02": 2}, {"2026-10-02": {}})
    got = merge(old, new, window("2026-10-02", "2026-10-02"), [], "2028-11-05")
    assert got["days"] == old["days"]  # retention counts from the newest evidence, not from the clock


def test_a_clock_behind_the_transcripts_keeps_the_days_it_cannot_write_back():
    old = ledger(days={"2026-10-01": day(1), "2026-10-02": day(2), "2026-10-06": day(5)})
    new = fresh({"2026-10-01": 1, "2026-10-02": 9, "2026-10-06": 9}, {d: {} for d in ("2026-10-01", "2026-10-02", "2026-10-06")})
    got = merge(old, new, window("2026-10-01", "2026-10-06"), [], "2026-10-03")
    assert got["days"] == {"2026-10-01": day(1), "2026-10-02": day(9), "2026-10-06": day(5)}  # the 6th is after "today": untouched


def test_unreadable_transcripts_never_lower_stored_days():
    old = ledger(days={"2026-10-01": day(4), "2026-10-02": day(8, aaaaaa=8)}, co={pair("a", "b"): {"2026-10": 5}})
    old["items"] = {
        H("a"): {"first_seen": "2026-10-01", "days": {"2026-10-02": cell(8, 8)}},
        H("b"): {"first_seen": "2026-10-01", "days": {}},
    }
    new = fresh({"2026-10-02": 1}, {"2026-10-02": {"aaaaaa": 1}}, {"a": {"2026-10-02": (1, 1, {})}}, [("2026-10-02", ("a", "b"))])
    skipped = UsageWindow(1, "2026-10-01", "2026-10-03", 1, 1)
    got = merge(old, new, skipped, ["a", "b"])
    assert got["days"] == old["days"] and got["items"][H("a")]["days"] == {"2026-10-02": cell(8, 8)} and got["co"] == old["co"]


BAD_ENTRIES = {
    "item key": lambda r: r["items"].update({"not-hex": r["items"].pop(H("a"))}),
    "project key": lambda r: r["days"]["2026-10-01"]["projects"].update({"toolongproject": 1}),
    "pair without a bar": lambda r: r["co"].update({"a" * 24: {"2026-10": 2}}),
    "pair of odd length": lambda r: r["co"].update({"a" * 12 + "|" + "b" * 11: {"2026-10": 2}}),
    "huge count": lambda r: r["days"]["2026-10-01"].update(sessions=2**53),
    "huge co count": lambda r: r["co"][pair("a", "b")].update({"2026-10": 2**80}),
}


@pytest.mark.parametrize("name", BAD_ENTRIES)
def test_keys_must_be_hashes_and_counts_below_two_to_the_53rd(tmp_path, name):
    bad = valid()
    BAD_ENTRIES[name](bad)
    assert not habits._valid(bad)
    assert habits._valid({**valid(), "days": {"2026-10-01": day(2**53 - 1)}})


def test_profile_survives_a_pair_whose_item_has_no_sessions():
    led = with_items({TODAY: day(5)}, a={ago(1): cell(0, 0)}, b={TODAY: cell(4, 4)})
    led["co"] = {pair("a", "b"): {"2026-11": 4}}
    got = profile(led, {"a": "skill", "b": "skill"}).items
    assert got["a"].needs == ()


def test_load_refuses_a_symlink_a_huge_file_and_a_fifo(tmp_path, monkeypatch):
    real = tmp_path / "real.json"
    habits.save(real, {"s": valid()})
    link = tmp_path / "link.json"
    link.symlink_to(real)
    assert habits.load(link) == ({}, "habit ledger could not be read; starting it over")
    monkeypatch.setattr(habits, "MAX_FILE", 10)
    assert habits.load(real)[1] == "habit ledger could not be read; starting it over"
    monkeypatch.setattr(habits, "MAX_FILE", real.stat().st_size)
    assert habits.load(real)[1] is None  # exactly the cap is allowed


def test_two_scans_at_once_take_turns(config, tmp_path):
    import fcntl
    import threading
    import time

    path = tmp_path / "habits.json"
    habits.save(path, {})
    lock = os.open(str(path) + ".lock", os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX)
    done = threading.Event()
    worker = threading.Thread(target=lambda: (run(config, path), done.set()))
    worker.start()
    time.sleep(0.3)
    assert not done.is_set()  # waiting for the first scan
    fcntl.flock(lock, fcntl.LOCK_UN)
    os.close(lock)
    worker.join(10)
    assert done.is_set() and stat.S_IMODE(os.stat(str(path) + ".lock").st_mode) == 0o600
