import json
from datetime import date, timedelta

from fakes import write_skill

from constellation import cli, habits, history, scanfile
from constellation import profile as pf
from constellation.usage import mac

SALT = "a" * 64
TODAY = "2026-11-06"
FOLDER = "-tmp-app"
OTHER = "-tmp-other"
OLD = "2026-01-01"


def pk(folder):
    return mac(SALT, folder, 6)


def iid(name):
    return f"x:skill:global:{name}"


def ledger(sessions=6, items=None, days=None):
    if days is None:
        days = {"2026-11-01": {"sessions": sessions, "projects": {pk(FOLDER): sessions}}}
    recs = {mac(SALT, iid(n), 12): {"first_seen": fs, "days": d} for n, (fs, d) in (items or {}).items()}
    return {"salt": SALT, "days": days, "items": recs, "co": {}}


def used(here=0, elsewhere=0, day="2026-11-01"):
    p = {}
    if here:
        p[pk(FOLDER)] = here
    if elsewhere:
        p[pk(OTHER)] = elsewhere
    return {day: {"n": here + elsewhere, "s": 1, "p": p}}


def tracked(*names, kind="skill"):
    return {iid(n): (kind, n) for n in names}


def build(led, *names, today=TODAY):
    return pf.build(led, today, tracked(*names), FOLDER, "my-app")


def test_used_noise_and_new_items_are_split_and_sorted():
    led = ledger(
        items={
            "b": (OLD, used(here=2, elsewhere=9)),
            "a": (OLD, used(here=7, elsewhere=1)),
            "n": (OLD, used(elsewhere=3)),
            "z": (OLD, {}),
            "fresh": ((date.fromisoformat(TODAY) - timedelta(days=30)).isoformat(), {}),
        }
    )
    out = build(led, "a", "b", "n", "z", "fresh", "unknown")
    assert [r["name"] for r in out["used"]] == ["a", "b"]
    assert out["used"][0] == {"name": "a", "kind": "skill", "uses": 7, "elsewhere": 1, "last_used": "2026-11-01"}
    assert out["noise"] == [
        {"name": "n", "kind": "skill", "uses": 0, "elsewhere": 3, "why": "used only in other projects"},
        {"name": "z", "kind": "skill", "uses": 0, "elsewhere": 0, "why": "not seen in any transcript"},
    ]
    assert out["too_new"] == 2  # exactly 30 days old, and no ledger record
    assert out["state"] == "ok" and out["sessions"] == 6 and out["active_days"] == 1


def test_an_item_31_days_old_is_judged():
    first = (date.fromisoformat(TODAY) - timedelta(days=31)).isoformat()
    out = build(ledger(items={"a": (first, {})}), "a")
    assert out["too_new"] == 0 and len(out["noise"]) == 1


def test_five_sessions_are_enough_four_are_not_and_the_note_says_so():
    assert build(ledger(sessions=5), "a")["state"] == "ok"
    out = build(ledger(sessions=4, items={"a": (OLD, {})}), "a")
    assert out["state"] == "not_enough_history" and out["noise"] == [] and out["used"] == []
    assert out["note"] == "Not enough history yet: 4 session(s) seen here, 5 needed."


def test_an_unknown_project_and_future_days_have_no_history():
    assert build(ledger(days={}), "a")["sessions"] == 0
    future = {"2026-11-07": {"sessions": 9, "projects": {pk(FOLDER): 9}}}
    assert build(ledger(days=future), "a")["state"] == "not_enough_history"
    led = ledger(items={"a": (OLD, {**used(here=1), **used(here=50, day="2026-11-07")})})
    assert build(led, "a")["used"][0]["uses"] == 1


def test_local_candidates_need_five_uses_and_four_fifths_here():
    led = ledger(
        items={
            "edge": (OLD, used(here=8, elsewhere=2)),
            "share": (OLD, used(here=7, elsewhere=2)),
            "few": (OLD, used(here=4)),
            "five": (OLD, used(here=5)),
        }
    )
    out = build(led, "edge", "share", "few", "five")
    assert [r["name"] for r in out["local_candidates"]] == ["edge", "five"]


def test_a_candidate_with_more_uses_sorts_first_and_mcp_kinds_are_kept():
    led = ledger(items={"a": (OLD, used(here=5)), "b": (OLD, used(here=9))})
    assert [r["name"] for r in build(led, "a", "b")["local_candidates"]] == ["b", "a"]
    assert pf.build(led, TODAY, tracked("a", kind="agent"), FOLDER, "x")["used"][0]["kind"] == "agent"


def test_encode_and_resolve_match_folders_by_path_or_unambiguous_name():
    assert pf.encode("/tmp/my app.x") == "-tmp-my-app-x"
    folders = ["-home-me-app", "-home-me-other-app", "-home-me-lib"]
    assert pf.resolve("lib", None, folders) == ("-home-me-lib", None)
    assert "matches 2 projects" in pf.resolve("app", None, folders)[1]
    assert pf.resolve("ap", None, folders)[0] is None  # a name ends a folder at a dash, not mid-word
    assert pf.resolve("nope", None, folders) == (None, "No history for 'nope'. Pass the project folder you open Claude Code in.")
    assert pf.resolve("/home/me/lib", "/home/me/lib", folders) == ("-home-me-lib", None)
    assert pf.resolve("/home/me/x", "/home/me/x", folders)[0] is None


def test_render_lists_sections_caps_long_ones_and_never_prints_hashes():
    led = ledger(
        items={f"s{i:02}": (OLD, used(here=1, elsewhere=1)) for i in range(16)} | {"n": (OLD, used(elsewhere=1)), "fresh": (TODAY, {})}
    )
    text = pf.render(build(led, *[f"s{i:02}" for i in range(16)], "n", "fresh"))
    assert text.startswith("Profile of my-app: 6 session(s) over 1 active day(s).")
    assert "Used here:\n  s00 (skill): 1 here, 1 elsewhere, last 2026-11-01" in text
    assert "s14" in text and "s15" not in text and "...and 1 more (see --json)" in text
    assert "Noise here (global, never used in this project):\n  n (skill): used only in other projects" in text
    assert "1 Item(s) too new to judge" in text and "Could be local" not in text
    assert SALT not in text and pk(FOLDER) not in text
    short = pf.render(build(ledger(sessions=1), "a"))
    assert short.endswith("Not enough history yet: 1 session(s) seen here, 5 needed.") and "Used here" not in short
    assert "more (see --json)" not in pf.render(build(ledger(items={"a": (OLD, used(here=1))}), "a"))


def test_the_cli_profiles_a_project_read_only_and_keeps_hashes_out(tmp_path, monkeypatch, capsys):
    config = tmp_path / "cfg"
    write_skill(config, "alpha", "x")
    write_skill(config, "beta", "x")
    project = tmp_path / "work" / "app"
    folder = pf.encode(str(project.resolve()))
    (config / "projects" / folder).mkdir(parents=True)
    salt = "b" * 64
    day = {"sessions": 6, "projects": {mac(salt, folder, 6): 6}}
    cell = {"first_seen": OLD, "days": {"2026-11-01": {"n": 3, "s": 1, "p": {mac(salt, folder, 6): 3}}}}
    ids = {i.name: i.id for i in __import__("constellation.claude_code", fromlist=["x"]).read_items(config)[0] if i.kind == "skill"}
    led = {
        "salt": salt,
        "days": {"2026-11-01": day},
        "co": {},
        "items": {mac(salt, ids["alpha"], 12): cell, mac(salt, ids["beta"], 12): {"first_seen": OLD, "days": {}}},
    }
    path = tmp_path / "habits.json"
    habits.save(path, {history.key(str(config.resolve())): led})
    before = path.read_bytes()
    monkeypatch.setattr(history, "_today", lambda: TODAY)
    # profile names Items from the saved (already redacted) scan, never from a fresh raw read of the config
    saved = tmp_path / "scan.json"
    rows = [{"id": ids[n], "kind": "skill", "name": n.replace("alpha", "[REDACTED]"), "scope": "global", "disabled": False} for n in ids]
    saved.write_text(json.dumps({"items": rows}))
    scanfile.remember(saved)
    assert cli.main(["profile", str(project), "--config-dir", str(config), "--habits", str(path)]) == 0
    text = capsys.readouterr().out
    assert "[REDACTED] (skill): 3 here, 0 elsewhere" in text and "alpha" not in text and "beta (skill): not seen in any transcript" in text
    assert cli.main(["profile", "app", "--config-dir", str(config), "--habits", str(path), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["project"] == "app" and data["used"][0]["name"] == "[REDACTED]"
    assert mac(salt, folder, 6) not in json.dumps(data) and folder not in json.dumps(data)
    assert path.read_bytes() == before


def test_the_cli_reports_an_unknown_project_or_missing_ledger_on_stderr(tmp_path, capsys):
    config = tmp_path / "cfg"
    config.mkdir()
    assert cli.main(["profile", "ghost", "--config-dir", str(config), "--habits", str(tmp_path / "none.json")]) == 2
    assert "No history for 'ghost'" in capsys.readouterr().err
    (config / "projects" / "-x-ghost").mkdir(parents=True)
    assert cli.main(["profile", "ghost", "--config-dir", str(config), "--habits", str(tmp_path / "none.json")]) == 2
    assert "No habit ledger yet" in capsys.readouterr().err


def test_encode_keeps_case_and_a_trailing_letter_of_the_name_is_not_stripped():
    assert pf.encode("My-App/x") == "My-App-x"
    assert pf.resolve("appX", None, ["-me-app", "-me-appX"]) == ("-me-appX", None)
    assert pf.resolve("app-", None, ["-me-app"]) == ("-me-app", None)


def test_today_counts_for_sessions_and_for_uses():
    led = ledger(days={TODAY: {"sessions": 5, "projects": {pk(FOLDER): 5}}}, items={"a": (OLD, used(here=2, day=TODAY))})
    out = build(led, "a")
    assert out["state"] == "ok" and out["note"] == "" and out["used"][0]["uses"] == 2


def test_render_is_exact_for_all_three_sections_and_a_full_page_has_no_more_line():
    led = ledger(items={"a": (OLD, used(here=9, elsewhere=1)), "n": (OLD, used(elsewhere=2)), "f": (TODAY, {})})
    assert pf.render(build(led, "a", "n", "f")) == (
        "Profile of my-app: 6 session(s) over 1 active day(s).\n"
        "\nUsed here:\n  a (skill): 9 here, 1 elsewhere, last 2026-11-01\n"
        "\nNoise here (global, never used in this project):\n  n (skill): used only in other projects\n"
        "\nCould be local to this project:\n  a (skill): 9 uses here, 1 elsewhere\n"
        "\n1 Item(s) too new to judge for this project."
    )
    assert pf.render(build(ledger(sessions=2), "a")) == (
        "Profile of my-app: 2 session(s) over 1 active day(s).\nNot enough history yet: 2 session(s) seen here, 5 needed."
    )
    names = [f"s{i:02}" for i in range(15)]
    text = pf.render(build(ledger(items={n: (OLD, used(here=1, elsewhere=1)) for n in names}), *names))
    assert "more" not in text and text.endswith("s14 (skill): 1 here, 1 elsewhere, last 2026-11-01")
    names.append("s15")
    text = pf.render(build(ledger(items={n: (OLD, used(here=1, elsewhere=1)) for n in names}), *names))
    assert text.endswith("s14 (skill): 1 here, 1 elsewhere, last 2026-11-01\n  ...and 1 more (see --json)")
