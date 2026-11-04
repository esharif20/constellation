from constellation.snapshot import snapshot


def test_snapshot_preserves_public_items_with_opaque_ids_and_no_provenance():
    data = {
        "items": [
            {
                "id": "/private/setup/server",
                "kind": "mcp_server",
                "name": "Demo server",
                "description": "Find docs",
                "source": "/private/setup",
            },
            {
                "id": "/private/setup/server/tool",
                "kind": "mcp_tool",
                "name": "Search",
                "description": "Search docs",
                "source": "/private/setup",
            },
        ],
        "warnings": ["Private path"],
        "usage": {"/private/setup/server": {"count": 1, "last_used": "2026-11-04"}},
        "usage_window": {"first": "2026-11-04"},
    }
    assert snapshot(data) == {
        "items": [
            {"id": "item-1", "kind": "mcp_server", "name": "Demo server", "description": "Find docs", "source": ""},
            {"id": "item-2", "kind": "mcp_tool", "name": "Search", "description": "Search docs", "source": ""},
        ],
        "relations": [],
        "labels": {},
        "clusters": [],
        "costs": {},
        "overlaps": [],
    }


def test_snapshot_remaps_all_public_references_and_preserves_unknown_and_zero_costs():
    data = {
        "items": [
            {"id": "z-server", "kind": "mcp_server", "name": "Docs", "description": "Browse", "source": "local"},
            {"id": "a-tool", "kind": "mcp_tool", "name": "Search", "description": "Find", "source": "local"},
        ],
        "relations": [{"source": "z-server", "target": "a-tool", "kind": "contains"}],
        "labels": {"z-server": "Documentation", "a-tool": "Search"},
        "clusters": [{"name": "Research", "item_ids": ["z-server", "a-tool"]}],
        "costs": {"z-server": {"always_on": None, "on_use": 0}, "a-tool": {"always_on": 12, "on_use": 34}},
        "overlaps": [{"a_id": "a-tool", "b_id": "z-server", "verdict": "wrapper", "reason": "Uses the server"}],
    }
    result = snapshot(data)
    assert [i["id"] for i in result.pop("items")] == ["item-2", "item-1"]
    assert result == {
        "relations": [{"source": "item-2", "target": "item-1", "kind": "contains"}],
        "labels": {"item-2": "Documentation", "item-1": "Search"},
        "clusters": [{"name": "Research", "item_ids": ["item-2", "item-1"]}],
        "costs": {"item-2": {"always_on": None, "on_use": 0}, "item-1": {"always_on": 12, "on_use": 34}},
        "overlaps": [{"a_id": "item-1", "b_id": "item-2", "verdict": "wrapper", "reason": "Uses the server"}],
    }


def test_snapshot_redacts_every_public_string_and_drops_unexpected_nested_fields():
    import copy
    import json

    secret = "ghp_" + "A" * 36
    a, b = f"/private/{secret}/a", f"/private/{secret}/b"
    private = {"usage": {"last_used": "2026-11-04"}, "env": {"TOKEN": secret}, "body": secret, "command": secret}
    data = {
        "items": [
            {"id": a, "kind": secret, "name": secret, "description": secret, "source": secret, **private},
            {"id": b, "kind": "mcp_tool", "name": "Tool", "description": "Safe", "source": secret, **private},
        ],
        "relations": [{"source": a, "target": b, "kind": secret, **private}],
        "labels": {a: secret},
        "clusters": [{"name": secret, "item_ids": [a, b], **private}],
        "costs": {a: {"always_on": 0, "on_use": None, **private}},
        "overlaps": [{"a_id": a, "b_id": b, "verdict": secret, "reason": secret, **private}],
        "warnings": [secret],
        "usage": {a: {"count": 1, "last_used": "2026-11-04"}},
        "usage_window": {"first": "2026-11-04"},
        "expansions": {a: {"tools": [private], "settings": private}},
        "hook_weights": {a: {"bytes": 1, "tokens": 1, **private}},
        "unexpected": private,
    }
    original = copy.deepcopy(data)
    result = snapshot(data)
    assert result == {
        "items": [
            {"id": "item-1", "kind": "[REDACTED]", "name": "[REDACTED]", "description": "[REDACTED]", "source": ""},
            {"id": "item-2", "kind": "mcp_tool", "name": "Tool", "description": "Safe", "source": ""},
        ],
        "relations": [{"source": "item-1", "target": "item-2", "kind": "[REDACTED]"}],
        "labels": {"item-1": "[REDACTED]"},
        "clusters": [{"name": "[REDACTED]", "item_ids": ["item-1", "item-2"]}],
        "costs": {"item-1": {"always_on": 0, "on_use": None}},
        "overlaps": [{"a_id": "item-1", "b_id": "item-2", "verdict": "[REDACTED]", "reason": "[REDACTED]"}],
    }
    assert secret not in json.dumps(result)
    assert data == original
    result["items"][0]["name"] = "Changed"
    result["clusters"][0]["item_ids"].clear()
    result["costs"]["item-1"]["always_on"] = 999
    assert data == original


def test_snapshot_drops_orphan_and_invalid_references_and_empty_clusters():
    data = {
        "items": [{"id": "a", "kind": "skill", "name": "One", "description": "", "source": "local"}],
        "relations": [{"source": "a", "target": "a", "kind": "triggers"}],
        "labels": {"a": "Keep", "missing": "Drop", 0: "Drop"},
        "clusters": [{"name": "Mixed", "item_ids": ["missing", "a", None, [], {}]}, {"name": "Empty", "item_ids": ["missing"]}],
        "costs": {"a": {"always_on": 0, "on_use": None}, "missing": {"always_on": 1, "on_use": 2}},
        "overlaps": [{"a_id": "a", "b_id": "a", "verdict": "distinct", "reason": "Keep"}],
    }
    for invalid in ["missing", None, 0, [], {}]:
        for key in ["source", "target"]:
            data["relations"].append({"source": "a", "target": "a", "kind": "contains", key: invalid})
        for key in ["a_id", "b_id"]:
            data["overlaps"].append({"a_id": "a", "b_id": "a", "verdict": "overlap", "reason": "Drop", key: invalid})
    data["relations"].append({"kind": "contains"})
    data["overlaps"].append({"verdict": "overlap", "reason": "Drop"})
    result = snapshot(data)
    assert result["relations"] == [{"source": "item-1", "target": "item-1", "kind": "triggers"}]
    assert result["labels"] == {"item-1": "Keep"}
    assert result["clusters"] == [{"name": "Mixed", "item_ids": ["item-1"]}]
    assert result["costs"] == {"item-1": {"always_on": 0, "on_use": None}}
    assert result["overlaps"] == [{"a_id": "item-1", "b_id": "item-1", "verdict": "distinct", "reason": "Keep"}]


def test_snapshot_numeric_cost_fields_cannot_carry_private_text_or_nested_data():
    data = {
        "items": [{"id": "a", "kind": "skill", "name": "Demo", "description": "", "source": "local"}],
        "costs": {},
    }
    for value in [None, -1, False, True, 1.5, "token=private", {"body": "private"}, ["private"]]:
        data["costs"] = {"a": {"always_on": value, "on_use": value}}
        assert snapshot(data)["costs"] == {"item-1": {"always_on": None, "on_use": None}}
    for value in [0, 1]:
        data["costs"] = {"a": {"always_on": value, "on_use": value}}
        assert snapshot(data)["costs"] == {"item-1": {"always_on": value, "on_use": value}}
    for value in [None, {}]:
        data["costs"] = {"a": value}
        assert snapshot(data)["costs"] == {"item-1": {"always_on": None, "on_use": None}}


def test_snapshot_opaque_ids_are_repeatable_and_independent_of_input_order():
    data = {
        "items": [
            {"id": "z", "kind": "agent", "name": "First", "description": "", "source": "local"},
            {"id": "a", "kind": "plugin", "name": "Second", "description": "", "source": "local"},
        ],
        "relations": [{"source": "z", "target": "a", "kind": "contains"}],
    }
    first = snapshot(data)
    assert snapshot(data) == first
    data["items"].reverse()
    reordered = snapshot(data)
    assert reordered["items"] == list(reversed(first["items"]))
    assert reordered["relations"] == first["relations"]


def test_snapshot_empty_scan_has_only_the_public_schema():
    assert snapshot({"items": []}) == {
        "items": [],
        "relations": [],
        "labels": {},
        "clusters": [],
        "costs": {},
        "overlaps": [],
    }
