import json

from fakes import write_skill
from test_usage import tool

from constellation.claude_code import read_items
from constellation.usage import Fresh, mac, read_fresh, read_usage

SALT = "ab" * 32
TDD, OTHER = "claude-code:skill:tdd", "claude-code:skill:other"


def put(config, folder, name, records):
    path = config / "projects" / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records))


def build(tmp_path):
    write_skill(tmp_path, "tdd", "invented")
    write_skill(tmp_path, "other", "invented")
    put(tmp_path, "alpha", "s1.jsonl", [tool(id_="a1"), tool(value="other", id_="a2"), tool(id_="a3", day="2026-11-03")])
    put(tmp_path, "alpha", "s1/subagents/x.jsonl", [tool(id_="a4", day="2026-11-03")])  # same session as s1.jsonl
    put(tmp_path, "beta", "s2.jsonl", [tool(id_="b1"), {"type": "user", "message": {"content": "undated"}}])
    put(tmp_path, "beta", "s3.jsonl", [tool(value="absent", id_="b2", day="2026-11-04")])  # a session with no tracked Item
    items, _, relations, _ = read_items(tmp_path)
    return items, relations


def test_fresh_has_per_day_sessions_projects_items_and_co(tmp_path):
    items, relations = build(tmp_path)
    fresh, window = read_fresh(tmp_path, items, relations, SALT)
    alpha, beta = mac(SALT, "alpha", 6), mac(SALT, "beta", 6)
    assert fresh.sessions == {"2026-11-02": 2, "2026-11-03": 1, "2026-11-04": 1}
    assert fresh.projects == {"2026-11-02": {alpha: 1, beta: 1}, "2026-11-03": {alpha: 1}, "2026-11-04": {beta: 1}}
    assert fresh.items == {
        TDD: {"2026-11-02": (2, 2, {alpha: 1, beta: 1}), "2026-11-03": (2, 1, {alpha: 2})},
        OTHER: {"2026-11-02": (1, 1, {alpha: 1})},
    }
    assert fresh.co == [("2026-11-03", (OTHER, TDD))]  # the day is the session's last invocation; s2 used only one Item
    assert (window.files, window.sessions, window.first, window.last) == (4, 3, "2026-11-02", "2026-11-04")
    assert len(alpha) == len(beta) == 6


def test_fresh_holds_no_folder_names_and_the_salt_changes_every_hash(tmp_path):
    items, relations = build(tmp_path)
    one, _ = read_fresh(tmp_path, items, relations, SALT)
    two, _ = read_fresh(tmp_path, items, relations, "cd" * 32)
    assert "alpha" not in repr(one) and "beta" not in repr(one) and "s1" not in repr(one)
    assert set(one.projects["2026-11-04"]) != set(two.projects["2026-11-04"])
    assert mac("k", "alpha", 3) == mac("k", "alpha", 12)[:3] and mac("k", "alpha", 12) != mac("j", "alpha", 12)


def test_read_usage_keeps_its_shape_and_makes_no_ledger_data(tmp_path):
    items, relations = build(tmp_path)
    usage, window, warnings, _ = read_usage(tmp_path, items, relations)
    assert usage[TDD].count == 4 and window.sessions == 3 and warnings == []


def test_a_session_split_across_two_projects_counts_twice_and_missing_projects_are_empty(tmp_path):
    write_skill(tmp_path, "tdd", "invented")
    items, _, relations, _ = read_items(tmp_path)
    assert read_fresh(tmp_path, items, relations, SALT)[0] == Fresh({}, {}, {}, [])
    put(tmp_path, "alpha", "same.jsonl", [tool(id_="a1")])
    put(tmp_path, "beta", "same.jsonl", [tool(id_="b1")])
    fresh, window = read_fresh(tmp_path, items, relations, SALT)
    assert fresh.sessions == {"2026-11-02": 2} and window.sessions == 2


def test_a_symlinked_projects_folder_yields_nothing(tmp_path):
    write_skill(tmp_path, "tdd", "invented")
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "projects").symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    items, _, relations, _ = read_items(tmp_path)
    fresh, window = read_fresh(tmp_path, items, relations, SALT)
    assert fresh == Fresh({}, {}, {}, []) and window.skipped == 1


def test_co_use_is_per_session_and_keeps_each_items_latest_day(tmp_path):
    write_skill(tmp_path, "tdd", "invented")
    write_skill(tmp_path, "other", "invented")
    put(tmp_path, "alpha", "s1.jsonl", [tool(id_="a1", day="2026-11-03"), tool(id_="a2", day="2026-11-02"), tool(value="other", id_="a3")])
    put(tmp_path, "alpha", "s2.jsonl", [tool(id_="b1", day="2026-11-04"), tool(value="other", id_="b2", day="2026-11-04")])
    items, _, relations, _ = read_items(tmp_path)
    fresh, _ = read_fresh(tmp_path, items, relations, SALT)
    assert fresh.co == [("2026-11-03", (OTHER, TDD)), ("2026-11-04", (OTHER, TDD))]


def test_two_folders_with_the_same_hash_add_up(tmp_path, monkeypatch):
    items, relations = build(tmp_path)
    monkeypatch.setattr("constellation.usage.mac", lambda salt, text, length: "c" * length)
    fresh, _ = read_fresh(tmp_path, items, relations, SALT)
    assert fresh.projects["2026-11-02"] == {"cccccc": 2}
    assert fresh.items[TDD]["2026-11-02"] == (2, 2, {"cccccc": 2})
    assert fresh.items[TDD]["2026-11-03"] == (2, 1, {"cccccc": 2})
