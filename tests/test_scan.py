from pathlib import Path

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

    assert set(servers) == {"localdb", "pserver"}  # pserver ships in the demo plugin
    assert servers["localdb"].description == "npx -y @example/db-mcp"


def test_scan_lists_hosted_connectors_as_one_item_each():
    connectors = by_kind(scan(FIXTURE), "connector")

    assert set(connectors) == {"docs"}
    assert connectors["docs"].description == "https://mcp.example.com/docs"


def test_scan_lists_a_hook_per_handler_across_all_five_lifecycle_events():
    hooks = by_kind(scan(FIXTURE), "hook")

    assert {n: h.description for n, h in hooks.items()} == {
        "SessionStart": "echo session started",
        "UserPromptSubmit": "echo prompt",
        "PreToolUse:Bash": "./block-rm.sh",
        "PostToolUse:Edit|Write": "./lint.sh",
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


def test_skill_without_description_is_skipped_with_a_warning():
    constellation = scan(FIXTURE)

    assert "nodesc" not in {i.name for i in constellation.items}
    assert len(constellation.warnings) == 1
    assert "nodesc" in constellation.warnings[0]
