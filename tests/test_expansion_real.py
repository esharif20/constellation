"""Expansion against real stdio MCP servers (tests/fixtures/mcp_servers); invented data only."""

import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constellation import expansion, scan, server
from constellation.cli import main

FIXTURES = Path(__file__).parent / "fixtures" / "mcp_servers"
BASE_URL = "http://127.0.0.1:8765"
CANARY = "canary-secret-7f3a9c1e5b"
UNREACHABLE = "The configured MCP server is unreachable."


def setup(tmp_path, monkeypatch, script, env=None):
    config = tmp_path / "config"
    config.mkdir()
    pidfile = tmp_path / "pid"
    entry = {"command": sys.executable, "args": [str(FIXTURES / script)], "env": {"FIXTURE_PIDFILE": str(pidfile), **(env or {})}}
    (config / ".mcp.json").write_text(json.dumps({"mcpServers": {"fixture": entry}}))
    data = asdict(scan(config, offline=True, usage=False))
    saved = tmp_path / "scan.json"
    saved.write_text(json.dumps(data))
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("fixture")
    monkeypatch.setattr(server, "STATIC", static)
    return config, saved, data["items"][0]["id"], pidfile


def run_both(config, saved, id_, capsys):
    """Run the CLI and the HTTP endpoint; return (cli_text, cli_json, http_text, http_json, seconds)."""
    start = time.monotonic()
    assert main(["expand", id_, "--config-dir", str(config), "--file", str(saved)]) == 0
    cli_text = capsys.readouterr().out
    client = TestClient(server.create_app(saved, config_dir=config), base_url=BASE_URL)
    response = client.post("/api/expand", json={"id": id_})
    assert response.status_code == 200
    return cli_text, json.loads(cli_text), response.text, response.json(), time.monotonic() - start


def assert_dead(pidfile):
    pid = int(pidfile.read_text())
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    os.kill(pid, 9)
    pytest.fail("server process left running")


def test_good_server_lists_tools_despite_stdout_and_stderr_junk(tmp_path, monkeypatch, capsys):
    config, saved, id_, pidfile = setup(tmp_path, monkeypatch, "good.py")
    cli_text, cli, http_text, http, _ = run_both(config, saved, id_, capsys)
    for result in (cli, http):
        assert result["status"] == "expanded"
        assert [(i["name"], i["description"]) for i in result["items"]] == [
            ("add", "Add two numbers."),
            ("noisy", "Write junk to stderr, then echo."),
            ("slow_echo", "Echo text after a pause."),
        ]
    both = cli_text + http_text
    assert "not JSON-RPC" not in both and "stderr junk" not in both and "/private/raw/path" not in both
    assert_dead(pidfile)


@pytest.mark.parametrize("script", ["crash.py", "oversize.py", "flood.py", "hang.py"])
def test_bad_servers_are_plainly_unreachable_and_reaped(tmp_path, monkeypatch, capsys, script):
    monkeypatch.setattr(expansion, "QUERY_TIMEOUT", 2.0)
    config, saved, id_, pidfile = setup(tmp_path, monkeypatch, script)
    cli_text, cli, http_text, http, seconds = run_both(config, saved, id_, capsys)
    for result in (cli, http):
        assert (result["status"], result["message"], result["items"]) == ("unreachable", UNREACHABLE, [])
    for leaked in ("hunter2", "/Users/someone", "Traceback", str(FIXTURES), "junk\n", "zzzz"):
        assert leaked not in cli_text + http_text
    assert seconds < 10  # two runs, each bounded by the 2 s timeout plus teardown
    if pidfile.exists():
        assert_dead(pidfile)


def test_canary_env_and_paths_never_reach_output(tmp_path, monkeypatch, capsys):
    config, saved, id_, pidfile = setup(tmp_path, monkeypatch, "canary.py", {"CANARY_SECRET": CANARY})
    cli_text, cli, http_text, http, _ = run_both(config, saved, id_, capsys)
    assert cli["status"] == http["status"] == "expanded"
    for text in (cli_text, http_text):
        assert CANARY not in text and str(FIXTURES) not in text and str(tmp_path) not in text
    assert_dead(pidfile)
