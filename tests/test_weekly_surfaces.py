import json
import re

import pytest
from fakes import FakeEmbedder
from fastapi.testclient import TestClient

from constellation import history, server, weekly
from constellation.cli import main
from constellation.server import create_app
from constellation.snapshot import snapshot

BASE_URL = "http://127.0.0.1:8765"


@pytest.fixture(autouse=True)
def no_local_embedder(monkeypatch):
    monkeypatch.setattr("constellation.cli._local_embedder", lambda: None)


@pytest.fixture(autouse=True)
def built_app(tmp_path, monkeypatch):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html>")
    monkeypatch.setattr(server, "STATIC", static)


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    root = tmp_path / "setup-dir"
    for name in ("alpha-skill", "beta-skill"):
        (root / "skills" / name).mkdir(parents=True)
        (root / "skills" / name / "SKILL.md").write_text(f"---\nname: {name}\ndescription: Does {name} work for you\n---\n")
    return root


def scan(config, tmp_path, day, monkeypatch, *extra):
    monkeypatch.setattr(history, "_today", lambda: day)
    out = tmp_path / "scan.json"
    return main(["scan", str(config), "--out", str(out), "--offline", *extra], embedder=FakeEmbedder({})), out


def two_scans(config, tmp_path, monkeypatch):
    scan(config, tmp_path, "2026-11-01", monkeypatch)
    (config / "skills" / "gamma-skill").mkdir()
    (config / "skills" / "gamma-skill" / "SKILL.md").write_text("---\nname: gamma-skill\ndescription: Does gamma work for you\n---\n")
    return scan(config, tmp_path, "2026-11-06", monkeypatch)


def test_weekly_on_a_first_scan_says_not_enough_history(config, tmp_path, monkeypatch, capsys):
    code, out = scan(config, tmp_path, "2026-11-01", monkeypatch)
    assert code == 0
    capsys.readouterr()
    assert main(["weekly", str(out)]) == 0
    assert capsys.readouterr().out == f"Weekly state of your setup\n{weekly.FIRST}\n"


def test_weekly_after_a_second_scan_names_what_was_added(config, tmp_path, monkeypatch, capsys):
    _, out = two_scans(config, tmp_path, monkeypatch)
    capsys.readouterr()
    assert main(["weekly", str(out)]) == 0
    text = capsys.readouterr().out
    assert text.startswith("Weekly state of your setup\nSince 2026-11-01: 1 added, 0 removed;")
    assert "Added (1)\n  skill  gamma-skill\n" in text
    assert "Removed" not in text
    assert not re.search(r"[0-9a-f]{12}", text) and str(tmp_path) not in text


def test_weekly_json_and_since(config, tmp_path, monkeypatch, capsys):
    _, out = two_scans(config, tmp_path, monkeypatch)
    capsys.readouterr()
    assert main(["weekly", str(out), "--json", "--since", "2026-11-01"]) == 0
    raw = capsys.readouterr().out
    assert raw.startswith('{\n  "state": "ready"')
    got = json.loads(raw)
    assert (got["state"], got["since"], got["days"], got["added"]) == ("ready", "2026-11-01", 5, [{"kind": "skill", "name": "gamma-skill"}])
    assert main(["weekly", str(out), "--json", "--since", "2026-10-31"]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "first"


@pytest.mark.parametrize("since", ["yesterday", "2026-13-01", "20261101", ""])
def test_weekly_rejects_a_bad_since_date(config, tmp_path, monkeypatch, capsys, since):
    _, out = two_scans(config, tmp_path, monkeypatch)
    capsys.readouterr()
    assert main(["weekly", str(out), "--since", since]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == "--since must be a date like 2026-11-01.\n"


def test_weekly_needs_a_scan_file(tmp_path, capsys):
    assert main(["weekly", str(tmp_path / "none.json")]) == 2
    assert re.fullmatch(
        r"^.*none\.json is missing or not a constellation scan; run `constellation scan` first\.\n$", capsys.readouterr().err
    )


def test_weekly_reports_a_scan_it_cannot_assess(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"items": [{"id": "x"}]}))
    assert main(["weekly", str(bad)]) == 2
    assert capsys.readouterr().err == "The saved scan could not be read; run `constellation scan` again.\n"


def test_no_history_scan_records_no_weekly_snapshot(config, tmp_path, monkeypatch):
    scan(config, tmp_path, "2026-11-01", monkeypatch, "--no-history")
    assert weekly.load(weekly.DEFAULT_CACHE) == []
    scan(config, tmp_path, "2026-11-01", monkeypatch)
    assert len(weekly.load(weekly.DEFAULT_CACHE)) == 1


def test_scan_warns_but_succeeds_when_the_weekly_snapshot_cannot_be_saved(config, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(weekly, "DEFAULT_CACHE", tmp_path / "setup-dir" / "skills" / "alpha-skill" / "SKILL.md" / "w.json")
    code, _ = scan(config, tmp_path, "2026-11-01", monkeypatch)
    assert code == 0 and "could not save the weekly snapshot" in capsys.readouterr().err


# ---- the Brief ----


def client(out, tmp_path):
    return TestClient(create_app(out, tmp_path / "checklist.md"), base_url=BASE_URL)


def test_brief_has_no_weekly_section_on_a_first_scan(config, tmp_path, monkeypatch):
    _, out = scan(config, tmp_path, "2026-11-01", monkeypatch)
    assert client(out, tmp_path).get("/api/brief").json()["weekly"] is None


def test_brief_carries_the_weekly_summary_without_hashes_or_paths(config, tmp_path, monkeypatch):
    _, out = two_scans(config, tmp_path, monkeypatch)
    response = client(out, tmp_path).get("/api/brief")
    got = response.json()["weekly"]
    assert (got["state"], got["since"], got["added"]) == ("ready", "2026-11-01", [{"kind": "skill", "name": "gamma-skill"}])
    text = json.dumps(got)
    assert not re.search(r"[0-9a-f]{12}", text) and str(tmp_path) not in text and "setup" not in got


def test_brief_weekly_uses_the_given_file_and_follows_the_host_guard(config, tmp_path, monkeypatch):
    _, out = two_scans(config, tmp_path, monkeypatch)
    other = tmp_path / "other-weekly.json"
    app = create_app(out, tmp_path / "checklist.md", weekly=other)
    assert TestClient(app, base_url=BASE_URL).get("/api/brief").json()["weekly"] is None  # that file holds no history
    assert TestClient(app, base_url="http://evil.example").get("/api/brief").status_code == 403


def test_a_scan_with_nothing_to_compare_never_breaks_the_brief(config, tmp_path, monkeypatch):
    _, out = two_scans(config, tmp_path, monkeypatch)
    monkeypatch.setattr(weekly, "build", lambda *a, **k: (_ for _ in ()).throw(KeyError("x")))
    got = client(out, tmp_path).get("/api/brief")
    assert got.status_code == 200 and got.json()["weekly"] is None


def test_assess_does_not_return_the_weekly_section(config, tmp_path, monkeypatch):
    _, out = two_scans(config, tmp_path, monkeypatch)
    assert "weekly" not in client(out, tmp_path).get("/api/assess").json()


def test_the_public_export_never_carries_weekly_data(config, tmp_path, monkeypatch):
    _, out = two_scans(config, tmp_path, monkeypatch)
    data = json.loads(out.read_text())
    data["weekly"] = {"headline": "SECRET-WEEKLY"}
    assert "SECRET-WEEKLY" not in json.dumps(snapshot(data))
    assert "weekly" not in snapshot(data)
