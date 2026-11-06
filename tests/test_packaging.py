import importlib.metadata
import json
import tomllib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constellation import server
from constellation.cli import main

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "http://127.0.0.1:8765"


@pytest.fixture
def built_app(tmp_path, monkeypatch):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><html></html>")
    monkeypatch.setattr(server, "STATIC", static)


def test_version_prints_the_installed_distribution_version(capsys):
    with pytest.raises(SystemExit) as stop:
        main(["--version"])

    assert stop.value.code == 0
    assert capsys.readouterr().out == f"constellation {importlib.metadata.version('constellation-cli')}\n"


def test_distribution_is_constellation_cli_with_the_server_in_base_dependencies():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]

    assert project["name"] == "constellation-cli"
    assert project["scripts"] == {"constellation": "constellation.cli:main"}
    assert project["license"] == "MIT"
    base = {d.split(">")[0].split("=")[0] for d in project["dependencies"]}
    assert {"fastapi", "uvicorn", "mcp"} <= base


def test_packaged_demo_is_identical_to_the_design_demo():
    packaged = ROOT / "src" / "constellation" / "demo" / "demo.json"

    assert packaged.read_bytes() == (ROOT / "docs" / "design" / "demo.json").read_bytes()


def test_open_demo_serves_the_packaged_scan_with_isolated_caches(built_app, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)  # no constellation.json here, so only the packaged demo can answer
    seen = []

    def serve(app, port, browser):
        seen.append((port, browser))
        client = TestClient(app, base_url=BASE_URL)
        seen.append(client.get("/api/constellation").json())
        seen.append(client.get("/api/history").status_code)

    code = main(["open", "demo", "--no-browser"], serve=serve)

    assert code == 0
    assert seen[0] == (8765, False)
    assert seen[1] == json.loads((ROOT / "docs" / "design" / "demo.json").read_text())
    assert seen[2] == 200


def test_open_demo_uses_a_throwaway_directory_for_every_cache(built_app, monkeypatch):
    captured = {}
    real = server.create_app

    def spy(scan_file, **kwargs):
        captured["scan"] = scan_file
        captured.update(kwargs)
        return real(scan_file, **kwargs)

    monkeypatch.setattr(server, "create_app", spy)
    main(["open", "demo", "--no-browser"], serve=lambda *a: None)

    sandbox = captured["checklist"].parent
    assert sandbox.name.startswith("constellation-demo-") and not sandbox.exists()  # removed on exit
    assert captured["scan"].name == "demo.json"
    for key in ("history", "pins", "habits", "weekly"):
        assert captured[key].parent == sandbox
