"""Saved-scan ids stay unique and private when secrets are in skill names (invented data only)."""

import json

import pytest
from fakes import FakeEmbedder, write_skill
from fastapi.testclient import TestClient

from constellation import habits, history, public_export, server, skill_search, weekly
from constellation.cli import main
from constellation.idkey import id_key
from constellation.redact import redact_tree, unique_ids

ONE, TWO = "ZZQ-INVENTED-SECRET-ONE-81", "ZZQ-INVENTED-SECRET-TWO-81"
BASE_URL = "http://127.0.0.1:8765"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    config = tmp_path / "invented-config"
    config.mkdir()
    (config / "settings.json").write_text(json.dumps({"env": {"INVENTED_TOKEN": ONE, "INVENTED_KEY": TWO}}))
    write_skill(config, ONE, "First instructions about typography for websites.", description="Invented first")
    write_skill(config, TWO, "Second instructions", description="Invented second")
    write_skill(config, "plain", "Plain instructions")
    monkeypatch.setattr("constellation.cli.load_env", lambda: None)
    static = tmp_path / "invented-build"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html></html>")
    monkeypatch.setattr(public_export, "STATIC", static)
    monkeypatch.setattr(server, "STATIC", static)
    return config


def run_scan(config, tmp_path):
    out = tmp_path / "scan.json"
    assert main(["scan", str(config), "--offline", "--no-origins", "--out", str(out)], embedder=FakeEmbedder({})) == 0
    return out, json.loads(out.read_text())


def test_secret_named_skills_get_distinct_ids_and_the_api_loads(setup, tmp_path):
    out, data = run_scan(setup, tmp_path)
    ids = [i["id"] for i in data["items"] if i["kind"] == "skill"]
    assert len(ids) == len(set(ids)) == 3
    secret_ids = [i for i in ids if "[REDACTED]" in i]
    assert len(secret_ids) == 2 and all(i.startswith("claude-code:skill:[REDACTED]~") for i in secret_ids)
    assert "claude-code:skill:plain" in ids
    assert ONE not in out.read_text() and TWO not in out.read_text()
    with TestClient(server.create_app(out, embedder=FakeEmbedder({})), base_url=BASE_URL) as client:
        reply = client.get("/api/constellation")
        assert reply.status_code == 200
        assert client.get("/api/explain").status_code == 200


def test_relations_point_at_the_right_item(setup, tmp_path):
    plugin = setup / "plugins/cache/m/invented-plugin/1"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin/plugin.json").write_text(json.dumps({"name": "invented-plugin", "description": "Invented"}))
    write_skill(plugin, ONE, "Plugin copy", description="Invented plugin first")
    (setup / "plugins/installed_plugins.json").write_text(json.dumps({"plugins": {"invented-plugin@m": [{"installPath": str(plugin)}]}}))
    _, data = run_scan(setup, tmp_path)
    names = {i["id"]: i for i in data["items"]}
    assert len(names) == len(data["items"])
    contained = [r for r in data["relations"] if r["kind"] == "contains"]
    assert contained and all(r["source"] in names and r["target"] in names for r in data["relations"])
    assert names[contained[0]["target"]]["description"] == "Invented plugin first"


def test_saved_ids_are_stable_between_scans_and_keyed_per_install(setup, tmp_path):
    first = {i["id"] for i in run_scan(setup, tmp_path)[1]["items"]}
    assert first == {i["id"] for i in run_scan(setup, tmp_path)[1]["items"]}
    key = id_key(history.DEFAULT_CACHE.with_name("id-key"))
    assert len(key) == 32 and (history.DEFAULT_CACHE.with_name("id-key").stat().st_mode & 0o777) == 0o600
    assert unique_ids(["a:" + ONE], [ONE], key) != unique_ids(["a:" + ONE], [ONE], b"x" * 32)


def test_redact_tree_maps_exact_ids_and_keys_but_redacts_other_text():
    ids = {"id:SECRET99": "id:[REDACTED]~abc123"}
    tree = {"id:SECRET99": ["id:SECRET99", "mentions id:SECRET99 inside", {"k": "id:SECRET99"}]}
    assert redact_tree(tree, ["SECRET99"], ids) == {
        "id:[REDACTED]~abc123": ["id:[REDACTED]~abc123", "mentions id:[REDACTED] inside", {"k": "id:[REDACTED]~abc123"}]
    }


def test_unique_ids_only_maps_ids_that_redaction_changes():
    key = b"k" * 32
    mapped = unique_ids(["plain", "x:" + ONE, "y:" + ONE], [ONE], key)
    assert set(mapped) == {"x:" + ONE, "y:" + ONE}
    assert mapped["x:" + ONE] != mapped["y:" + ONE]
    assert all(v.startswith(("x:", "y:")) and len(v.split("~")[1]) == 6 for v in mapped.values())


def test_find_skills_resolves_secret_named_skills_to_their_saved_ids(setup, tmp_path):
    _, data = run_scan(setup, tmp_path)
    saved = {i["id"] for i in data["items"]}
    hits, _ = skill_search.find_skills("typography websites", setup, cache=tmp_path / "idx" / "c.json")
    assert hits and {h["id"] for h in hits} <= saved
    assert any(h["id"].startswith("claude-code:skill:[REDACTED]~") for h in hits)
    content = json.loads((tmp_path / "idx" / "c.json").read_text())
    assert set(content) <= saved and len(content) == 3
    assert ONE not in json.dumps(hits) and ONE not in json.dumps(content)


def test_habits_and_weekly_keys_match_the_saved_scan_ids(setup, tmp_path):
    _, data = run_scan(setup, tmp_path)
    assert habits.DEFAULT_CACHE.is_file() and weekly.DEFAULT_CACHE.is_file() and history.DEFAULT_CACHE.is_file()
    ledger = next(iter(json.loads(habits.DEFAULT_CACHE.read_text())["setups"].values()))
    hashed = {habits.mac(ledger["salt"], i["id"], 12) for i in data["items"] if i["kind"] in habits.TRACKED}
    assert hashed and set(ledger["items"]) <= hashed
    entry = json.loads(history.DEFAULT_CACHE.read_text())["entries"][0]
    assert set(entry["ids"]) == {history.key(i["id"]) for i in data["items"]}
    snap = json.loads(weekly.DEFAULT_CACHE.read_text())
    assert ONE not in json.dumps(snap) and TWO not in json.dumps(snap)


def test_no_planted_secret_appears_in_any_cache_file_after_a_scan(setup, tmp_path, monkeypatch, capsys):
    cache = history.DEFAULT_CACHE.parent
    # a transcript that uses the secret-named skill, so the ledger sees it
    transcripts = setup / "projects" / "p"
    transcripts.mkdir(parents=True)
    line = {
        "type": "assistant",
        "timestamp": "2026-11-05T12:00:00Z",
        "cwd": str(tmp_path),
        "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Skill", "input": {"skill": ONE}}]},
    }
    (transcripts / "s.jsonl").write_text(json.dumps(line) + "\n")
    run_scan(setup, tmp_path)
    capsys.readouterr()
    files = [p for p in cache.rglob("*") if p.is_file()]
    assert {p.name for p in files} >= {"habits.json", "weekly.json", "history.json", "id-key"}
    for path in files:
        raw = path.read_bytes()
        assert ONE.encode() not in raw and TWO.encode() not in raw, path.name
        assert history.key("claude-code:skill:" + ONE).encode() not in raw, path.name


def test_find_skills_redacts_warnings_with_a_known_secret(setup, tmp_path, monkeypatch):
    real = skill_search.read_items

    def with_warning(config_dir):
        items, warnings, relations, bodies = real(config_dir)
        return items, [*warnings, f"could not read {ONE}"], relations, bodies

    monkeypatch.setattr(skill_search, "read_items", with_warning)
    _, warnings = skill_search.find_skills("typography", setup, cache=tmp_path / "idx" / "c.json")
    assert warnings == ["could not read [REDACTED]"]
