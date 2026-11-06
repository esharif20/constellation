import json
from dataclasses import asdict

from fakes import FakeEmbedder, FakeLLM

from constellation import scan
from constellation.receipt import receipt

NOTE = "Connected through claude.ai; seen only in transcripts, so its tools and cost are unknown"


def calls(tmp_path, *calls, inputs=None):
    """A transcript with one tool_use per (tool name, id); `inputs` is the tool input every call carries."""
    records = [
        {
            "type": "assistant",
            "timestamp": "2026-11-02T12:00:00Z",
            "message": {"content": [{"type": "tool_use", "name": name, "id": id_, "input": inputs or {}}]},
        }
        for name, id_ in calls
    ]
    path = tmp_path / "projects" / "invented" / "s.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records))


def test_a_claude_ai_call_makes_one_connector_item_counted_like_any_usage(tmp_path):
    calls(
        tmp_path, ("mcp__claude_ai_Gmail__search", "1"), ("mcp__claude_ai_Gmail__send", "2"), ("mcp__claude_ai_Google_Calendar__list", "3")
    )

    result = scan(tmp_path)
    found = {i.id: i for i in result.items}

    gmail = found["claude-code:connector:claude.ai/Gmail"]
    assert (gmail.kind, gmail.name, gmail.description, gmail.origin, gmail.scope) == ("connector", "Gmail", NOTE, "claude.ai", "global")
    assert found["claude-code:connector:claude.ai/Google_Calendar"].name == "Google Calendar"
    assert result.usage[gmail.id].count == 2 and result.usage[gmail.id].last_used == "2026-11-02"
    assert len(found) == 2 and result.warnings == []
    assert scan(tmp_path, usage=False).items == []  # no transcripts read, so no connector is known


def test_connectors_reach_the_labels_and_the_clusters_before_clustering(tmp_path):
    calls(tmp_path, ("mcp__claude_ai_Gmail__search", "1"), ("mcp__claude_ai_Drive__find", "2"), ("mcp__claude_ai_Docs__read", "3"))

    result = scan(tmp_path, llm=FakeLLM({"Gmail": "mail"}), embedder=FakeEmbedder({}))

    assert set(result.labels) == {i.id for i in result.items} and len(result.items) == 3
    assert sorted(i for c in result.clusters for i in c.item_ids) == sorted(result.labels)


def test_an_unmatched_non_connector_prefix_gives_one_count_only_warning(tmp_path):
    calls(tmp_path, ("mcp__PLANTEDfoo__x", "1"), ("mcp__PLANTEDfoo__y", "2"), ("mcp__PLANTEDbar__x", "3"), ("mcp__plugin_gone_srv__x", "4"))

    result = scan(tmp_path)

    assert result.items == []
    assert result.warnings == ["usage: 3 MCP servers were called in transcripts but not in your config"]
    calls_one = tmp_path / "projects" / "invented" / "s.jsonl"
    calls_one.write_text(calls_one.read_text().splitlines()[0] + "\n")
    assert scan(tmp_path).warnings == ["usage: 1 MCP server was called in transcripts but not in your config"]


def test_a_config_server_and_a_connector_with_the_same_name_stay_apart(tmp_path):
    (tmp_path / ".mcp.json").write_text('{"mcpServers": {"claude_ai_Gmail": {"command": "x"}}}')
    calls(tmp_path, ("mcp__claude_ai_Gmail__search", "1"), ("mcp__claude_ai_Drive__find", "2"))

    result = scan(tmp_path)

    assert result.usage["claude-code:mcp_server:claude_ai_Gmail"].count == 1
    assert [i.id for i in result.items if i.kind == "connector"] == ["claude-code:connector:claude.ai/Drive"]


def test_only_the_server_segment_is_kept_never_inputs_and_names_are_redacted(tmp_path):
    calls(
        tmp_path,
        ("mcp__claude_ai_Gmail__search", "1"),
        ("mcp__claude_ai_ghp_abcdefghijklmnopqrstuvwxyz0123456789__x", "2"),
        ("mcp__claude_ai_bad name PLANTED__x", "3"),
        inputs={"query": "PLANTED_INPUT_SECRET"},
    )

    result = scan(tmp_path)
    everything = json.dumps(asdict(result)) + repr(result.warnings)

    assert "PLANTED" not in everything and "abcdefghijklmnop" not in everything
    assert "search" not in everything.replace("seen only in transcripts", "")  # the tool segment is dropped
    assert result.warnings == [
        "usage: 1 MCP server was called in transcripts but not in your config"
    ]  # a name with spaces is not a connector


def test_the_receipt_lists_a_connector_as_unmeasured(tmp_path):
    calls(tmp_path, ("mcp__claude_ai_Gmail__search", "1"))

    rows = receipt(json.loads(json.dumps(asdict(scan(tmp_path)))))

    assert [(g["kind"], g["count"], g["unknown"]) for g in rows["groups"]] == [("connector", 1, 1)]
