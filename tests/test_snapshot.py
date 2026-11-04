import json

import pytest

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
            {"id": "item-1", "kind": "mcp_server", "name": "Demo server", "description": "MCP server", "source": ""},
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
        "labels": {"item-2": "MCP server", "item-1": "Search"},
        "clusters": [{"name": "Research", "item_ids": ["item-2", "item-1"]}],
        "costs": {"item-2": {"always_on": None, "on_use": 0}, "item-1": {"always_on": 12, "on_use": 34}},
        "overlaps": [{"a_id": "item-1", "b_id": "item-2", "verdict": "wrapper", "reason": "Involves an executable setup item."}],
    }


def test_snapshot_redacts_every_public_string_and_drops_unexpected_nested_fields():
    import copy
    import json

    secret = "ghp_" + "A" * 36
    a, b = f"/private/{secret}/a", f"/private/{secret}/b"
    private = {"usage": {"last_used": "2026-11-04"}, "env": {"TOKEN": secret}, "body": secret, "command": secret}
    data = {
        "items": [
            {"id": a, "kind": "skill", "name": secret, "description": secret, "source": secret, **private},
            {"id": b, "kind": "mcp_tool", "name": "Tool", "description": "Safe", "source": secret, **private},
        ],
        "relations": [{"source": a, "target": b, "kind": "contains", **private}],
        "labels": {a: secret},
        "clusters": [{"name": secret, "item_ids": [a, b], **private}],
        "costs": {a: {"always_on": 0, "on_use": None, **private}},
        "overlaps": [{"a_id": a, "b_id": b, "verdict": "overlap", "reason": secret, **private}],
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
            {"id": "item-1", "kind": "skill", "name": "[REDACTED]", "description": "[REDACTED]", "source": ""},
            {"id": "item-2", "kind": "mcp_tool", "name": "Tool", "description": "Safe", "source": ""},
        ],
        "relations": [{"source": "item-1", "target": "item-2", "kind": "contains"}],
        "labels": {"item-1": "[REDACTED]"},
        "clusters": [{"name": "[REDACTED]", "item_ids": ["item-1", "item-2"]}],
        "costs": {"item-1": {"always_on": 0, "on_use": None}},
        "overlaps": [{"a_id": "item-1", "b_id": "item-2", "verdict": "overlap", "reason": "[REDACTED]"}],
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


@pytest.mark.parametrize("field", ["relations", "labels", "clusters", "costs", "overlaps"])
def test_snapshot_treats_null_optional_collections_as_empty(field):
    assert snapshot({"items": [], field: None}) == {
        "items": [],
        "relations": [],
        "labels": {},
        "clusters": [],
        "costs": {},
        "overlaps": [],
    }


def test_snapshot_replaces_executable_descriptions_with_kind_specific_public_text():
    data = {
        "items": [
            {"id": "a", "kind": "hook", "name": "Start", "description": "run private-command", "source": "local"},
            {"id": "b", "kind": "mcp_server", "name": "Docs", "description": "launch private-command", "source": "local"},
            {"id": "c", "kind": "connector", "name": "Search", "description": "connect private-endpoint", "source": "local"},
        ]
    }
    assert [i["description"] for i in snapshot(data)["items"]] == ["Hook", "MCP server", "Connector"]


@pytest.mark.parametrize("kind", ["unexpected", "", None, [], {}])
def test_snapshot_drops_unknown_item_kinds_and_their_references(kind):
    data = {
        "items": [
            {"id": "a", "kind": kind, "name": "Private", "description": "Private", "source": "local"},
            {"id": "b", "kind": "skill", "name": "Demo", "description": "Safe", "source": "local"},
        ],
        "relations": [{"source": "a", "target": "b", "kind": "contains"}],
        "labels": {"a": "Private"},
        "clusters": [{"name": "Private", "item_ids": ["a"]}],
        "costs": {"a": {"always_on": 1, "on_use": 2}},
        "overlaps": [{"a_id": "a", "b_id": "b", "verdict": "overlap", "reason": "Private"}],
    }
    assert snapshot(data) == {
        "items": [{"id": "item-1", "kind": "skill", "name": "Demo", "description": "Safe", "source": ""}],
        "relations": [],
        "labels": {},
        "clusters": [],
        "costs": {},
        "overlaps": [],
    }


def test_snapshot_keeps_commands_and_strips_disabled_plugin_state_and_scoped_ids():
    import json

    data = {
        "items": [
            {
                "id": "claude-code:command:local/2/review",
                "kind": "command",
                "name": "review",
                "description": "Review a change",
                "source": "claude-code",
                "disabled": True,
                "config": {"enabledPlugins": {"private-plugin": False}},
                "credentials": {"token": "planted-token"},
            },
            {
                "id": "claude-code:plugin:private-plugin",
                "kind": "plugin",
                "name": "private-plugin",
                "description": "Private plugin",
                "source": "claude-code",
                "disabled": True,
                "config": {"enabledPlugins": {"private-plugin": False}},
                "credentials": {"token": "planted-token"},
            },
        ],
        "relations": [{"source": "claude-code:plugin:private-plugin", "target": "claude-code:command:local/2/review", "kind": "contains"}],
    }

    result = snapshot(data)

    assert result["items"] == [
        {"id": "item-1", "kind": "command", "name": "review", "description": "Review a change", "source": "", "disabled": True},
        {"id": "item-2", "kind": "plugin", "name": "private-plugin", "description": "Private plugin", "source": "", "disabled": True},
    ]
    assert result["relations"] == [{"source": "item-2", "target": "item-1", "kind": "contains"}]
    public_json = json.dumps(result)
    assert "local/2" not in public_json
    assert '"disabled": true' in public_json
    assert "enabledPlugins" not in public_json
    assert "credentials" not in public_json
    assert "planted-token" not in public_json


def test_snapshot_omits_false_or_malformed_disabled_values():
    data = {
        "items": [
            {"id": "a", "kind": "skill", "name": "Active", "description": "", "source": "local", "disabled": False},
            {"id": "b", "kind": "agent", "name": "Malformed", "description": "", "source": "local", "disabled": "private"},
        ]
    }
    assert snapshot(data)["items"] == [
        {"id": "item-1", "kind": "skill", "name": "Active", "description": "", "source": ""},
        {"id": "item-2", "kind": "agent", "name": "Malformed", "description": "", "source": ""},
    ]


@pytest.mark.parametrize(
    "private",
    [
        "/Users/demo-person/private/setup",
        "/home/demo-person/private/setup",
        "~/private/setup",
        r"C:\Users\demo-person\private\setup",
        "demo.person@example.test",
        "dev-db.internal.example",
        "https://demo-user:planted-password@dev-db.internal.example/private",
        "https://intranet/private",
        "http://127.0.0.1:8080/private",
        "localhost",
    ],
)
def test_snapshot_scrubs_public_identifiers_in_every_retained_free_text_field(private):
    import json

    data = {
        "items": [{"id": "a", "kind": "skill", "name": private, "description": private, "source": private}],
        "relations": [{"source": "a", "target": "a", "kind": "contains"}],
        "labels": {"a": private},
        "clusters": [{"name": private, "item_ids": ["a"]}],
        "overlaps": [{"a_id": "a", "b_id": "a", "verdict": "overlap", "reason": private}],
    }
    result = snapshot(data)
    assert result == {
        "items": [{"id": "item-1", "kind": "skill", "name": "[REDACTED]", "description": "[REDACTED]", "source": ""}],
        "relations": [{"source": "item-1", "target": "item-1", "kind": "contains"}],
        "labels": {"item-1": "[REDACTED]"},
        "clusters": [{"name": "[REDACTED]", "item_ids": ["item-1"]}],
        "costs": {},
        "overlaps": [{"a_id": "item-1", "b_id": "item-1", "verdict": "overlap", "reason": "[REDACTED]"}],
    }
    assert private not in json.dumps(result)


def test_snapshot_removes_all_planted_identifiers_inside_public_prose():
    import json

    private = [
        "/Users/demo-person/private/setup",
        "demo.person@example.test",
        "dev-db.internal.example",
        "demo-user",
        "planted-password",
    ]
    text = (
        "Uses /Users/demo-person/private/setup by demo.person@example.test on dev-db.internal.example "
        "via HTTPS://demo-user:planted-password@dev-db.internal.example/private"
    )
    data = {
        "items": [{"id": "a", "kind": "skill", "name": text, "description": text, "source": "local"}],
        "relations": [{"source": "a", "target": "a", "kind": "triggers"}],
        "labels": {"a": text},
        "clusters": [{"name": text, "item_ids": ["a"]}],
        "overlaps": [{"a_id": "a", "b_id": "a", "verdict": "duplicate", "reason": text}],
    }
    result = snapshot(data)
    expected = "Uses [REDACTED] by [REDACTED] on [REDACTED] via [REDACTED]"
    assert result["items"][0]["name"] == expected
    assert result["items"][0]["description"] == expected
    assert result["labels"]["item-1"] == expected
    assert result["clusters"][0]["name"] == expected
    assert result["overlaps"][0]["reason"] == expected
    for value in private:
        assert value not in json.dumps(result)


ATTACKS = [
    (r"D:\work\demo-person\notes", "demo-person"),
    (r"C:\\Users\\demo-person\\x", "demo-person"),
    ("C:/work/demo-person/x", "demo-person"),
    (r"\\fileserver\share\demo-person", "fileserver"),
    ("/root/demo-person/.ssh", "demo-person"),
    ("~demo-person/notes", "demo-person"),
    ("'/Users/demo person/My Docs/x.md'", "demo"),
    ('"C:\\Users\\demo person\\x y"', "demo"),
    ("`/home/demo person/a b`", "demo"),
    ("2001:db8:85a3:0:0:8a2e:370:7334", "8a2e"),
    ("fe80::1ff:fe23:4567:890a", "4567"),
    ("::1", "::1"),
    ("dbhost:5432", "dbhost"),
    ("%2FUsers%2Fdemo-person%2Fx", "demo-person"),
    ("%252FUsers%252Fdemo-person", "demo-person"),
    ("%25252525252FUsers%25252525252Fdemo-person", "demo-person"),
    ("/Us\u200bers/demo-person", "demo-person"),
    ("/Us\u00aders/demo-person", "demo-person"),
    ("/Volumes/Backup-demo/x", "demo"),
    ("demo%40example.test", "example"),
    ("demo-person\uff20example.test", "example"),
    ("db\u3002corp\u3002", "db"),
    ("m\u00fcnchen-db.internal", "nchen"),
    ("host\uff0elocal", "host"),
    ("/Users/\u200bdemo-person/x", "demo-person"),
    ("ssh demo-person@10.0.0.5", "demo-person"),
    ("ssh://demo-person@build-box/repo", "build-box"),
    ("file:///Users/demo-person/x", "demo-person"),
    ("file://fileserver/share", "fileserver"),
    ("[notes](https://wiki.example.test/demo-person)", "demo-person"),
    ("demo+tag@example.test", "demo"),
    ("192.168.1.20:8080", "192.168"),
    ("build-01.corp", "build-01"),
    ("nas.lan:445", "nas"),
    ("api.internal.example", "api"),
    ("Aq9Zx3Kp7Lm2Nv8Bc4Td6Fh1Jr5Sw0Yq", "Aq9Zx3Kp7Lm2"),
    ("see /Users/demo-person/a.md and /home/demo-person/b.md", "demo-person"),
]


@pytest.mark.parametrize(("attack", "needle"), ATTACKS)
def test_snapshot_scrubs_attack_strings_in_every_free_text_field(attack, needle):
    import json

    data = {
        "items": [{"id": "a", "kind": "skill", "name": attack, "description": f"x {attack} y", "source": attack}],
        "relations": [{"source": "a", "target": "a", "kind": "contains"}],
        "labels": {"a": attack},
        "clusters": [{"name": attack, "item_ids": ["a"]}],
        "overlaps": [{"a_id": "a", "b_id": "a", "verdict": "overlap", "reason": attack}],
    }
    result = snapshot(data)
    blob = json.dumps(result, ensure_ascii=False)
    assert needle not in blob
    assert "REDACTED" in result["items"][0]["name"]
    assert "REDACTED" in result["items"][0]["description"]
    assert "REDACTED" in result["labels"]["item-1"]
    assert "REDACTED" in result["clusters"][0]["name"]
    assert "REDACTED" in result["overlaps"][0]["reason"]


def test_snapshot_removes_a_quoted_path_with_spaces_as_one_span():
    data = {"items": [{"id": "a", "kind": "skill", "name": "Reads '/Users/demo person/My Docs/x.md' now", "description": "", "source": ""}]}
    assert snapshot(data)["items"][0]["name"] == "Reads [REDACTED] now"


@pytest.mark.parametrize(
    "text",
    [
        "Next.js", "e.g., SKILL.md", "v1.2.3", "Node.js app", "README.md", "Uses Vue.js, Three.js and D3.js", "1.5x faster",
        "12:30:45 UTC", "std::vector", "and/or", "docs/guide.md", "Use the /plan command",
        "10:30", "version 2.0", "foo.bar", "TypeScript 5.4",
    ],
)  # fmt: skip
def test_snapshot_keeps_ordinary_words_that_only_look_like_hostnames(text):
    data = {"items": [{"id": "a", "kind": "skill", "name": text, "description": text, "source": ""}]}
    assert snapshot(data)["items"][0]["name"] == text
    assert snapshot(data)["items"][0]["description"] == text


def test_snapshot_drops_relations_and_overlaps_with_values_outside_the_allowed_sets():
    items = [{"id": i, "kind": "skill", "name": i, "description": "", "source": ""} for i in ("a", "b")]
    relations = [{"source": "a", "target": "b", "kind": k} for k in ("contains", "triggers", "secret-kind", "", None, ["x"])]
    overlaps = [
        {"a_id": "a", "b_id": "b", "verdict": v, "reason": "r"}
        for v in ("duplicate", "wrapper", "overlap", "distinct", "other", "", None, ["x"])
    ]
    result = snapshot({"items": items, "relations": relations, "overlaps": overlaps})
    assert [r["kind"] for r in result["relations"]] == ["contains", "triggers"]
    assert [o["verdict"] for o in result["overlaps"]] == ["duplicate", "wrapper", "overlap", "distinct"]


def test_snapshot_replaces_model_text_derived_from_executable_items():
    host = "secret-db-host"
    data = {
        "items": [
            {"id": "h", "kind": "hook", "name": "h", "description": f"ssh {host} run.sh"},
            {"id": "m", "kind": "mcp_server", "name": "m", "description": f"node {host}"},
            {"id": "s", "kind": "skill", "name": "s", "description": "Demo"},
            {"id": "t", "kind": "skill", "name": "t", "description": "Other"},
        ],
        "labels": {"h": f"Runs ssh to {host}", "m": f"Server at {host}", "s": "Does demo"},
        "clusters": [
            {"name": f"{host} tools", "item_ids": ["h", "m"]},
            {"name": "Demos", "item_ids": ["s", "t"]},
        ],
        "overlaps": [
            {"a_id": "h", "b_id": "s", "verdict": "overlap", "reason": f"Both reach {host}"},
            {"a_id": "s", "b_id": "t", "verdict": "overlap", "reason": "Both demo"},
        ],
    }
    out = snapshot(data)
    assert host not in json.dumps(out)
    assert out["labels"] == {"item-1": "Hook", "item-2": "MCP server", "item-3": "Does demo"}
    assert [c["name"] for c in out["clusters"]] == ["Executable setup", "Demos"]
    assert [o["reason"] for o in out["overlaps"]] == ["Involves an executable setup item.", "Both demo"]
