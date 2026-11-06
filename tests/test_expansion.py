"""Expansion tests use the CLI/HTTP boundaries; all registrations are synthetic."""

import json
from dataclasses import asdict
from hashlib import sha256

from fastapi.testclient import TestClient

from constellation import scan, server
from constellation.cli import main

BASE_URL = "http://127.0.0.1:8765"


def setup_scan(tmp_path, monkeypatch, servers=None):
    config = tmp_path / "config"
    config.mkdir()
    (config / ".mcp.json").write_text(json.dumps({"mcpServers": servers or {"fixture": {"command": "synthetic"}}}))
    data = asdict(scan(config, offline=True, usage=False))
    saved = tmp_path / "scan.json"
    saved.write_text(json.dumps(data))
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("fixture")
    monkeypatch.setattr(server, "STATIC", static)
    return config, saved, data["items"][0]["id"]


def test_expansion_lists_sorted_tools_through_cli_and_http(tmp_path, monkeypatch, capsys):
    config, saved, id_ = setup_scan(tmp_path, monkeypatch)
    calls = []

    async def query(registration):
        calls.append(registration)
        return [("zeta", None), ("alpha", "First tool")]

    assert main(["expand", id_, "--config-dir", str(config), "--file", str(saved)], expansion_query=query) == 0
    result = json.loads(capsys.readouterr().out)
    expected = {
        "item_id": id_,
        "status": "expanded",
        "items": [
            {
                "id": id_ + ":tool:8ed3f6ad685b959ead7022518e1af76cd816f8e8ec7ccdda1ed4018e8f2223f8",
                "kind": "mcp_tool",
                "name": "alpha",
                "description": "First tool",
                "source": "claude-code",
            },
            {
                "id": id_ + ":tool:5cc10d9143b2cff082cf5fb373073b13d02d12c9a4d24a97d822d701404fb421",
                "kind": "mcp_tool",
                "name": "zeta",
                "description": "",
                "source": "claude-code",
            },
        ],
        "relations": [],
        "message": "Tools listed.",
    }
    for item, got, name in zip(expected["items"], result["items"], ("alpha", "zeta"), strict=True):
        item["disabled"] = False
        item.update(origin=None, scope="global", project=None, changed_on=None)  # Item fields added since this test was written
        # Ids are keyed per process: stable here, never the plain digest of the raw tool name.
        assert got["id"].startswith(id_ + ":tool:") and len(got["id"]) == len(id_) + 6 + 64
        assert got["id"] != id_ + ":tool:" + sha256(name.encode()).hexdigest()
        item["id"] = got["id"]
    expected["relations"] = [{"source": id_, "target": i["id"], "kind": "contains"} for i in expected["items"]]
    assert result == expected
    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=query), base_url=BASE_URL)
    assert client.post("/api/expand", json={"id": id_}).json() == expected
    assert len(calls) == 2


def test_real_synthetic_stdio_pagination_and_cleanup(tmp_path, monkeypatch, capfd):
    import os
    import sys
    from pathlib import Path

    fixture = Path(__file__).parent / "fixtures" / "expansion" / "server.py"
    record = tmp_path / "protocol.jsonl"
    config, saved, id_ = setup_scan(
        tmp_path, monkeypatch, {"fixture": {"command": sys.executable, "args": [str(fixture), "success", str(record)]}}
    )
    monkeypatch.setenv("EXPANSION_AMBIENT_SENTINEL", "never-inherit")
    for name in ("LOGNAME", "PATH", "SHELL", "TERM", "USER"):
        monkeypatch.setenv(name, "ambient-fixture-" + name)
    before = saved.read_bytes(), (config / ".mcp.json").read_bytes()
    assert main(["expand", id_, "--config-dir", str(config), "--file", str(saved)]) == 0
    captured = capfd.readouterr()
    assert "FIXTURE_LEAK" not in captured.out + captured.err
    result = json.loads(captured.out)
    assert result["status"] == "expanded"
    assert [i["name"] for i in result["items"]] == ["alpha", "zeta"]
    messages = [json.loads(line) for line in record.read_text().splitlines()]
    process, *protocol = messages
    assert process["cwd"] == str(config.resolve())
    assert process["sentinel"] is None
    assert process["home"] != str(Path.home())
    assert not Path(process["home"]).exists()
    assert process["environment"] == {
        "HOME": process["home"],
        "LOGNAME": "constellation",
        "PATH": "/usr/bin:/bin",
        "SHELL": "/bin/sh",
        "TERM": "dumb",
        "USER": "constellation",
    }
    assert [m["method"] for m in protocol] == ["initialize", "notifications/initialized", "tools/list", "tools/list"]
    assert protocol[-1]["params"]["cursor"] == "page-two"
    assert protocol[-2].get("params", {}).get("cursor") is None
    assert not {"sampling", "roots", "elicitation"} & protocol[0]["params"]["capabilities"].keys()
    with __import__("pytest").raises(ProcessLookupError):
        os.kill(process["pid"], 0)
    assert "FIXTURE_LEAK" not in json.dumps(result)
    assert before == (saved.read_bytes(), (config / ".mcp.json").read_bytes())


def test_unreachable_is_successful_result_and_no_partial_tools(tmp_path, monkeypatch, capsys):
    config, saved, id_ = setup_scan(tmp_path, monkeypatch)

    async def unreachable(registration):
        raise OSError("fixture-secret-must-not-escape")

    assert main(["expand", id_, "--config-dir", str(config), "--file", str(saved)], expansion_query=unreachable) == 0
    result = json.loads(capsys.readouterr().out)
    assert result == {
        "item_id": id_,
        "status": "unreachable",
        "items": [],
        "relations": [],
        "message": "The configured MCP server is unreachable.",
    }
    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=unreachable), base_url=BASE_URL)
    response = client.post("/api/expand", json={"id": id_})
    assert response.status_code == 200 and response.json() == result

    for error in (
        RuntimeError("fixture-secret"),
        TypeError("fixture-secret"),
        ExceptionGroup("fixture-secret", [RuntimeError("fixture-secret")]),
    ):

        async def failed(registration, error=error):
            raise error

        assert main(["expand", id_, "--config-dir", str(config), "--file", str(saved)], expansion_query=failed) == 0
        output = capsys.readouterr()
        assert json.loads(output.out) == result
        assert "fixture-secret" not in output.out + output.err
        client = TestClient(server.create_app(saved, config_dir=config, expansion_query=failed), base_url=BASE_URL)
        response = client.post("/api/expand", json={"id": id_})
        assert response.status_code == 200 and response.json() == result


def test_empty_tools_and_duplicate_identity_fail_safely(tmp_path, monkeypatch):
    config, saved, id_ = setup_scan(tmp_path, monkeypatch)
    tools = []

    async def query(registration):
        return tools

    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=query), base_url=BASE_URL)
    empty = client.post("/api/expand", json={"id": id_}).json()
    assert empty == {"item_id": id_, "status": "expanded", "items": [], "relations": [], "message": "Tools listed."}
    tools.extend([("same", "first"), ("same", "second")])
    conflict = client.post("/api/expand", json={"id": id_}).json()
    assert conflict["status"] == "unreachable" and conflict["items"] == [] and conflict["relations"] == []
    tools[:] = [("same", None), ("same", None)]
    identical = client.post("/api/expand", json={"id": id_}).json()
    assert identical["status"] == "expanded" and len(identical["items"]) == 1


def test_short_explicit_values_are_never_needles_and_secret_names_do_not_collide(tmp_path, monkeypatch, capsys, caplog):
    env = {"SECRET": "xy", "LONG": "Q7-fixture-env-value", "EMPTY": ""}
    config, saved, id_ = setup_scan(tmp_path, monkeypatch, {"fixture": {"command": "synthetic", "env": env}})

    async def query(registration):
        assert registration.env == env
        return [("tool-Q7-fixture-env-value", "Use xy; token=some-private-value"), ("tool-[REDACTED]", "safe")]

    assert main(["expand", id_, "--config-dir", str(config), "--file", str(saved)], expansion_query=query) == 0
    text = capsys.readouterr().out
    assert "Q7-fixture-env-value" not in text and "some-private-value" not in text
    result = json.loads(text)
    assert [i["name"] for i in result["items"]] == ["tool-[REDACTED]", "tool-[REDACTED]"]
    assert len({i["id"] for i in result["items"]}) == 2
    assert "safe" in text and "Use xy; token=[REDACTED]" in text  # "xy" is under 8 chars: never a needle
    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=query), base_url=BASE_URL)
    assert client.post("/api/expand", json={"id": id_}).json() == result
    assert "Q7-fixture-env-value" not in caplog.text


def test_expansion_never_loads_environment_bodies_or_providers(tmp_path, monkeypatch):
    from pathlib import Path

    import constellation
    import constellation.claude_code as adapter
    import constellation.cli as cli

    config, saved, id_ = setup_scan(tmp_path, monkeypatch)

    def forbidden(*args, **kwargs):
        raise AssertionError("Expansion crossed a private boundary")

    for module, attr in (
        (cli, "load_env"),
        (cli, "read_secrets"),
        (adapter, "_read_root"),
        (constellation, "scan"),
        (constellation, "read_usage"),
    ):
        monkeypatch.setattr(module, attr, forbidden)
    original = Path.read_text

    def private_read(path, *args, **kwargs):
        assert path.name not in (".env", "SKILL.md")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", private_read)

    async def query(registration):
        return [("safe", None)]

    assert main(["expand", id_, "--config-dir", str(config), "--file", str(saved)], expansion_query=query) == 0
    calls = []
    assert main(["open", str(saved), "--config-dir", str(config)], expansion_query=query, serve=lambda app, *_: calls.append(app)) == 0
    client = TestClient(calls[0], base_url=BASE_URL)
    assert client.get("/api/constellation").status_code == 200
    assert client.post("/api/expand", json={"id": id_}).json()["status"] == "expanded"


def test_no_launch_for_connectors_other_kinds_removed_or_mismatched_items(tmp_path, monkeypatch):
    import pytest

    config, saved, id_ = setup_scan(tmp_path, monkeypatch)
    data = json.loads(saved.read_text())

    async def never(registration):
        pytest.fail("must not launch")

    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=never), base_url=BASE_URL)
    for field, value in (("source", "other"), ("kind", "skill"), ("kind", "connector")):
        changed = json.loads(json.dumps(data))
        changed["items"][0][field] = value
        saved.write_text(json.dumps(changed))
        assert client.post("/api/expand", json={"id": id_}).json() == {
            "item_id": id_,
            "status": "not_expandable",
            "items": [],
            "relations": [],
            "message": "This Item has no local MCP tool list.",
        }
    saved.write_text(json.dumps(data))
    for servers in ({},):
        (config / ".mcp.json").write_text(json.dumps({"mcpServers": servers}))
        assert client.post("/api/expand", json={"id": id_}).json() == {
            "item_id": id_,
            "status": "unreachable",
            "items": [],
            "relations": [],
            "message": "The configured MCP server is unreachable.",
        }
    (config / ".mcp.json").unlink()
    assert client.post("/api/expand", json={"id": id_}).json() == {
        "item_id": id_,
        "status": "unreachable",
        "items": [],
        "relations": [],
        "message": "The configured MCP server is unreachable.",
    }
    assert client.post("/api/expand", json={"id": "unknown"}).status_code == 404


def test_missing_root_is_unavailable_and_cli_input_errors_exit_two(tmp_path, monkeypatch, capsys):
    import pytest

    config, saved, id_ = setup_scan(tmp_path, monkeypatch)

    async def never(registration):
        pytest.fail("must not launch")

    client = TestClient(server.create_app(saved, expansion_query=never), base_url=BASE_URL)
    assert client.post("/api/expand", json={"id": id_}).json() == {
        "item_id": id_,
        "status": "unavailable",
        "items": [],
        "relations": [],
        "message": "Open with --config-dir to enable live Expansion.",
    }
    assert main(["expand", "unknown", "--config-dir", str(config), "--file", str(saved)], expansion_query=never) == 2
    assert "Unknown Item" in capsys.readouterr().err
    client = TestClient(server.create_app(saved, config_dir=tmp_path / "missing", expansion_query=never), base_url=BASE_URL)
    assert client.post("/api/expand", json={"id": id_}).status_code == 422
    assert main(["expand", id_, "--config-dir", str(tmp_path / "missing"), "--file", str(saved)], expansion_query=never) == 2
    saved.unlink()
    assert client.post("/api/expand", json={"id": id_}).status_code == 404
    assert main(["expand", id_, "--config-dir", str(config), "--file", str(saved)], expansion_query=never) == 2


def test_host_origin_media_and_body_guards_reject_before_config_reads(tmp_path, monkeypatch):
    from pathlib import Path

    import pytest

    config, saved, id_ = setup_scan(tmp_path, monkeypatch)

    async def never(registration):
        pytest.fail("must not launch")

    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=never), base_url=BASE_URL)
    original = Path.read_text

    def no_config(path, *args, **kwargs):
        assert path == saved, "unsafe request read config"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", no_config)
    for headers in ({"host": "evil:8765"}, {"origin": "http://evil"}, {"sec-fetch-site": "cross-site"}):
        assert client.post("/api/expand", json={"id": id_}, headers=headers).status_code == 403
    assert client.post("/api/expand", content='{"id":"unknown"}').status_code == 415
    for body in ({}, {"id": 1}, {"id": id_, "command": "arbitrary"}, {"id": id_, "config_dir": "arbitrary"}, []):
        assert client.post("/api/expand", json=body).status_code == 422
    assert client.post("/api/expand", content="{", headers={"content-type": "application/json"}).status_code == 422
    assert client.get("/api/expand").status_code == 404
    assert client.get("/api/constellation").status_code == 200


def test_root_and_active_plugin_same_name_resolve_exact_registration(tmp_path, monkeypatch):
    config, saved, id_ = setup_scan(tmp_path, monkeypatch)
    for version in ("1", "2"):
        root = config / "plugins" / "cache" / "fixture-market" / "plugin" / version
        (root / ".claude-plugin").mkdir(parents=True)
        (root / ".claude-plugin" / "plugin.json").write_text('{"name":"invented-plugin"}')
        (root / ".mcp.json").write_text(json.dumps({"mcpServers": {"fixture": {"command": "version-" + version}}}))
    active = config / "plugins" / "cache" / "fixture-market" / "plugin" / "1"
    (config / "plugins" / "installed_plugins.json").write_text(json.dumps({"plugins": {"plugin@market": [{"installPath": str(active)}]}}))
    saved.write_text(json.dumps(asdict(scan(config, offline=True, usage=False))))
    calls = []

    async def query(registration):
        calls.append((registration.command, registration.cwd))
        return []

    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=query), base_url=BASE_URL)
    plugin_id = "claude-code:mcp_server:invented-plugin/fixture"
    assert client.post("/api/expand", json={"id": plugin_id}).json()["status"] == "expanded"
    assert client.post("/api/expand", json={"id": id_}).json()["status"] == "expanded"
    assert calls == [("version-1", active.resolve()), ("synthetic", config.resolve())]


def test_malformed_scan_config_and_unsupported_substitutions_do_not_launch(tmp_path, monkeypatch):
    import pytest

    config, saved, id_ = setup_scan(tmp_path, monkeypatch)
    original = saved.read_bytes()

    async def never(registration):
        pytest.fail("must not launch")

    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=never), base_url=BASE_URL)
    for data in (
        [],
        {},
        {"items": {}},
        {"items": [None]},
        {"items": [{"id": id_}]},
        {"items": [{"id": id_, "kind": 2, "source": "claude-code"}]},
    ):
        saved.write_text(json.dumps(data))
        assert client.post("/api/expand", json={"id": id_}).status_code == 422
    saved.write_bytes(original)
    data = json.loads(original)
    data["items"] *= 2
    saved.write_text(json.dumps(data))
    assert client.post("/api/expand", json={"id": id_}).status_code == 422
    saved.write_bytes(original)
    for data in (
        "{",
        '{"mcpServers":{"fixture":{}}}',
        '{"mcpServers":{"fixture":{"command":"synthetic","args":[1]}}}',
        '{"mcpServers":{"fixture":{"command":"synthetic","env":{"secret":1}}}}',
    ):
        (config / ".mcp.json").write_text(data)
        assert client.post("/api/expand", json={"id": id_}).status_code == 422
    # Like the reader, a config whose server mapping is malformed is skipped: nothing launches, nothing blocks.
    (config / ".mcp.json").write_text('{"mcpServers":[]}')
    assert client.post("/api/expand", json={"id": id_}).json()["status"] == "unreachable"
    for field, value in (("command", "${COMMAND}"), ("args", ["${CLAUDE_PLUGIN_ROOT}/main.js"]), ("env", {"TOKEN": "${TOKEN}"})):
        (config / ".mcp.json").write_text(json.dumps({"mcpServers": {"fixture": {"command": "synthetic", field: value}}}))
        assert client.post("/api/expand", json={"id": id_}).json() == {
            "item_id": id_,
            "status": "unreachable",
            "items": [],
            "relations": [],
            "message": "The configured MCP server is unreachable.",
        }


def test_synthetic_failures_hide_diagnostics_and_reap_children(tmp_path, monkeypatch, capfd, caplog):
    import logging
    import os
    import sys
    from pathlib import Path

    import pytest

    import constellation.expansion as expansion

    config, saved, id_ = setup_scan(tmp_path, monkeypatch)
    monkeypatch.setattr(expansion, "QUERY_TIMEOUT", 1.0)
    caplog.set_level(logging.DEBUG)
    fixture = Path(__file__).parent / "fixtures" / "expansion" / "server.py"
    for mode in ("failure", "malformed", "late-failure", "repeated", "timeout", "empty", "stubborn"):
        monkeypatch.setattr(expansion, "QUERY_TIMEOUT", 10.0 if mode == "stubborn" else 1.0)
        record = tmp_path / (mode + ".jsonl")
        (config / ".mcp.json").write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "fixture": {
                            "command": sys.executable,
                            "args": [str(fixture), mode, str(record)],
                            "env": {"FIXTURE_SECRET": "invented-local-secret"},
                        }
                    }
                }
            )
        )
        assert main(["expand", id_, "--config-dir", str(config), "--file", str(saved)]) == 0
        output = capfd.readouterr()
        result = json.loads(output.out)
        assert result["status"] == ("expanded" if mode in ("empty", "stubborn") else "unreachable")
        if mode != "stubborn":
            assert result["items"] == [] and result["relations"] == []
        assert "FIXTURE_LEAK" not in output.out + output.err + caplog.text
        assert "invented-local-secret" not in output.out + output.err + caplog.text
        if mode == "repeated":
            assert sum(json.loads(line).get("method") == "tools/list" for line in record.read_text().splitlines()) == 2
        process = json.loads(record.read_text().splitlines()[0])
        assert process["configured"] == "invented-local-secret"
        with pytest.raises(ProcessLookupError):
            os.kill(process["pid"], 0)
    (config / ".mcp.json").write_text('{"mcpServers":{"fixture":{"command":"/missing-fixture-command"}}}')
    assert main(["expand", id_, "--config-dir", str(config), "--file", str(saved)]) == 0
    assert json.loads(capfd.readouterr().out)["status"] == "unreachable"


def test_waiting_expansion_keeps_get_responsive_and_cancellation_reaps(tmp_path, monkeypatch, caplog):
    import logging
    import os
    import sys
    import time
    from pathlib import Path

    import anyio
    import httpx
    import pytest

    fixture = Path(__file__).parent / "fixtures" / "expansion" / "server.py"
    record = tmp_path / "cancelled.jsonl"
    config, saved, id_ = setup_scan(
        tmp_path, monkeypatch, {"fixture": {"command": sys.executable, "args": [str(fixture), "timeout", str(record)]}}
    )
    app = server.create_app(saved, config_dir=config)

    async def requests():
        started = anyio.Event()
        scopes = []
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client:

            async def post():
                with anyio.CancelScope() as scope:
                    scopes.append(scope)
                    started.set()
                    await client.post("/api/expand", json={"id": id_})
                    pytest.fail("a cancelled Expansion must not report success")

            async with anyio.create_task_group() as group:
                group.start_soon(post)
                await started.wait()
                with anyio.fail_after(2):
                    while not record.exists():
                        await anyio.sleep(0.01)
                    with anyio.fail_after(0.5):
                        response = await client.get("/api/constellation")
                    assert response.status_code == 200
                logging.getLogger("mcp.client.stdio").warning("concurrent diagnostics stay visible")
                scopes[0].cancel()
            assert (await client.get("/api/constellation")).status_code == 200
            (config / ".mcp.json").write_text(
                json.dumps(
                    {"mcpServers": {"fixture": {"command": sys.executable, "args": [str(fixture), "empty", str(tmp_path / "retry.jsonl")]}}}
                )
            )
            assert (await client.post("/api/expand", json={"id": id_})).json()["status"] == "expanded"

    before = time.monotonic()
    anyio.run(requests)
    assert time.monotonic() - before < 7
    assert "concurrent diagnostics stay visible" in caplog.text
    process = json.loads(record.read_text().splitlines()[0])
    with pytest.raises(ProcessLookupError):
        os.kill(process["pid"], 0)


def test_aggregate_deadline_covers_all_pages_and_unrelated_logs_survive(tmp_path, monkeypatch, caplog):
    import logging

    import anyio

    import constellation.expansion as expansion

    config, saved, id_ = setup_scan(tmp_path, monkeypatch)
    monkeypatch.setattr(expansion, "QUERY_TIMEOUT", 0.02)

    async def query(registration):
        logging.getLogger("application-fixture").warning("unrelated request still logs")
        await anyio.sleep(0.05)
        return [("never-partial", "private")]

    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=query), base_url=BASE_URL)
    result = client.post("/api/expand", json={"id": id_}).json()
    assert result["status"] == "unreachable"
    assert result["items"] == [] and result["relations"] == []
    assert "unrelated request still logs" in caplog.text


def test_real_stdio_deadline_is_shared_by_initialization_and_pages(tmp_path, monkeypatch):
    import sys
    from pathlib import Path

    import constellation.expansion as expansion

    fixture = Path(__file__).parent / "fixtures" / "expansion" / "server.py"
    record = tmp_path / "slow.jsonl"
    config, saved, id_ = setup_scan(
        tmp_path, monkeypatch, {"fixture": {"command": sys.executable, "args": [str(fixture), "slow", str(record)]}}
    )
    monkeypatch.setattr(expansion, "QUERY_TIMEOUT", 1.5)
    client = TestClient(server.create_app(saved, config_dir=config), base_url=BASE_URL)
    response = client.post("/api/expand", json={"id": id_})
    assert response.status_code == 200
    assert response.json()["status"] == "unreachable"
    assert response.json()["items"] == []
    assert [json.loads(line).get("method") for line in record.read_text().splitlines()][-1] == "tools/list"


def test_asyncio_debug_does_not_log_private_command_arguments(tmp_path, monkeypatch, caplog):
    import asyncio
    import logging
    import sys
    from pathlib import Path

    import anyio
    import httpx

    fixture = Path(__file__).parent / "fixtures" / "expansion" / "server.py"
    record = tmp_path / "invented-argument-secret.jsonl"
    executable = tmp_path / "invented-command-secret"
    executable.symlink_to(sys.executable)
    config, saved, id_ = setup_scan(
        tmp_path, monkeypatch, {"fixture": {"command": str(executable), "args": [str(fixture), "success", str(record)]}}
    )
    app = server.create_app(saved, config_dir=config)
    caplog.set_level(logging.DEBUG)

    async def request():
        loop = asyncio.get_running_loop()
        loop.set_debug(True)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client:
                assert (await client.post("/api/expand", json={"id": id_})).json()["status"] == "expanded"
        finally:
            loop.set_debug(False)

    anyio.run(request)
    assert "invented-argument-secret" not in caplog.text
    assert "invented-command-secret" not in caplog.text


def test_each_invalid_setting_and_ambiguous_registration_is_input_failure(tmp_path, monkeypatch):
    import pytest

    config, saved, id_ = setup_scan(tmp_path, monkeypatch)

    async def never(registration):
        pytest.fail("must not launch")

    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=never), base_url=BASE_URL)
    for settings in (
        {"command": ""},
        {"command": "synthetic", "args": "abc"},
        {"command": "synthetic", "args": {}},
        {"command": "synthetic", "env": []},
    ):
        (config / ".mcp.json").write_text(json.dumps({"mcpServers": {"fixture": settings}}))
        assert client.post("/api/expand", json={"id": id_}).status_code == 422
    data = json.loads(saved.read_text())
    for field, value in (("id", 42), ("kind", None), ("source", 42)):
        invalid = json.loads(json.dumps(data))
        invalid["items"][0][field] = value
        saved.write_text(json.dumps(invalid))
        assert client.post("/api/expand", json={"id": id_}).status_code == 422
    plugin = config / "plugins" / "cache" / "market" / "plugin" / "1"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text('{"name":"plugin"}')
    settings = {"command": "synthetic"}
    (config / ".mcp.json").write_text(json.dumps({"mcpServers": {"plugin/fixture": settings}}))
    (plugin / ".mcp.json").write_text(json.dumps({"mcpServers": {"fixture": settings}}))
    ambiguous = "claude-code:mcp_server:plugin/fixture"
    data["items"][0]["id"] = ambiguous
    saved.write_text(json.dumps(data))
    assert client.post("/api/expand", json={"id": ambiguous}).status_code == 422


def test_unreadable_config_and_failed_root_resolution_are_local_input_errors(tmp_path, monkeypatch, capsys):
    from pathlib import Path

    import pytest

    config, saved, id_ = setup_scan(tmp_path, monkeypatch)

    async def never(registration):
        pytest.fail("must not launch")

    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=never), base_url=BASE_URL)
    original = Path.read_text

    def unreadable(path, *args, **kwargs):
        if path.name == ".mcp.json":
            raise OSError("fixture-local-secret")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", unreadable)
    assert client.post("/api/expand", json={"id": id_}).status_code == 422
    monkeypatch.setattr(Path, "read_text", original)
    resolve = Path.resolve

    def unavailable(path, *args, **kwargs):
        if path == config:
            raise OSError("fixture-local-secret")
        return resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", unavailable)
    response = client.post("/api/expand", json={"id": id_})
    assert response.status_code == 422 and "fixture-local-secret" not in response.text
    assert main(["expand", id_, "--config-dir", str(config), "--file", str(saved)], expansion_query=never) == 2
    assert "fixture-local-secret" not in capsys.readouterr().err


def test_native_asyncio_cancellation_reaps_the_owned_fixture_process(tmp_path, monkeypatch):
    import asyncio
    import os
    import sys
    import threading
    from pathlib import Path

    import httpx
    import pytest

    fixture = Path(__file__).parent / "fixtures" / "expansion" / "server.py"
    record = tmp_path / "native-cancelled.jsonl"
    config, saved, id_ = setup_scan(
        tmp_path, monkeypatch, {"fixture": {"command": sys.executable, "args": [str(fixture), "timeout", str(record)]}}
    )
    app = server.create_app(saved, config_dir=config)

    watchdog_fired = threading.Event()

    def stop_stalled_child(pid):
        watchdog_fired.set()
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass

    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client:
            task = asyncio.create_task(client.post("/api/expand", json={"id": id_}))
            async with asyncio.timeout(2):
                while not record.exists():
                    await asyncio.sleep(0.01)
            process = json.loads(record.read_text().splitlines()[0])
            # wait_for can exceed its deadline while waiting for cancellation cleanup.
            # A watchdog bounds the fixture too, and firing it must fail this test.
            watchdog = threading.Timer(9, stop_stalled_child, args=(process["pid"],))
            watchdog.start()
            try:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(task, timeout=7)
                assert (await client.get("/api/constellation")).status_code == 200
            finally:
                watchdog.cancel()
            assert not watchdog_fired.is_set()

    asyncio.run(request())
    process = json.loads(record.read_text().splitlines()[0])
    with pytest.raises(ProcessLookupError):
        os.kill(process["pid"], 0)


def test_selected_config_known_secrets_are_redacted_from_cli_and_api(tmp_path, monkeypatch, capsys):
    config, saved, id_ = setup_scan(tmp_path, monkeypatch)
    (config / ".credentials.json").write_text('{"fixture":"inventedcredential"}')
    (config / "settings.json").write_text('{"env":{"FIXTURE":"inventedsetting"}}')

    async def query(registration):
        return [("inventedcredential-tool", "Use inventedsetting and inventedcredential")]

    assert main(["expand", id_, "--config-dir", str(config), "--file", str(saved)], expansion_query=query) == 0
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result["status"] == "expanded"
    assert result["items"][0]["name"] == "[REDACTED]-tool"
    assert result["items"][0]["description"] == "Use [REDACTED] and [REDACTED]"
    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=query), base_url=BASE_URL)
    assert client.post("/api/expand", json={"id": id_}).json() == result


def test_tool_metadata_limits_fail_without_partial_children(tmp_path, monkeypatch):
    config, saved, id_ = setup_scan(tmp_path, monkeypatch)
    tools = [("tool-" + str(i), "safe") for i in range(1000)]
    tools[0] = ("n" * 4096, "é" * 2048)

    async def query(registration):
        return tools

    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=query), base_url=BASE_URL)
    result = client.post("/api/expand", json={"id": id_}).json()
    assert result["status"] == "expanded" and len(result["items"]) == 1000
    assert any(item["description"] == "é" * 2048 for item in result["items"])
    for excessive in ([("safe", None)] * 1001, [("safe", "é" * 2048 + "x")], [("n" * 4097, None)]):
        tools[:] = excessive
        result = client.post("/api/expand", json={"id": id_}).json()
        assert result["status"] == "unreachable" and result["items"] == [] and result["relations"] == []


def test_stdio_discovery_bounds_pages_and_accumulated_tools(tmp_path, monkeypatch):
    import sys
    from pathlib import Path

    config, saved, id_ = setup_scan(tmp_path, monkeypatch)
    fixture = Path(__file__).parent / "fixtures" / "expansion" / "server.py"
    client = TestClient(server.create_app(saved, config_dir=config), base_url=BASE_URL)
    for mode in ("pages-limit", "pages-over", "tools-limit", "tools-over", "tools-pages-over", "text-limit", "text-over", "name-over"):
        record = tmp_path / (mode + ".jsonl")
        (config / ".mcp.json").write_text(
            json.dumps({"mcpServers": {"fixture": {"command": sys.executable, "args": [str(fixture), mode, str(record)]}}})
        )
        result = client.post("/api/expand", json={"id": id_}).json()
        assert result["status"] == ("expanded" if mode in ("pages-limit", "tools-limit", "text-limit") else "unreachable")
        assert len(result["items"]) == len(result["relations"]) == (1 if mode in ("tools-limit", "text-limit") else 0)
        count = sum(json.loads(line).get("method") == "tools/list" for line in record.read_text().splitlines())
        assert count == (2 if mode == "tools-pages-over" else 100 if mode.startswith("pages-") else 1)


def test_redaction_obeys_aggregate_deadline_and_does_not_block_get(tmp_path, monkeypatch):
    import time

    import anyio
    import httpx

    import constellation.expansion as expansion

    config, saved, id_ = setup_scan(tmp_path, monkeypatch)
    original = expansion.redact

    def slow_redact(text, known):
        time.sleep(0.6)  # Keep blocked-worker latency well above normal scheduling noise under mutation load.
        return original(text, known)

    monkeypatch.setattr(expansion, "redact", slow_redact)
    monkeypatch.setattr(expansion, "QUERY_TIMEOUT", 0.05)

    async def query(registration):
        return [("safe", "safe")]

    app = server.create_app(saved, config_dir=config, expansion_query=query)

    async def requests():
        results = []
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client:

            async def post():
                results.append((await client.post("/api/expand", json={"id": id_})).json())

            before = time.monotonic()
            async with anyio.create_task_group() as group:
                group.start_soon(post)
                await anyio.sleep(0.01)
                assert (await client.get("/api/constellation")).status_code == 200
                assert time.monotonic() - before < 0.35
            assert time.monotonic() - before < 0.35
        assert results[0]["status"] == "unreachable"
        assert results[0]["items"] == [] and results[0]["relations"] == []

    anyio.run(requests)


def test_only_one_inflight_launch_per_server_id_and_retry_after_completion(tmp_path, monkeypatch):
    import anyio
    import httpx

    config, saved, id_ = setup_scan(tmp_path, monkeypatch, {"fixture": {"command": "synthetic"}, "other": {"command": "other"}})

    async def requests():
        with anyio.fail_after(3):
            started, release = anyio.Event(), anyio.Event()
            launches = []
            results = []

            async def query(registration):
                launches.append(registration.command)
                if registration.command == "synthetic":
                    started.set()
                    await release.wait()
                return []

            app = server.create_app(saved, config_dir=config, expansion_query=query)
            second_app = server.create_app(saved, config_dir=config, expansion_query=query)
            async with (
                httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as client,
                httpx.AsyncClient(transport=httpx.ASGITransport(app=second_app), base_url=BASE_URL) as second,
            ):

                async def first():
                    results.append((await client.post("/api/expand", json={"id": id_})).json())

                async with anyio.create_task_group() as group:
                    group.start_soon(first)
                    with anyio.fail_after(1):
                        await started.wait()
                    with anyio.fail_after(0.5):
                        duplicate = (await second.post("/api/expand", json={"id": id_})).json()
                    assert duplicate["status"] == "unreachable" and duplicate["items"] == [] and duplicate["relations"] == []
                    other = await second.post("/api/expand", json={"id": "claude-code:mcp_server:other"})
                    assert other.json()["status"] == "expanded"
                    assert launches == ["synthetic", "other"]
                    release.set()
                assert results[0]["status"] == "expanded"
                assert (await second.post("/api/expand", json={"id": id_})).json()["status"] == "expanded"
                assert launches == ["synthetic", "other", "synthetic"]

    anyio.run(requests)


def test_parent_mcp_diagnostics_are_private_only_during_discovery(tmp_path, monkeypatch, caplog):
    import logging
    import sys
    from pathlib import Path

    import constellation.expansion as expansion

    fixture = Path(__file__).parent / "fixtures" / "expansion" / "server.py"
    config, saved, id_ = setup_scan(
        tmp_path, monkeypatch, {"fixture": {"command": sys.executable, "args": [str(fixture), "empty", str(tmp_path / "parent-log.jsonl")]}}
    )
    original = expansion.ClientSession.initialize

    async def initialize(session):
        logging.getLogger("mcp").warning("invented-parent-diagnostic-secret")
        return await original(session)

    monkeypatch.setattr(expansion.ClientSession, "initialize", initialize)
    client = TestClient(server.create_app(saved, config_dir=config), base_url=BASE_URL)
    assert client.post("/api/expand", json={"id": id_}).json()["status"] == "expanded"
    assert "invented-parent-diagnostic-secret" not in caplog.text
    logging.getLogger("mcp").warning("outside request stays visible")
    assert "outside request stays visible" in caplog.text


def test_page_validation_worker_wait_obeys_deadline(tmp_path, monkeypatch):
    import sys
    import time
    from pathlib import Path

    import constellation.expansion as expansion

    fixture = Path(__file__).parent / "fixtures" / "expansion" / "server.py"
    config, saved, id_ = setup_scan(
        tmp_path, monkeypatch, {"fixture": {"command": sys.executable, "args": [str(fixture), "empty", str(tmp_path / "validation.jsonl")]}}
    )
    original = expansion._validate_tools

    def slow_validation(tools):
        time.sleep(0.8)  # Simulate page processing latency at the time boundary.
        original(tools)

    monkeypatch.setattr(expansion, "_validate_tools", slow_validation)
    monkeypatch.setattr(expansion, "QUERY_TIMEOUT", 0.2)
    client = TestClient(server.create_app(saved, config_dir=config), base_url=BASE_URL)
    before = time.monotonic()
    result = client.post("/api/expand", json={"id": id_}).json()
    assert time.monotonic() - before < 0.6
    assert result["status"] == "unreachable" and result["items"] == [] and result["relations"] == []


def test_expansion_selects_main_reader_user_local_and_manifest_servers(tmp_path, monkeypatch):
    config, saved, _ = setup_scan(tmp_path, monkeypatch)
    (config / ".claude.json").write_text(
        json.dumps(
            {
                "mcpServers": {"same": {"command": "user-command"}},
                "projects": {
                    "/invented/z": {"mcpServers": {"same": {"command": "local-z"}}},
                    "/invented/a": {"mcpServers": {"same": {"command": "local-a"}}},
                },
            }
        )
    )
    plugin = config / "plugins/cache/market/plugin/1"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin/plugin.json").write_text(
        json.dumps(
            {
                "name": "plugin",
                "mcpServers": [{"same": {"command": "inline"}}, "extra.json", "bundle.mcpb"],
            }
        )
    )
    (plugin / "extra.json").write_text(json.dumps({"mcpServers": {"file": {"command": "manifest-file"}}}))
    data = asdict(scan(config, offline=True, usage=False))
    saved.write_text(json.dumps(data))
    expected = {
        "user/same": ("user-command", config),
        "local/1/same": ("local-a", config),
        "local/2/same": ("local-z", config),
        "plugin/same": ("inline", plugin),
        "plugin/file": ("manifest-file", plugin),
    }
    calls = []

    async def query(registration):
        calls.append((registration.command, registration.cwd))
        return [("tool", None)]

    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=query), base_url=BASE_URL)
    for scope, registration in expected.items():
        item_id = "claude-code:mcp_server:" + scope
        assert client.post("/api/expand", json={"id": item_id}).json()["status"] == "expanded"
        assert calls[-1] == registration

    bundle = client.post("/api/expand", json={"id": "claude-code:mcp_server:plugin/bundle"})
    assert bundle.status_code == 200
    assert bundle.json() == {
        "item_id": "claude-code:mcp_server:plugin/bundle",
        "status": "not_expandable",
        "items": [],
        "relations": [],
        "message": "This Item has no local MCP tool list.",
    }
    assert len(calls) == len(expected)


def test_lookup_keeps_root_servers_when_dot_claude_has_no_sibling_state(tmp_path, monkeypatch):
    config, saved, id_ = setup_scan(tmp_path, monkeypatch)
    config = config.rename(config.parent / ".claude")

    async def query(registration):
        return []

    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=query), base_url=BASE_URL)
    assert client.post("/api/expand", json={"id": id_}).json()["status"] == "expanded"
    (config / ".claude.json").write_text("[]")
    assert client.post("/api/expand", json={"id": id_}).json()["status"] == "expanded"


def test_registration_lookup_wait_is_cancellable(tmp_path, monkeypatch):
    import time

    import constellation.expansion as expansion

    config, saved, id_ = setup_scan(tmp_path, monkeypatch)
    original = expansion._registrations

    def slow(root):
        time.sleep(0.6)
        yield from original(root)

    monkeypatch.setattr(expansion, "_registrations", slow)
    monkeypatch.setattr(expansion, "QUERY_TIMEOUT", 0.05)
    client = TestClient(server.create_app(saved, config_dir=config), base_url=BASE_URL)
    before = time.monotonic()
    assert client.post("/api/expand", json={"id": id_}).json()["status"] == "unreachable"
    assert time.monotonic() - before < 0.35


def test_registration_lookup_and_query_share_one_deadline(tmp_path, monkeypatch):
    import time

    import anyio

    import constellation.expansion as expansion

    config, saved, id_ = setup_scan(tmp_path, monkeypatch)
    original = expansion._registrations

    def slow(root):
        time.sleep(0.15)
        yield from original(root)

    async def query(registration):
        await anyio.sleep(0.15)
        return []

    monkeypatch.setattr(expansion, "_registrations", slow)
    monkeypatch.setattr(expansion, "QUERY_TIMEOUT", 0.25)
    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=query), base_url=BASE_URL)
    assert client.post("/api/expand", json={"id": id_}).json()["status"] == "unreachable"


def test_lookup_ignores_non_server_project_entries_without_changing_local_numbers(tmp_path, monkeypatch):
    config, saved, _ = setup_scan(tmp_path, monkeypatch)
    (config / ".claude.json").write_text(
        json.dumps(
            {
                "projects": {
                    "/invented/a": None,
                    "/invented/b": {},
                    "/invented/c": {"mcpServers": {}},
                    "/invented/z": {"mcpServers": {"same": {"command": "selected"}}},
                }
            }
        )
    )
    saved.write_text(json.dumps(asdict(scan(config, offline=True, usage=False))))

    async def query(registration):
        assert registration.command == "selected"
        return []

    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=query), base_url=BASE_URL)
    assert client.post("/api/expand", json={"id": "claude-code:mcp_server:local/1/same"}).json()["status"] == "expanded"


def test_lookup_matches_scan_ids_redacted_with_known_config_secrets(tmp_path, monkeypatch):
    config, saved, _ = setup_scan(tmp_path, monkeypatch)
    (config / ".credentials.json").write_text(json.dumps({"fixture": "inventedregistration"}))
    (config / ".mcp.json").write_text(json.dumps({"mcpServers": {"inventedregistration": {"command": "synthetic"}}}))
    saved.write_text(json.dumps(asdict(scan(config, offline=True, usage=False))))

    async def query(registration):
        assert registration.command == "synthetic"
        return []

    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=query), base_url=BASE_URL)
    assert client.post("/api/expand", json={"id": "claude-code:mcp_server:[REDACTED]"}).json()["status"] == "expanded"


def test_lookup_skips_repeated_plugin_names_and_continues_to_later_plugins(tmp_path, monkeypatch):
    config, saved, _ = setup_scan(tmp_path, monkeypatch)
    for market, name, command in (("a", "same", "first"), ("b", "same", "second"), ("c", "other", "third")):
        root = config / f"plugins/cache/{market}/demo/1"
        (root / ".claude-plugin").mkdir(parents=True)
        (root / ".claude-plugin/plugin.json").write_text(json.dumps({"name": name, "mcpServers": {"s": {"command": command}}}))
    saved.write_text(json.dumps(asdict(scan(config, offline=True, usage=False))))
    commands = []

    async def query(registration):
        commands.append(registration.command)
        return []

    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=query), base_url=BASE_URL)
    for name in ("same", "other"):
        assert client.post("/api/expand", json={"id": f"claude-code:mcp_server:{name}/s"}).json()["status"] == "expanded"
    assert commands == ["first", "third"]


def test_lookup_supports_all_declared_bundle_extensions_without_launch(tmp_path, monkeypatch):
    config, saved, _ = setup_scan(tmp_path, monkeypatch)
    root = config / "plugins/cache/market/plugin/1"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin/plugin.json").write_text(json.dumps({"name": "plugin", "mcpServers": ["a.mcpb", "b.dxt", "c.DXT"]}))
    saved.write_text(json.dumps(asdict(scan(config, offline=True, usage=False))))

    async def never(registration):
        raise AssertionError("bundles must not launch")

    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=never), base_url=BASE_URL)
    for name in ("a", "b", "c"):
        assert client.post("/api/expand", json={"id": f"claude-code:mcp_server:plugin/{name}"}).json()["status"] == "not_expandable"


def test_lookup_rejects_manifest_files_outside_the_plugin(tmp_path, monkeypatch):
    config, saved, _ = setup_scan(tmp_path, monkeypatch)
    root = config / "plugins/cache/market/plugin/1"
    (root / ".claude-plugin").mkdir(parents=True)
    manifest = root / ".claude-plugin/plugin.json"
    manifest.write_text(json.dumps({"name": "plugin", "mcpServers": {"s": {"command": "original"}}}))
    saved.write_text(json.dumps(asdict(scan(config, offline=True, usage=False))))
    outside = tmp_path / "invented-outside.json"
    outside.write_text(json.dumps({"s": {"command": "must-not-launch"}}))
    (root / "escape.json").symlink_to(outside)

    async def never(registration):
        raise AssertionError("outside files must not launch")

    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=never), base_url=BASE_URL)
    for entry in (str(outside), "escape.json", "missing.json", 42, {"s": []}, {"s": None}):
        manifest.write_text(json.dumps({"name": "plugin", "mcpServers": entry}))
        assert client.post("/api/expand", json={"id": "claude-code:mcp_server:plugin/s"}).json()["status"] == "unreachable"


def test_url_servers_stay_single_items_without_launch_or_input_failure(tmp_path, monkeypatch, capsys):
    config, saved, id_ = setup_scan(tmp_path, monkeypatch, {"fixture": {"url": "https://fixture.invalid"}})

    async def never(registration):
        raise AssertionError("URL must not launch")

    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=never), base_url=BASE_URL)
    for settings in ({"url": "https://fixture.invalid"}, {"url": "https://fixture.invalid", "command": "synthetic"}):
        (config / ".mcp.json").write_text(json.dumps({"mcpServers": {"fixture": settings}}))
        response = client.post("/api/expand", json={"id": id_})
        assert response.status_code == 200
        assert response.json() == {
            "item_id": id_,
            "status": "not_expandable",
            "items": [],
            "relations": [],
            "message": "This Item has no local MCP tool list.",
        }
        assert main(["expand", id_, "--config-dir", str(config), "--file", str(saved)], expansion_query=never) == 0
        assert json.loads(capsys.readouterr().out)["status"] == "not_expandable"


def test_argument_values_are_redacted_from_cli_and_api_tools(tmp_path, monkeypatch, capsys):
    config, saved, id_ = setup_scan(
        tmp_path,
        monkeypatch,
        {
            "fixture": {
                "command": "synthetic",
                "args": [
                    "--token",
                    "xy",
                    "--password=invented-argument-value",
                    "--header",
                    "Authorization: Bearer opaque-header",
                    "--endpoint=https://user%3Aname:p%40ss%3Aword@fixture.invalid?token=url-query",
                ],
            },
        },
    )

    async def query(registration):
        assert registration.args[:3] == ["--token", "xy", "--password=invented-argument-value"]
        return [
            (
                "tool-xy",
                "Use invented-argument-value and xy opaque-header user:name p@ss:word url-query --password=invented-argument-value XXXX",
            )
        ]

    assert main(["expand", id_, "--config-dir", str(config), "--file", str(saved)], expansion_query=query) == 0
    output = capsys.readouterr().out
    assert "invented-argument-value" not in output
    result = json.loads(output)
    assert result["items"][0]["name"] == "tool-xy"  # under 8 chars: never a needle, so ordinary text is not garbled
    assert result["items"][0]["description"] == "Use [REDACTED] and xy [REDACTED] [REDACTED] [REDACTED] [REDACTED] [REDACTED] XXXX"
    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=query), base_url=BASE_URL)
    assert client.post("/api/expand", json={"id": id_}).json() == result


def test_sdk_child_loggers_created_during_discovery_cannot_leak(tmp_path, monkeypatch, caplog):
    import logging
    import sys
    from pathlib import Path

    import constellation.expansion as expansion

    fixture = Path(__file__).parent / "fixtures/expansion/server.py"
    config, saved, id_ = setup_scan(
        tmp_path,
        monkeypatch,
        {
            "fixture": {"command": sys.executable, "args": [str(fixture), "empty", str(tmp_path / "late-log.jsonl")]},
        },
    )
    explicit_level_loggers = []
    original = expansion.ClientSession.initialize
    logger_name = "mcp.late_fixture." + str(tmp_path)
    private_names = (logger_name, "mcp", "client", "asyncio")
    for name in private_names:
        monkeypatch.delitem(logging.Logger.manager.loggerDict, name, raising=False)

    async def initialize(session):
        for name in private_names:
            logging.getLogger(name).warning("invented-late-diagnostic-secret")
        logging.getLogger("unrelated.late_fixture").warning("unrelated logs stay visible")
        explicit = logging.getLoggerClass()(logger_name + ".explicit", logging.ERROR)
        explicit.addHandler(caplog.handler)
        explicit_level_loggers.append(explicit)
        return await original(session)

    monkeypatch.setattr(expansion.ClientSession, "initialize", initialize)
    client = TestClient(server.create_app(saved, config_dir=config), base_url=BASE_URL)
    assert client.post("/api/expand", json={"id": id_}).json()["status"] == "expanded"
    assert "invented-late-diagnostic-secret" not in caplog.text
    assert "unrelated logs stay visible" in caplog.text
    for name in private_names:
        logging.getLogger(name).warning("outside late request stays visible")
        assert any(record.name == name and record.getMessage() == "outside late request stays visible" for record in caplog.records)
    explicit_level_loggers[0].warning("below configured level stays hidden")
    explicit_level_loggers[0].error("configured error stays visible")
    assert "below configured level stays hidden" not in caplog.text
    assert "configured error stays visible" in caplog.text


def test_declared_and_implicit_plugin_mcp_file_is_one_expandable_registration(tmp_path, monkeypatch, capsys):
    config, saved, _ = setup_scan(tmp_path, monkeypatch)
    plugin = config / "plugins/cache/market/plugin/1"
    (plugin / ".claude-plugin").mkdir(parents=True)
    manifest = plugin / ".claude-plugin/plugin.json"
    manifest.write_text(json.dumps({"name": "plugin", "mcpServers": "./.mcp.json"}))
    (plugin / ".mcp.json").write_text(json.dumps({"mcpServers": {"same": {"command": "plugin-command"}}}))
    data = asdict(scan(config, offline=True, usage=False))
    saved.write_text(json.dumps(data))
    item_id = "claude-code:mcp_server:plugin/same"
    assert len([item for item in data["items"] if item["id"] == item_id]) == 1
    calls = []

    async def query(registration):
        calls.append((registration.command, registration.cwd))
        return [("tool", "Plugin tool")]

    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=query), base_url=BASE_URL)
    response = client.post("/api/expand", json={"id": item_id})
    assert response.status_code == 200 and response.json()["status"] == "expanded"
    assert main(["expand", item_id, "--config-dir", str(config), "--file", str(saved)], expansion_query=query) == 0
    assert json.loads(capsys.readouterr().out) == response.json()
    assert calls == [("plugin-command", plugin), ("plugin-command", plugin)]
    manifest.write_text(json.dumps({"name": "plugin", "mcpServers": {"same": {"command": "different-command"}}}))
    assert client.post("/api/expand", json={"id": item_id}).status_code == 422
    assert main(["expand", item_id, "--config-dir", str(config), "--file", str(saved)], expansion_query=query) == 2
    assert len(calls) == 2


def _enable(config, key, value):
    (config / "settings.json").write_text(json.dumps({"enabledPlugins": {key: value}}))


def test_disabled_plugin_server_is_not_expandable_and_never_launches(tmp_path, monkeypatch):
    config, saved, _ = setup_scan(tmp_path, monkeypatch)
    root = config / "plugins/cache/market/demo/1"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin/plugin.json").write_text(json.dumps({"name": "demo", "mcpServers": {"s": {"command": "synthetic"}}}))
    _enable(config, "demo@market", False)
    data = asdict(scan(config, offline=True, usage=False))
    saved.write_text(json.dumps(data))
    plugin_id = "claude-code:mcp_server:demo/s"
    assert next(i for i in data["items"] if i["id"] == plugin_id)["disabled"] is True

    async def never(registration):
        raise AssertionError("disabled plugin must not launch")

    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=never), base_url=BASE_URL)
    assert client.post("/api/expand", json={"id": plugin_id}).json()["status"] == "not_expandable"
    # A stale saved scan that lacks the flag is still refused when settings now disable the plugin.
    for item in data["items"]:
        item["disabled"] = False
    saved.write_text(json.dumps(data))
    assert client.post("/api/expand", json={"id": plugin_id}).json()["status"] == "not_expandable"
    # Enabled again in settings, but the saved Item says disabled: also refused.
    _enable(config, "demo@market", True)
    for item in data["items"]:
        item["disabled"] = True
    saved.write_text(json.dumps(data))
    assert client.post("/api/expand", json={"id": plugin_id}).json()["status"] == "not_expandable"


def test_non_stdio_types_never_launch_even_with_a_command(tmp_path, monkeypatch):
    config, saved, id_ = setup_scan(tmp_path, monkeypatch)

    async def never(registration):
        raise AssertionError("non-stdio must not launch")

    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=never), base_url=BASE_URL)
    for kind in ("http", "sse", "ws", "other"):
        (config / ".mcp.json").write_text(json.dumps({"mcpServers": {"fixture": {"type": kind, "command": "synthetic"}}}))
        assert client.post("/api/expand", json={"id": id_}).json()["status"] == "not_expandable"
    calls = []

    async def query(registration):
        calls.append(registration.command)
        return []

    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=query), base_url=BASE_URL)
    (config / ".mcp.json").write_text(json.dumps({"mcpServers": {"fixture": {"type": "stdio", "command": "synthetic"}}}))
    assert client.post("/api/expand", json={"id": id_}).json()["status"] == "expanded"
    assert calls == ["synthetic"]


def test_registration_repr_hides_env_and_args(tmp_path):
    from constellation.expansion import Registration

    text = repr(Registration("cmd", ["--token=invented-arg-secret"], {"K": "invented-env-secret"}, tmp_path))
    assert "invented-arg-secret" not in text and "invented-env-secret" not in text


def test_one_malformed_server_entry_does_not_block_the_others(tmp_path, monkeypatch):
    config, saved, id_ = setup_scan(tmp_path, monkeypatch)
    (config / ".mcp.json").write_text(json.dumps({"mcpServers": {"bad": "not an object", "fixture": {"command": "synthetic"}}}))
    plugin = config / "plugins/cache/market/demo/1"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin/plugin.json").write_text(json.dumps({"name": "demo", "mcpServers": [42, {"s": {"command": "p"}}]}))

    saved.write_text(json.dumps(asdict(scan(config, offline=True, usage=False))))

    async def query(registration):
        return []

    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=query), base_url=BASE_URL)
    assert client.post("/api/expand", json={"id": id_}).json()["status"] == "expanded"
    assert client.post("/api/expand", json={"id": "claude-code:mcp_server:demo/s"}).json()["status"] == "expanded"


def test_asyncio_noise_after_the_query_cannot_leak_private_values(tmp_path, monkeypatch, caplog):
    import logging

    import constellation.expansion as expansion

    monkeypatch.setattr(expansion, "_PRIVATE_TEXT", set())  # isolate from values other tests registered
    config, saved, id_ = setup_scan(
        tmp_path, monkeypatch, {"fixture": {"command": "synthetic", "args": ["invented-late-argument", "abc", "abcd"]}}
    )

    async def query(registration):
        return []

    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=query), base_url=BASE_URL)
    assert client.post("/api/expand", json={"id": id_}).json()["status"] == "expanded"
    logging.getLogger("asyncio").warning("late callback failed for invented-late-argument")
    logging.getLogger("asyncio").warning("unrelated asyncio message")
    logging.getLogger("asyncio").warning("short abc stays visible")
    logging.getLogger("asyncio").warning("four abcd hidden")
    assert "short abc stays visible" in caplog.text and "four abcd hidden" not in caplog.text
    assert "invented-late-argument" not in caplog.text
    assert "unrelated asyncio message" in caplog.text


def test_every_disabled_plugin_registration_path_is_refused_using_the_installed_key(tmp_path, monkeypatch):
    config, saved, _ = setup_scan(tmp_path, monkeypatch)
    root = config / "plugins/cache/market/demo/1"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin/plugin.json").write_text(
        json.dumps({"name": "demo", "mcpServers": [{"inline": {"command": "a"}}, "extra.json", "tool.mcpb"]})
    )
    (root / "extra.json").write_text(json.dumps({"fromfile": {"command": "b"}}))
    (root / ".mcp.json").write_text(json.dumps({"mcpServers": {"implicit": {"command": "c"}}}))
    (config / "plugins/installed_plugins.json").write_text(json.dumps({"plugins": {"custom@key": [{"installPath": str(root)}]}}))
    _enable(config, "custom@key", True)
    saved.write_text(json.dumps(asdict(scan(config, offline=True, usage=False))))
    launched = []

    async def query(registration):
        launched.append(registration.command)
        return []

    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=query), base_url=BASE_URL)
    names = ("inline", "fromfile", "implicit")
    assert [client.post("/api/expand", json={"id": f"claude-code:mcp_server:demo/{n}"}).json()["status"] for n in names] == ["expanded"] * 3
    _enable(config, "custom@key", False)
    # The default key (name@marketplace) being disabled must not matter once the installed key says enabled, and vice versa.
    for n in (*names, "tool"):
        assert client.post("/api/expand", json={"id": f"claude-code:mcp_server:demo/{n}"}).json()["status"] == "not_expandable"
    assert launched == ["a", "b", "c"]


def test_non_object_server_files_are_skipped_not_input_failures(tmp_path, monkeypatch):
    config, saved, id_ = setup_scan(tmp_path, monkeypatch)
    (config / ".mcp.json").write_text("[]")
    client = TestClient(server.create_app(saved, config_dir=config), base_url=BASE_URL)
    assert client.post("/api/expand", json={"id": id_}).json()["status"] == "unreachable"


def test_lookup_skips_a_malformed_manifest_and_continues_to_later_plugins(tmp_path, monkeypatch):
    config, saved, _ = setup_scan(tmp_path, monkeypatch)
    for market, text in (("a", "{not json"), ("b", json.dumps({"name": "good", "mcpServers": {"s": {"command": "later"}}}))):
        root = config / f"plugins/cache/{market}/demo/1"
        (root / ".claude-plugin").mkdir(parents=True)
        (root / ".claude-plugin/plugin.json").write_text(text)
    saved.write_text(json.dumps(asdict(scan(config, offline=True, usage=False))))
    commands = []

    async def query(registration):
        commands.append(registration.command)
        return []

    client = TestClient(server.create_app(saved, config_dir=config, expansion_query=query), base_url=BASE_URL)
    assert client.post("/api/expand", json={"id": "claude-code:mcp_server:good/s"}).json()["status"] == "expanded"
    assert commands == ["later"]
