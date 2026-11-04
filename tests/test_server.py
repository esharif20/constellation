import json

import pytest
from fastapi.testclient import TestClient

from constellation import server
from constellation.cli import main
from constellation.server import create_app

DATA = {
    "items": [{"id": "a", "kind": "skill", "name": "a", "description": "d", "source": "s"}],
    "relations": [],
    "labels": {},
    "clusters": [],
    "warnings": [],
}


@pytest.fixture(autouse=True)
def built_app(tmp_path, monkeypatch):
    """A stand-in frontend build, so these tests never depend on `npm run build`."""
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><html><div id=root></div></html>")
    monkeypatch.setattr(server, "STATIC", static)
    return static


@pytest.fixture
def scan_file(tmp_path):
    path = tmp_path / "constellation.json"
    path.write_text(json.dumps(DATA))
    return path


def test_api_returns_scan_file_and_root_serves_app(scan_file):
    client = TestClient(create_app(scan_file))

    assert client.get("/api/constellation").json() == DATA
    root = client.get("/")
    assert root.status_code == 200
    assert "<html" in root.text


def test_api_reads_file_at_request_time(scan_file):
    client = TestClient(create_app(scan_file))
    scan_file.write_text(json.dumps({**DATA, "warnings": ["new"]}))

    assert client.get("/api/constellation").json()["warnings"] == ["new"]
    scan_file.unlink()
    assert client.get("/api/constellation").status_code == 404


def test_open_builds_app_and_passes_port_and_browser_flag(scan_file):
    calls = []

    code = main(
        ["open", str(scan_file), "--port", "9000", "--no-browser"], serve=lambda app, port, browser: calls.append((app, port, browser))
    )

    assert code == 0
    ((app, port, browser),) = calls
    assert (port, browser) == (9000, False)
    assert TestClient(app).get("/api/constellation").json() == DATA


def test_open_opens_browser_by_default(scan_file):
    calls = []
    main(["open", str(scan_file)], serve=lambda app, port, browser: calls.append((port, browser)))
    assert calls == [(8765, True)]


def test_open_missing_file_exits_2(tmp_path, capsys):
    code = main(["open", str(tmp_path / "nope.json")], serve=lambda *a: pytest.fail("must not serve"))

    assert code == 2
    assert "constellation scan" in capsys.readouterr().err


def test_open_without_frontend_build_exits_2_with_build_hint(scan_file, built_app, capsys):
    (built_app / "index.html").unlink()

    code = main(["open", str(scan_file)], serve=lambda *a: pytest.fail("must not serve"))

    assert code == 2
    assert "npm --prefix frontend install && npm --prefix frontend run build" in capsys.readouterr().err
