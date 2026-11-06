import json
from pathlib import Path

import pytest
from fakes import own

from constellation import scan

FIXTURE = Path(__file__).parent / "fixtures" / "claude_config"


def test_scan_lists_every_skill_as_an_item():
    constellation = scan(FIXTURE)

    items = by_kind(constellation, "skill")
    assert set(items) == {"alpha", "beta"}
    assert items["alpha"].description == "Does the alpha thing when asked."
    assert items["beta"].description == "Handles beta: with a colon in the text."
    assert {i.kind for i in items.values()} == {"skill"}
    assert {i.source for i in items.values()} == {"claude-code"}


def by_kind(constellation, kind):
    return {i.name: i for i in constellation.items if i.kind == kind}


def test_scan_lists_agents_as_items():
    agents = by_kind(scan(FIXTURE), "agent")

    assert set(agents) == {"reviewer", "helper"}  # helper ships in the demo plugin
    assert agents["reviewer"].description == "Reviews code for quality and best practices"


def test_scan_lists_locally_configured_mcp_servers_as_items():
    servers = by_kind(scan(FIXTURE), "mcp_server")

    assert set(servers) == {"localdb", "pserver", "docs"}  # pserver ships in the demo plugin
    assert servers["localdb"].description == "stdio: npx"  # the command's basename only: args can carry tokens


def test_a_url_server_is_a_remote_mcp_server_not_a_connector():
    constellation = scan(FIXTURE)

    assert by_kind(constellation, "mcp_server")["docs"].description == "remote http: https://mcp.example.com"
    assert by_kind(constellation, "connector") == {}  # connectors live in the account, not on disk


def test_scan_lists_a_hook_per_handler_across_all_five_lifecycle_events():
    hooks = by_kind(scan(FIXTURE), "hook")

    assert {n: h.description for n, h in hooks.items()} == {
        "SessionStart": "echo session started",
        "UserPromptSubmit": "echo prompt",
        "PreToolUse:Bash": "./block-rm.sh",
        "PostToolUse:Edit|Write": "./lint.sh",
        "PostToolUse:Write": "localdb.scan",
        "Stop": "echo done",
        "PostToolUse:Read": "${CLAUDE_PLUGIN_ROOT}/scripts/log.sh",  # ships in the demo plugin
    }


def test_scan_lists_plugins_and_links_them_to_what_they_contain():
    constellation = scan(FIXTURE)

    plugins = by_kind(constellation, "plugin")
    assert set(plugins) == {"demo"}
    assert plugins["demo"].description == "A demo plugin bundling an agent, a hook and an MCP server."
    names = {i.id: (i.kind, i.name) for i in constellation.items}
    contained = {names[r.target] for r in constellation.relations if r.kind == "contains" and r.source == plugins["demo"].id}
    assert contained == {("agent", "helper"), ("mcp_server", "pserver"), ("hook", "PostToolUse:Read")}


def test_hook_that_calls_an_mcp_tool_triggers_that_server():
    constellation = scan(FIXTURE)

    hook = by_kind(constellation, "hook")["PostToolUse:Write"]
    server = by_kind(constellation, "mcp_server")["localdb"]
    assert hook.description == "localdb.scan"
    assert [(r.source, r.target, r.kind) for r in constellation.relations if r.kind == "triggers"] == [(hook.id, server.id, "triggers")]


def test_skill_without_description_is_skipped_with_a_warning():
    constellation = scan(FIXTURE)

    assert "nodesc" not in {i.name for i in constellation.items}
    assert len(own(constellation.warnings)) == 1
    assert "nodesc" in own(constellation.warnings)[0]


def _skill_file(root, name, text):
    (root / "skills" / name).mkdir(parents=True)
    (root / "skills" / name / "SKILL.md").write_text(text)


def test_a_description_with_an_unquoted_colon_is_read_leniently_with_a_warning(tmp_path):
    # Real skill files are not always valid YAML, and Claude Code still loads them.
    _skill_file(tmp_path, "tikz", "---\nname: tikz\ndescription: Use when asked: draw a diagram. Triggers: plot, figure\n---\nbody\n")

    constellation = scan(tmp_path)

    [item] = constellation.items
    assert item.description == "Use when asked: draw a diagram. Triggers: plot, figure"
    assert any("tikz" in w and "leniently" in w for w in own(constellation.warnings))


@pytest.mark.parametrize("text", ["just markdown, no frontmatter\n", "---\n---\nbody\n"], ids=["no-frontmatter", "empty-frontmatter"])
def test_a_skill_file_with_no_usable_frontmatter_is_skipped_with_a_warning_not_a_crash(tmp_path, text):
    _skill_file(tmp_path, "broken", text)

    constellation = scan(tmp_path)

    assert constellation.items == []
    assert any("broken" in w for w in own(constellation.warnings))


def _plugin_version(config, version, skill_text):
    root = config / "plugins" / "cache" / "mkt" / "tool" / version
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text('{"name": "tool", "description": "A tool plugin."}')
    (root / "skills" / "helper").mkdir(parents=True)
    (root / "skills" / "helper" / "SKILL.md").write_text(f"---\nname: helper\ndescription: {skill_text}\n---\n")
    return root


def test_only_the_installed_plugin_version_is_read(tmp_path):
    old, new = _plugin_version(tmp_path, "1.0.0", "Old text."), _plugin_version(tmp_path, "2.0.0", "New text.")
    installed = {"version": 2, "plugins": {"tool@mkt": [{"installPath": str(old)}]}}
    (tmp_path / "plugins" / "installed_plugins.json").write_text(json.dumps(installed))

    constellation = scan(tmp_path)

    assert [i.description for i in constellation.items if i.name == "helper"] == ["Old text."]
    assert len({i.id for i in constellation.items}) == len(constellation.items)
    assert new.exists()


def test_without_installed_plugins_json_the_newest_cached_version_wins_and_ids_stay_unique(tmp_path):
    _plugin_version(tmp_path, "1.0.0", "Old text."), _plugin_version(tmp_path, "2.0.0", "New text.")

    constellation = scan(tmp_path)

    assert [i.description for i in constellation.items if i.name == "helper"] == ["New text."]
    assert len({i.id for i in constellation.items}) == len(constellation.items)


def test_skills_synced_from_claude_ai_are_read_too_with_ids_that_do_not_collide(tmp_path):
    for folder in ("skills/stop-slop", "skills/synced/abc123/stop-slop", "skills/synced/abc123/pdf"):
        (tmp_path / folder).mkdir(parents=True)
        (tmp_path / folder / "SKILL.md").write_text(f"---\nname: {folder.rsplit('/', 1)[1]}\ndescription: From {folder}\n---\nBody.\n")

    constellation = scan(tmp_path)

    assert sorted(i.description for i in constellation.items) == [
        "From skills/stop-slop",
        "From skills/synced/abc123/pdf",
        "From skills/synced/abc123/stop-slop",
    ]
    assert len({i.id for i in constellation.items}) == 3


def test_scan_records_claude_md_size(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("hello")

    assert scan(tmp_path).memory_bytes == 5


def test_scan_without_claude_md_is_none(tmp_path):
    assert scan(tmp_path).memory_bytes is None


def test_claude_md_text_never_saved(tmp_path):
    from dataclasses import asdict

    (tmp_path / "CLAUDE.md").write_text("key sk-ant-api03-PLANTED")

    assert "sk-ant-api03-PLANTED" not in json.dumps(asdict(scan(tmp_path)))
