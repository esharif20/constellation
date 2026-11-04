import json
import shutil
from dataclasses import asdict
from pathlib import Path

from constellation import scan

FIXTURE = Path(__file__).parent / "fixtures" / "mcp_config"


def named(result, kind):
    return {i.name: i for i in result.items if i.kind == kind}


def test_servers_come_from_claude_json_and_plugins_as_shape_only():
    result = scan(FIXTURE)
    servers = {i.id.removeprefix("claude-code:mcp_server:"): i.description for i in result.items if i.kind == "mcp_server"}

    assert servers["user/uservm"] == "stdio: runner"
    assert servers["user/userweb"] == "remote sse: https://api.example.com"
    assert servers["user/shellcmd"] == "stdio: node"
    local = [d for k, d in servers.items() if k.startswith("local/")]
    assert local == ["remote http: https://local.example.com"]
    assert servers["inl/inlsrv"] == "stdio: inlcmd"
    assert servers["inl/zbundle2"] == "remote http: https://inl.example.com"
    assert servers["nowrap/filesrv"] == "stdio: filecmd"  # a plugin.json path entry, without the wrapper
    assert servers["nowrap/wrapped"] == "stdio: nowrapcmd"  # .mcp.json without the wrapper
    assert servers["nowrap/bundle"] == "bundle: shape unknown"
    assert "nowrap/escaped" not in servers  # a path outside the plugin root is refused
    assert not any(k.startswith("broken/") for k in servers)


def test_no_planted_secret_survives_anywhere_in_the_scan():
    result = scan(FIXTURE)

    everything = json.dumps(asdict(result)) + repr(result.warnings)
    assert "PLANTED" not in everything
    assert "work/app" not in everything  # the project path stays out of ids too


def test_a_malformed_server_file_is_a_warning_with_no_file_text():
    result = scan(FIXTURE)

    assert any("broken/.mcp.json" in w and "not valid JSON" in w for w in result.warnings)
    assert "plugin nowrap" in " ".join(w for w in result.warnings if "skipped an MCP entry" in w)  # the ../escape.json entry


def test_unparseable_claude_json_is_a_warning_not_a_crash(tmp_path):
    config = tmp_path / "cfg"
    config.mkdir()
    (config / ".claude.json").write_text('{"oauth": "PLANTED_TOKEN", broken')

    result = scan(config)

    assert result.items == []
    assert result.warnings == ["could not read .claude.json: unreadable or not valid JSON"]


def test_claude_json_beside_a_dot_claude_dir_is_read_and_a_missing_one_warns(tmp_path):
    shutil.copytree(FIXTURE, tmp_path / ".claude")
    (tmp_path / ".claude" / ".claude.json").rename(tmp_path / ".claude.json")

    result = scan(tmp_path / ".claude")
    assert "uservm" in named(result, "mcp_server")

    (tmp_path / ".claude.json").unlink()
    result = scan(tmp_path / ".claude")
    assert "uservm" not in named(result, "mcp_server")
    assert any(".claude.json" in w and "not listed" in w for w in result.warnings)


def test_a_dir_not_named_dot_claude_never_looks_in_its_parent(tmp_path):
    (tmp_path / ".claude.json").write_text('{"mcpServers": {"x": {"command": "y"}}}')
    (tmp_path / "other").mkdir()

    assert scan(tmp_path / "other").items == []


def test_slash_commands_are_items_from_user_and_plugin_dirs():
    result = scan(FIXTURE)
    commands = named(result, "command")

    assert {n: c.description for n, c in commands.items()} == {
        "ship": "Ship it",
        "review": "Review the diff carefully.",  # no frontmatter: the first non-empty line
        "pc": "Plugin command line.",
    }
    assert commands["pc"].id == "claude-code:command:nowrap/pc"
    assert any("skipped command 'empty'" in w for w in result.warnings)


def test_a_disabled_plugin_and_its_contents_stay_flagged():
    result = scan(FIXTURE)
    flagged = {i.name for i in result.items if i.disabled}

    assert flagged == {"off", "offskill"}
    assert not named(result, "plugin")["inl"].disabled


def test_a_plugin_installed_outside_the_cache_is_found(tmp_path):
    config = tmp_path / "cfg"
    local = tmp_path / "market" / "mine"
    (local / ".claude-plugin").mkdir(parents=True)
    (local / ".claude-plugin" / "plugin.json").write_text('{"name": "mine", "description": "d"}')
    (local / "commands").mkdir()
    (local / "commands" / "go.md").write_text("Go.\n")
    (config / "plugins").mkdir(parents=True)
    (config / "plugins" / "installed_plugins.json").write_text(json.dumps({"plugins": {"mine@local": [{"installPath": str(local)}]}}))
    (config / "settings.json").write_text('{"enabledPlugins": {"mine@local": false}}')

    result = scan(config)

    assert {i.id: i.disabled for i in result.items} == {"claude-code:plugin:mine": True, "claude-code:command:mine/go": True}


def test_tool_calls_credit_user_scope_servers_not_a_plugin_called_user(tmp_path):
    (tmp_path / ".claude.json").write_text(
        '{"mcpServers": {"srv": {"command": "x"}}, "projects": {"/p": {"mcpServers": {"loc": {"command": "y"}}}}}'
    )
    call = {
        "type": "assistant",
        "timestamp": "2026-11-02T12:00:00Z",
        "message": {"content": [{"type": "tool_use", "name": "mcp__srv__go", "id": "1", "input": {}}]},
    }
    transcript = tmp_path / "projects" / "p" / "s.jsonl"
    transcript.parent.mkdir(parents=True)
    other = json.loads(json.dumps(call))
    other["message"]["content"][0].update(name="mcp__loc__go", id="2")
    transcript.write_text(json.dumps(call) + "\n" + json.dumps(other) + "\n")

    result = scan(tmp_path)

    assert result.usage["claude-code:mcp_server:user/srv"].count == 1
    assert [u.count for k, u in result.usage.items() if ":local/" in k] == [1]
