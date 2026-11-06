import json

from constellation import cli, habits, history
from constellation import purge as pg
from constellation.usage import mac

SALT = "a" * 64
TODAY = "2026-11-06"
DEAD, DEAD2, LIVE = "-tmp-dead", "-tmp-dead2", "-tmp-live"
OLD = "2026-01-01"


def pk(f):
    return mac(SALT, f, 6)


def iid(n, kind="skill"):
    return f"x:{kind}:global:{n}"


def days(dead_day="2026-08-01", live_day="2026-11-01"):
    return {
        dead_day: {"sessions": 2, "projects": {pk(DEAD): 1, pk(DEAD2): 1}},
        live_day: {"sessions": 1, "projects": {pk(LIVE): 1}},
    }


def use(**per):
    return {"2026-07-01": {"n": sum(per.values()), "s": 1, "p": {pk(f): n for f, n in per.items() if n}}}


def ledger(items, d=None):
    recs = {mac(SALT, iid(n), 12): {"first_seen": fs, "days": u} for n, (fs, u) in items.items()}
    return {"salt": SALT, "days": d or days(), "items": recs, "co": {}}


def rows(*names, kind="skill", **extra):
    return [{"id": iid(n, kind), "kind": kind, "name": n, **extra} for n in names]


def run(led, items, costs=None, pinned=frozenset(), today=TODAY):
    return pg.build(led, today, items, costs or {}, pinned)


def dead_use(n=1):
    return {"2026-07-01": {"n": n, "s": 1, "p": {pk(DEAD): n}}}


def test_only_idle_use_is_a_candidate_with_tokens_and_reason():
    led = ledger({"old": (OLD, {"2026-07-01": {"n": 4, "s": 1, "p": {pk(DEAD): 3, pk(DEAD2): 1}}})})
    out = run(led, rows("old"), {iid("old"): {"always_on": 120}})
    assert out["candidates"] == [
        {
            "name": "old", "kind": "skill", "tokens": 120, "idle_projects": 2, "idle_since": "2026-08-01",
            "why": "only used in 2 idle projects, none active since 2026-08-01",
        }
    ]  # fmt: skip
    assert out["tokens_saved"] == 120 and out["idle_days"] == 60
    assert run(ledger({"old": (OLD, dead_use())}), rows("old"))["candidates"][0]["why"].startswith("only used in 1 idle project,")


def test_protected_and_unjudgeable_items_are_never_candidates():
    mixed = {"2026-07-01": {"n": 4, "s": 1, "p": {pk(DEAD): 3, pk(LIVE): 1}}}
    led = ledger(
        {
            "mixed": (OLD, mixed),
            "new": ("2026-10-20", dead_use()),
            "edge": ("2026-10-07", dead_use()),  # exactly 30 days old: still too new
            "pinned": (OLD, dead_use()),
            "unused": (OLD, {}),
            "dis": (OLD, dead_use()),
            "proj": (OLD, dead_use()),
            "cmd": (OLD, dead_use()),
        }
    )
    items = rows("mixed", "new", "edge", "pinned", "unused", "norecord") + rows("dis", disabled=True) + rows("proj", scope="project")
    items += rows("cmd", kind="command")
    assert run(led, items, pinned=frozenset({iid("pinned")}))["candidates"] == []
    assert len(run(led, rows("edge"), today="2026-11-07")["candidates"]) == 1  # 31 days old


def test_unknown_project_counts_as_active_and_boundary_is_strict():
    ghost = {"2026-07-01": {"n": 2, "s": 1, "p": {pk("-tmp-ghost"): 2}}}
    assert run(ledger({"a": (OLD, ghost)}), rows("a"))["candidates"] == []
    edge = ledger({"a": (OLD, dead_use())}, days("2026-09-07"))  # exactly 60 days idle: not yet idle
    assert run(edge, rows("a"))["candidates"] == []
    assert run(edge, rows("a"), today="2026-11-07")["candidates"][0]["idle_since"] == "2026-09-07"


def test_future_days_and_zero_counts_are_ignored():
    d = days()
    d["2026-12-01"] = {"sessions": 1, "projects": {pk(DEAD): 1}}  # a future session must not revive the project
    d["2026-07-02"] = {"sessions": 0, "projects": {pk(LIVE): 0}}  # a zero count is not activity
    u = dead_use(2)
    u["2026-12-01"] = {"n": 1, "s": 1, "p": {pk(LIVE): 1}}
    u["2026-07-02"] = {"n": 0, "s": 0, "p": {pk(LIVE): 0}}
    assert len(run(ledger({"a": (OLD, u)}, d), rows("a"))["candidates"]) == 1


def test_sorted_by_tokens_unknown_costs_and_render():
    names = ("b", "a", "c", "d")
    led = ledger({n: (OLD, dead_use()) for n in names})
    costs = {iid("c"): {"always_on": 50}, iid("a"): {"always_on": True}, iid("b"): {"always_on": 50}}
    out = run(led, rows(*names), costs)
    assert [(r["name"], r["tokens"]) for r in out["candidates"]] == [("b", 50), ("c", 50), ("a", None), ("d", None)]
    assert out["tokens_saved"] == 100
    text = pg.render(out)
    assert (
        "4 Item(s)" in text
        and "100 tokens every session" in text
        and "a (skill): unknown tokens" in text
        and "b (skill): 50 tokens" in text
    )
    assert "Nothing was changed" in text and "more" not in text
    assert pg.render({"candidates": [], "tokens_saved": 0, "idle_days": 60}) == (
        "Nothing to purge: no Item is used only by projects idle for more than 60 days."
    )


def test_render_truncates_long_lists():
    names = [f"s{n:02d}" for n in range(pg.SHOWN + 2)]
    led = ledger({n: (OLD, dead_use()) for n in names})
    text = pg.render(run(led, rows(*names)))
    assert "...and 2 more (see --json)" in text and "s14" in text and "s15" not in text


def test_cli_prints_without_project_labels(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(history, "_today", lambda: TODAY)
    monkeypatch.setattr(pg.pins, "DEFAULT_CACHE", tmp_path / "pins.json")
    path = tmp_path / "h.json"
    habits.save(path, {"setup1": ledger({"old": (OLD, dead_use(3))})})
    scan = tmp_path / "c.json"
    scan.write_text(json.dumps({"setup": "setup1", "items": rows("old"), "costs": {iid("old"): {"always_on": 7}}}))
    assert cli.main(["purge", str(scan), "--habits", str(path), "--json"]) == 0
    out = capsys.readouterr().out
    assert json.loads(out)["tokens_saved"] == 7
    assert DEAD not in out and pk(DEAD) not in out and SALT not in out
    assert cli.main(["purge", str(scan), "--habits", str(path), "--dry-run"]) == 0
    assert "old (skill): 7 tokens" in capsys.readouterr().out
    assert cli.main(["purge", str(scan), "--habits", str(tmp_path / "none.json")]) == 2
    assert "No habit ledger" in capsys.readouterr().err
    assert cli.main(["purge", str(tmp_path / "missing.json"), "--habits", str(path)]) == 2


def test_today_counts_and_last_activity_is_the_latest_day():
    d = {"2026-11-06": {"sessions": 1, "projects": {pk(DEAD): 1}}, "2026-01-01": {"sessions": 1, "projects": {pk(DEAD): 1}}}
    assert run(ledger({"a": (OLD, dead_use())}, d), rows("a"))["candidates"] == []  # a session today makes it active
    d = {"2026-08-05": {"sessions": 1, "projects": {pk(DEAD): 1}}, "2026-08-01": {"sessions": 1, "projects": {pk(DEAD): 1}}}
    assert run(ledger({"a": (OLD, dead_use())}, d), rows("a"))["candidates"][0]["idle_since"] == "2026-08-05"
    u = {"2026-11-06": {"n": 1, "s": 1, "p": {pk(LIVE): 1}}, **dead_use()}  # a use today in a live project protects the Item
    assert run(ledger({"a": (OLD, u)}), rows("a"))["candidates"] == []


def test_skipped_items_do_not_stop_the_scan():
    led = ledger({"new": ("2026-11-01", dead_use()), "a": (OLD, {}), "pin": (OLD, dead_use()), "z": (OLD, dead_use())})
    items = rows("norecord") + rows("p", scope="project")
    items += rows("dis", disabled=True) + rows("cmd", kind="command") + rows("new", "pin", "a", "z")
    assert [r["name"] for r in run(led, items, pinned=frozenset({iid("pin")}))["candidates"]] == ["z"]


def test_one_token_ranks_above_unknown():
    led = ledger({"a": (OLD, dead_use()), "z": (OLD, dead_use())})
    out = run(led, rows("a", "z"), {iid("z"): {"always_on": 1}})
    assert [r["name"] for r in out["candidates"]] == ["z", "a"]


def test_render_exact_text_and_shown_boundary():
    row = {"name": "n", "kind": "skill", "tokens": 5, "idle_projects": 1, "idle_since": "2026-08-01", "why": "w"}
    assert pg.render({"candidates": [row], "tokens_saved": 5, "idle_days": 60}) == (
        "1 Item(s) only used by idle projects; removing all would save 5 tokens every session.\n\n"
        "  n (skill): 5 tokens, w\n\n"
        "Nothing was changed. Use `constellation remove-preview <name>` before removing anything."
    )
    assert "more" not in pg.render({"candidates": [row] * pg.SHOWN, "tokens_saved": 0, "idle_days": 60})


def test_cli_exact_output_and_messages(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(history, "_today", lambda: TODAY)
    monkeypatch.setattr(pg.pins, "DEFAULT_CACHE", tmp_path / "pins.json")
    path = tmp_path / "h.json"
    habits.save(path, {"XXXX": ledger({"old": (OLD, dead_use())}), "s": ledger({})})
    scan = tmp_path / "c.json"
    scan.write_text(json.dumps({"items": rows("old")}))  # no "setup": must not fall back to any ledger
    assert cli.main(["purge", str(scan), "--habits", str(path)]) == 2
    assert capsys.readouterr().err == "No habit ledger for this scan yet. Run `constellation scan` first.\n"
    scan.write_text(json.dumps({"setup": "s", "items": []}))
    assert cli.main(["purge", str(scan), "--habits", str(path), "--json"]) == 0
    assert capsys.readouterr().out == json.dumps({"candidates": [], "tokens_saved": 0, "idle_days": 60}, indent=2) + "\n"
