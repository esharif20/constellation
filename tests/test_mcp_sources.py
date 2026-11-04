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


def shapes(tmp_path, servers):
    (tmp_path / ".claude.json").write_text(json.dumps({"mcpServers": servers}))
    return {i.name: i.description for i in scan(tmp_path).items if i.kind == "mcp_server"}


def test_stdio_shape_skips_env_assignments_and_never_emits_an_equals_word(tmp_path):
    got = shapes(
        tmp_path,
        {
            "a": {"command": "GITHUB_PAT=abc123zz npx srv"},
            "b": {"command": "A=1 B=2 /usr/bin/runner x"},
            "c": {"command": "ONLY=secret9"},
            "d": {"command": "--token=abc123zz"},
        },
    )

    assert got == {"a": "stdio: npx", "b": "stdio: runner", "c": "stdio: unknown", "d": "stdio: unknown"}


def test_a_scheme_less_url_never_prints_its_userinfo_as_the_scheme(tmp_path):
    got = shapes(tmp_path, {"a": {"url": "tok3nabc:pw@host.com"}, "b": {"type": "sse", "url": "wss://x.example.com/p"}})

    assert got == {"a": "remote http: unknown://", "b": "remote sse: wss://x.example.com"}


def test_local_servers_get_a_per_scan_index_not_a_path_derived_id(tmp_path):
    projects = {"/z/b": {"mcpServers": {"s": {"command": "x"}}}, "/a/a": {"mcpServers": {"s": {"command": "y"}}}}
    (tmp_path / ".claude.json").write_text(json.dumps({"projects": projects}))

    ids = sorted(i.id for i in scan(tmp_path).items)

    assert ids == ["claude-code:mcp_server:local/1/s", "claude-code:mcp_server:local/2/s"]


def test_local_scope_can_be_switched_off(tmp_path, monkeypatch):
    import constellation.claude_code as cc

    (tmp_path / ".claude.json").write_text(json.dumps({"projects": {"/p": {"mcpServers": {"s": {"command": "x"}}}}}))
    monkeypatch.setattr(cc, "LOCAL_SCOPE", False)

    assert scan(tmp_path).items == []


def test_command_descriptions_are_capped_and_redacted_and_bodies_never_reach_the_counter(tmp_path):
    (tmp_path / "commands").mkdir()
    (tmp_path / "commands" / "c.md").write_text("Run PLANTEDSECRET99 now " + "x" * 400 + "\nBODY_PLANTED_TEXT\n")
    (tmp_path / "settings.json").write_text('{"env": {"K": "PLANTEDSECRET99"}}')
    sent = []

    def counter(texts):
        sent.extend(texts)
        return [1] * len(texts)

    result = scan(tmp_path, counter=counter, count_bodies=True, cost_cache=tmp_path / "cache.json")

    command = named(result, "command")["c"]
    assert len(command.description) <= 200
    assert "PLANTEDSECRET99" not in command.description
    assert sent
    assert "BODY_PLANTED_TEXT" not in " ".join(sent)
    assert result.costs[command.id].on_use is None


def test_an_invalid_utf8_command_and_a_malformed_installed_plugins_entry_warn_and_continue(tmp_path):
    (tmp_path / "commands").mkdir()
    (tmp_path / "commands" / "bad.md").write_bytes(b"\xff\xfe PLANTED_BYTES")
    (tmp_path / "commands" / "ok.md").write_text("Fine.\n")
    (tmp_path / "plugins").mkdir()
    (tmp_path / "plugins" / "installed_plugins.json").write_text(json.dumps({"plugins": {"a@m": [5, {"installPath": 3}], "b@m": "x"}}))

    result = scan(tmp_path)

    assert list(named(result, "command")) == ["ok"]
    assert "skipped a command file: unreadable or not valid UTF-8" in result.warnings
    assert "skipped malformed entries in installed_plugins.json" in result.warnings
    assert "bad.md" not in repr(result.warnings) and "PLANTED" not in repr(result.warnings)


def test_a_symlink_inside_a_plugin_pointing_outside_is_refused(tmp_path):
    root = tmp_path / "plugins" / "cache" / "mkt" / "p" / "1.0.0"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text('{"name": "p", "description": "d"}')
    (root / "commands").mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("PLANTED_OUTSIDE first line\n")
    (root / "commands" / "evil.md").symlink_to(outside)

    result = scan(tmp_path)

    assert "evil" not in named(result, "command")
    assert "PLANTED_OUTSIDE" not in json.dumps(asdict(result))
    assert "skipped a file in a plugin: it is a symlink pointing outside the plugin" in result.warnings


def test_a_plugin_named_user_is_not_the_user_scope_for_tool_calls(tmp_path):
    root = tmp_path / "plugins" / "cache" / "mkt" / "user" / "1.0.0"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin").joinpath("plugin.json").write_text(
        '{"name": "user", "description": "d", "mcpServers": {"srv": {"command": "x"}}}'
    )
    (tmp_path / ".claude.json").write_text('{"mcpServers": {"other": {"command": "y"}}}')
    transcript = tmp_path / "projects" / "p" / "s.jsonl"
    transcript.parent.mkdir(parents=True)
    block = {"type": "tool_use", "name": "mcp__srv__go", "id": "1", "input": {}}
    transcript.write_text(json.dumps({"type": "assistant", "timestamp": "2026-11-02T12:00:00Z", "message": {"content": [block]}}) + "\n")

    result = scan(tmp_path)

    assert result.usage["claude-code:mcp_server:user/srv"].count == 0  # mcp__srv__ is not the plugin's name (plugin_user_srv)
    block["name"] = "mcp__plugin_user_srv__go"
    transcript.write_text(json.dumps({"type": "assistant", "timestamp": "2026-11-02T12:00:00Z", "message": {"content": [block]}}) + "\n")
    assert scan(tmp_path).usage["claude-code:mcp_server:user/srv"].count == 1


def test_a_hook_calling_a_user_scope_server_links_to_it(tmp_path):
    (tmp_path / ".claude.json").write_text('{"mcpServers": {"srv": {"command": "x"}}}')
    (tmp_path / "settings.json").write_text(
        json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "mcp_tool", "server": "srv", "tool": "t"}]}]}})
    )

    result = scan(tmp_path)

    assert [(r.target, r.kind) for r in result.relations if r.kind == "triggers"] == [("claude-code:mcp_server:user/srv", "triggers")]


def test_planted_secrets_reach_no_provider_input_and_not_the_report(tmp_path):
    from fakes import FakeEmbedder, FakeLLM

    from constellation.report import render_report

    shutil.copytree(FIXTURE, tmp_path / "cfg")
    (tmp_path / "cfg" / "commands" / "first.md").write_text("Use PLANTED_SETTINGS_ENV here\n")
    llm, verifier, embedder = FakeLLM({}), FakeLLM({}, default='{"verdict": "distinct", "reason": "x"}'), FakeEmbedder({})
    counted = []

    def counter(texts):
        counted.extend(texts)
        return [1] * len(texts)

    result = scan(
        tmp_path / "cfg", llm=llm, embedder=embedder, counter=counter, count_bodies=True, verifier=verifier,
        cost_cache=tmp_path / "c.json", label_cache=tmp_path / "l.json", verdict_cache=tmp_path / "v.json",
    )  # fmt: skip
    offline = scan(tmp_path / "cfg", offline=True)

    sent = "\n".join([*llm.prompts, *verifier.prompts, *embedder.texts, *counted])
    assert sent and "PLANTED" not in sent
    for each in (result, offline):
        assert "PLANTED" not in render_report(json.loads(json.dumps(asdict(each))), top=10, color=False, width=100, show_all=True)
