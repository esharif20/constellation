import json
import os
import stat

import pytest
from fakes import FakeEmbedder
from fastapi.testclient import TestClient

from constellation import history, server
from constellation.cli import main
from constellation.server import create_app

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
    monkeypatch.setattr(history, "_today", lambda: "2026-11-04")
    root = tmp_path / "setup-dir"
    (root / "skills" / "NAME-MARKER").mkdir(parents=True)
    (root / "skills" / "NAME-MARKER" / "SKILL.md").write_text("---\nname: NAME-MARKER\ndescription: DESC-MARKER\n---\n")
    return root


def scan(config, tmp_path, *extra, name="scan.json"):
    out = tmp_path / name
    code = main(["scan", str(config), "--out", str(out), "--offline", *extra], embedder=FakeEmbedder({}))
    return code, out


def e(setup="s", day="2026-11-04", ids=("a",), items=None, always_on=0, unknown=0):
    return {
        "setup": setup,
        "date": day,
        "items": len(ids) if items is None else items,
        "always_on": always_on,
        "unknown": unknown,
        "ids": list(ids),
    }


def test_scan_records_counts_only(config, tmp_path):
    code, out = scan(config, tmp_path)

    path = history.DEFAULT_CACHE
    raw = path.read_text()
    (only,) = json.loads(raw)["entries"]
    assert code == 0
    assert set(only) == {"setup", "date", "items", "always_on", "unknown", "ids"}
    assert only["date"] == "2026-11-04" and only["items"] == 1 and only["unknown"] == 1 and only["always_on"] == 0
    assert only["ids"] == [history.key(json.loads(out.read_text())["items"][0]["id"])]
    assert only["setup"] == history.key(str(config.resolve()))
    for marker in ("NAME-MARKER", "DESC-MARKER", str(tmp_path)):
        assert marker not in raw
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(path.parent).st_mode) == 0o700
    saved = json.loads(out.read_text())
    assert saved["scanned_at"] == "2026-11-04" and saved["setup"] == only["setup"]


def test_entry_sums_known_costs_and_counts_unknown():
    data = {"items": [{"id": "a"}, {"id": "b"}, {"id": "c"}], "costs": {"a": {"always_on": 100}, "b": {"always_on": 0}, "c": None}}
    assert history.entry(data, "s", "2026-01-01") == {
        "setup": "s",
        "date": "2026-01-01",
        "items": 3,
        "always_on": 100,
        "unknown": 1,
        "ids": sorted(history.key(i) for i in "abc"),
    }


def test_key_is_twelve_hex_of_sha256():
    assert history.key("abc") == "ba7816bf8f01"


def test_same_day_rescan_replaces_and_other_day_adds(config, tmp_path, monkeypatch):
    scan(config, tmp_path)
    scan(config, tmp_path)
    assert [x["date"] for x in history.load(history.DEFAULT_CACHE)] == ["2026-11-04"]
    monkeypatch.setattr(history, "_today", lambda: "2026-11-05")
    scan(config, tmp_path)
    assert [x["date"] for x in history.load(history.DEFAULT_CACHE)] == ["2026-11-04", "2026-11-05"]


def test_two_setups_kept_apart(tmp_path):
    path = tmp_path / "h.json"
    history.record(path, e("one"))
    history.record(path, e("two"))
    history.record(path, e("one", ids=("a", "b")))
    assert [(x["setup"], x["ids"]) for x in history.load(path)] == [("one", ["a", "b"]), ("two", ["a"])]


def test_entries_older_than_400_days_dropped(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "_today", lambda: "2026-11-05")
    path = tmp_path / "h.json"
    for day in ("2025-09-30", "2025-10-01", "2025-10-02", "2026-11-05"):  # 401, 400 and 399 days before the newest
        history.record(path, e(day=day))
    assert [x["date"] for x in history.load(path)] == ["2025-10-01", "2025-10-02", "2026-11-05"]


def test_dry_run_and_no_history_record_nothing(config, tmp_path):
    main(["scan", str(config), "--out", str(tmp_path / "x.json"), "--dry-run"], embedder=FakeEmbedder({}))
    code, out = scan(config, tmp_path, "--no-history")
    assert code == 0 and out.is_file()
    assert not history.DEFAULT_CACHE.exists()
    assert json.loads(out.read_text())["scanned_at"] == "2026-11-04"


def test_unwritable_history_warns_and_scan_still_written(config, tmp_path, monkeypatch, capsys):
    blocker = tmp_path / "blocker"
    blocker.write_text("")
    monkeypatch.setattr(history, "DEFAULT_CACHE", blocker / "history.json")
    code, out = scan(config, tmp_path)
    assert code == 0 and out.is_file()
    assert "could not save scan history:" in capsys.readouterr().err


@pytest.mark.parametrize("text", ["not json", "[]", '{"v": 2, "entries": []}', '{"v": 1, "entries": 3}', ""])
def test_corrupt_history_reads_empty(tmp_path, text):
    path = tmp_path / "h.json"
    path.write_text(text)
    assert history.load(path) == []
    history.record(path, e())
    assert len(history.load(path)) == 1


def test_load_skips_malformed_entries(tmp_path):
    path = tmp_path / "h.json"
    bad = [None, {**e(), "extra": 1}, {**e(), "items": "3"}, {**e(), "items": True}, e(day="nope"), {**e(), "ids": [1]}]
    path.write_text(json.dumps({"v": 1, "entries": [*bad, e()]}))
    assert history.load(path) == [e()]


def test_failed_write_leaves_old_file_and_no_temp(tmp_path, monkeypatch):
    path = tmp_path / "sub" / "h.json"
    history.record(path, e())
    before = path.read_text()
    moved = []

    def broken(src, dst):
        moved.append(src)
        raise OSError("boom")

    monkeypatch.setattr(os, "replace", broken)
    with pytest.raises(OSError):
        history.record(path, e(day="2026-11-05"))
    assert os.path.dirname(moved[0]) == str(path.parent) and os.path.basename(moved[0]).startswith(".history-")
    assert path.read_text() == before and [p.name for p in path.parent.iterdir()] == ["h.json"]


def test_timeline_added_removed_gone_first_seen(tmp_path):
    path = tmp_path / "h.json"
    k = history.key
    for x in (
        e(day="2026-10-01", ids=[k("a"), k("b")], always_on=10),
        e(day="2026-10-08", ids=[k("a"), k("b"), k("c")], always_on=20, unknown=1),
        e(day="2026-10-15", ids=[k("a"), k("c")]),
        e(day="2026-10-22", ids=[k("a"), k("b"), k("c"), k("d")]),
        e(setup="other", day="2026-10-22", ids=[k("z")]),
        e(day="2026-11-30", ids=[k("a")]),
    ):
        history.record(path, x)
    data = {"setup": "s", "scanned_at": "2026-10-22", "items": [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "e"}]}
    out = history.timeline(path, data)
    assert [(r["date"], r["added"], r["removed"], r["gone"]) for r in out["entries"]] == [
        ("2026-10-01", 0, 0, 0),
        ("2026-10-08", 1, 0, 0),
        ("2026-10-15", 0, 1, 0),
        ("2026-10-22", 2, 0, 1),
    ]
    assert out["entries"][1] == {"date": "2026-10-08", "items": 3, "always_on": 20, "unknown": 1, "added": 1, "removed": 0, "gone": 0}
    assert out["first_seen"] == {"a": "2026-10-01", "b": "2026-10-22", "c": "2026-10-08", "e": "2026-10-22"}


def test_timeline_without_setup_or_entries_is_empty(tmp_path):
    path = tmp_path / "h.json"
    history.record(path, e())
    assert history.timeline(path, {"items": []}) == {"entries": [], "first_seen": {}}
    assert history.timeline(path, {"items": [], "setup": "s"}) == {"entries": [], "first_seen": {}}
    assert history.timeline(path, {"items": [{"id": "a"}], "setup": "x", "scanned_at": "2026-11-04"}) == {"entries": [], "first_seen": {}}


@pytest.fixture
def served(config, tmp_path):
    code, out = scan(config, tmp_path)
    assert code == 0
    return TestClient(create_app(out, checklist=tmp_path / "c.md", history=history.DEFAULT_CACHE), base_url=BASE_URL), out


def test_api_history_localhost_only(served):
    client, _ = served
    assert client.get("/api/history").status_code == 200
    assert client.get("/api/history", headers={"host": "evil.example"}).status_code == 403


def test_api_history_has_no_hashes_or_paths(served, tmp_path):
    client, out = served
    body = client.get("/api/history").content.decode()
    raw = history.DEFAULT_CACHE.read_text()
    for h in json.loads(raw)["entries"][0]["ids"] + [json.loads(raw)["entries"][0]["setup"], str(tmp_path)]:
        assert h not in body
    assert json.loads(body)["entries"][0]["date"] == "2026-11-04"


def test_api_history_empty_for_old_scan(tmp_path):
    scan_file = tmp_path / "old.json"
    scan_file.write_text(json.dumps({"items": []}))
    client = TestClient(create_app(scan_file, checklist=tmp_path / "c.md", history=tmp_path / "h.json"), base_url=BASE_URL)
    assert client.get("/api/history").json() == {"entries": [], "first_seen": {}}


def test_api_history_404_for_unreadable_scan(tmp_path):
    client = TestClient(create_app(tmp_path / "missing.json", checklist=tmp_path / "c.md", history=tmp_path / "h.json"), base_url=BASE_URL)
    assert client.get("/api/history").status_code == 404


def test_open_passes_history_flag_and_default_read_at_call_time(config, tmp_path, monkeypatch):
    code, out = scan(config, tmp_path)
    seen = []
    assert (
        main(["open", str(out), "--history", str(tmp_path / "h.json"), "--no-browser"], serve=lambda app, port, browser: seen.append(app))
        == 0
    )
    assert TestClient(seen[0], base_url=BASE_URL).get("/api/history").json() == {"entries": [], "first_seen": {}}
    assert main(["open", str(out), "--no-browser"], serve=lambda app, port, browser: seen.append(app)) == 0
    assert len(TestClient(seen[1], base_url=BASE_URL).get("/api/history").json()["entries"]) == 1


def test_new_directories_are_private(tmp_path):
    path = tmp_path / "a" / "b" / "h.json"
    history.record(path, e())
    assert stat.S_IMODE(os.stat(path.parent).st_mode) == 0o700 and stat.S_IMODE(os.stat(path).st_mode) == 0o600


@pytest.mark.parametrize("zone", ["Pacific/Kiritimati", "Etc/GMT+12"])  # UTC+14 and UTC-12: one of them is always on another calendar day
def test_today_is_the_utc_date(monkeypatch, zone):
    import time
    from datetime import UTC, datetime

    monkeypatch.setenv("TZ", zone)
    time.tzset()
    try:
        before = datetime.now(UTC).date().isoformat()
        assert history._today() in (before, datetime.now(UTC).date().isoformat())
    finally:
        monkeypatch.undo()
        time.tzset()


def test_future_dated_entry_does_not_delete_real_history(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "_today", lambda: "2026-11-05")
    path = tmp_path / "h.json"
    history.record(path, e(day="2026-01-01"))
    history.record(path, e(day="9999-01-01"))
    assert [x["date"] for x in history.load(path)] == ["2026-01-01", "9999-01-01"]


@pytest.mark.parametrize("day", ["20261105", "2026-W45-3"])
def test_non_canonical_dates_are_skipped(tmp_path, day):
    path = tmp_path / "h.json"
    path.write_text(json.dumps({"v": 1, "entries": [e(day=day), e()]}))
    assert history.load(path) == [e()]


def test_existing_directory_is_made_private(tmp_path):
    (tmp_path / "d").mkdir(mode=0o755)
    os.chmod(tmp_path / "d", 0o755)
    history.record(tmp_path / "d" / "h.json", e())
    assert stat.S_IMODE(os.stat(tmp_path / "d").st_mode) == 0o700


def test_corrupt_existing_file_warns_on_record_only(tmp_path, capsys):
    path = tmp_path / "h.json"
    path.write_text("not json")
    history.load(path)
    assert capsys.readouterr().err == ""
    history.record(path, e())
    assert "could not be read" in capsys.readouterr().err
    history.record(tmp_path / "new.json", e())
    assert capsys.readouterr().err == ""


def test_write_is_fsynced_before_replace(tmp_path, monkeypatch):
    order = []
    real = os.fsync
    monkeypatch.setattr(os, "fsync", lambda fd: (order.append("fsync"), real(fd))[1])
    real_replace = os.replace
    monkeypatch.setattr(os, "replace", lambda a, b: (order.append("replace"), real_replace(a, b))[1])
    history.record(tmp_path / "h.json", e())
    assert order == ["fsync", "replace"]
