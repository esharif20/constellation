import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constellation import server
from constellation.server import create_app

BASE_URL = "http://127.0.0.1:8765"
DEMO = Path(__file__).parent.parent / "docs" / "design"


@pytest.fixture(autouse=True)
def built_app(tmp_path, monkeypatch):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><html><div id=root></div></html>")
    monkeypatch.setattr(server, "STATIC", static)


def lenses(path, tmp_path, base_url=BASE_URL):
    return TestClient(create_app(path, checklist=tmp_path / "c.md"), base_url=base_url).get("/api/lenses")


def test_demo_lenses_serves_every_lens(tmp_path):
    body = lenses(DEMO / "demo-lenses.json", tmp_path).json()
    assert set(body) == {"receipt", "hooks", "conflicts", "triggers"}
    assert [h["name"] for h in body["hooks"][:2]] == ["UserPromptSubmit", "UserPromptSubmit"]
    assert next(h for h in body["hooks"] if h["name"] == "PreToolUse:Edit")["runs"] == "mcp_tool"
    assert [c["kind"] for c in body["conflicts"]] == ["hook", "mcp_name", "trigger"]
    assert body["triggers"]["files"] == 40
    assert {r["name"]: r["flags"] for r in body["triggers"]["rows"]} == {"release-notes": ["greedy"], "repo-map": ["never"]}


def test_demo_250_has_no_conflicts(tmp_path):
    assert lenses(DEMO / "demo-250.json", tmp_path).json()["conflicts"] == []


def test_lenses_never_return_hook_commands_or_descriptions(tmp_path):
    secret = "sk-ant-api03-PLANTED"
    items = [
        {"id": "h1", "kind": "hook", "name": "PreToolUse:Bash", "description": f'curl -H "Authorization: {secret}"', "source": "s"},
        {"id": "h2", "kind": "hook", "name": "PreToolUse:Bash", "description": secret, "source": "s"},
        {"id": "s1", "kind": "skill", "name": "a", "description": f'{secret} "draft the notes"', "source": "s"},
        {"id": "s2", "kind": "skill", "name": "b", "description": f'"draft the notes" {secret}', "source": "s"},
    ]
    path = tmp_path / "scan.json"
    path.write_text(
        json.dumps(
            {
                "items": items,
                "relations": [],
                "usage": {"s1": {"count": 0, "last_used": None}, "s2": {"count": 3, "last_used": "2026-11-01"}},
                "usage_window": {"files": 5, "first": "2026-10-01", "last": "2026-11-01", "skipped": 0},
            }
        )
    )
    response = lenses(path, tmp_path)
    body = response.json()
    assert len(body["hooks"]) == 2 and [r["id"] for r in body["triggers"]["rows"]] == ["s1"]
    assert {c["key"] for c in body["conflicts"]} == {"PreToolUse:Bash", "draft the notes"}
    assert secret not in response.text and "curl" not in response.text


def test_lenses_route_bad_scan_and_foreign_host(tmp_path):
    path = tmp_path / "scan.json"
    path.write_text("not json")
    assert lenses(path, tmp_path).status_code == 404
    path.write_text(json.dumps({"items": []}))
    assert lenses(path, tmp_path, "http://evil.com").status_code == 403
