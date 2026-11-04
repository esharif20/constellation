import json
from copy import deepcopy

from constellation.hook_safety import hook_safety


def test_hook_rows_split_event_and_matcher():
    rows = hook_safety(
        {"items": [{"id": name, "kind": "hook", "name": name} for name in ("PreToolUse:Bash", "Stop", "PreToolUse:mcp__x:y", "Stop:")]}
    )
    assert {row["id"]: (row["event"], row["matcher"]) for row in rows} == {
        "PreToolUse:Bash": ("PreToolUse", "Bash"),
        "Stop": ("Stop", None),
        "PreToolUse:mcp__x:y": ("PreToolUse", "mcp__x:y"),
        "Stop:": ("Stop", ""),
    }


def test_phase_and_block_table():
    expected = {
        "SessionStart": ("session_start", False),
        "UserPromptSubmit": ("before_prompt", True),
        "PreToolUse": ("each_tool_call", True),
        "PostToolUse": ("each_tool_call", False),
        "PermissionRequest": ("each_tool_call", True),
        "Stop": ("other", True),
        "SubagentStop": ("other", True),
        "FutureEvent": ("other", False),
    }
    rows = hook_safety({"items": [{"id": name, "kind": "hook", "name": name} for name in expected]})
    assert {row["id"]: (row["phase"], row["can_block"]) for row in rows} == expected


def test_mcp_tool_hook_detected_by_relation():
    data = {
        "items": [{"id": value, "kind": "hook", "name": "PreToolUse:Edit"} for value in ("calls", "target", "contains", "missing")],
        "relations": [
            {"source": "calls", "target": "target", "kind": "triggers"},
            {"source": "contains", "target": "server", "kind": "contains"},
        ],
    }
    assert {row["id"]: row["runs"] for row in hook_safety(data)} == {
        "calls": "mcp_tool",
        "target": "shell",
        "contains": "shell",
        "missing": "shell",
    }


def test_hook_rank_order():
    examples = [
        ("other", "FutureEvent", 99000),
        ("after", "PostToolUse", 99000),
        ("unknown", "PreToolUse:A", None),
        ("zero", "PreToolUse:Z", 0),
        ("tie-b", "PreToolUse:B", 12),
        ("tie-a", "PreToolUse:B", 12),
        ("name", "PreToolUse:A", 12),
        ("large", "PreToolUse:Z", 9000),
        ("session", "SessionStart", 1),
        ("prompt", "UserPromptSubmit", 10),
        ("stop", "Stop", None),
    ]
    data = {
        "items": [{"id": item_id, "kind": "hook", "name": name} for item_id, name, _ in examples],
        "hook_weights": {item_id: {"bytes": size, "tokens": 2} for item_id, _, size in examples},
    }
    rows = hook_safety(data)
    assert [row["id"] for row in rows] == [
        "prompt",
        "session",
        "large",
        "name",
        "tie-a",
        "tie-b",
        "zero",
        "unknown",
        "after",
        "stop",
        "other",
    ]
    assert [(row["bytes"], row["tokens"]) for row in rows[:3]] == [(10, 2), (1, 2), (9000, 2)]


def test_hook_weight_unknown_stays_none():
    data = {
        "items": [{"id": item_id, "kind": "hook", "name": "SessionStart"} for item_id in ("missing", "null", "bytes", "tokens", "zero")],
        "hook_weights": {
            "null": {"bytes": None, "tokens": None},
            "bytes": {"bytes": 100, "tokens": None},
            "tokens": {"bytes": None, "tokens": 3},
            "zero": {"bytes": 0, "tokens": 0},
        },
    }
    assert {row["id"]: (row["bytes"], row["tokens"]) for row in hook_safety(data)} == {
        "missing": (None, None),
        "null": (None, None),
        "bytes": (100, None),
        "tokens": (None, 3),
        "zero": (0, 0),
    }


def test_hook_safety_never_returns_command():
    data = {
        "items": [
            {
                "id": "safe-id",
                "kind": "hook",
                "name": "Stop",
                "description": 'curl -H "Authorization: sk-ant-api03-PLANTED"',
            }
        ]
    }
    original = deepcopy(data)
    rows = hook_safety(data)
    assert rows == [
        {
            "id": "safe-id",
            "name": "Stop",
            "event": "Stop",
            "matcher": None,
            "runs": "shell",
            "phase": "other",
            "can_block": True,
            "bytes": None,
            "tokens": None,
        }
    ]
    assert "sk-ant-api03-PLANTED" not in json.dumps(rows)
    assert "curl" not in json.dumps(rows)
    assert data == original


def test_disabled_hooks_omitted():
    data = {
        "items": [
            {"id": "off", "kind": "hook", "name": "UserPromptSubmit", "disabled": True},
            {"id": "skill", "kind": "skill", "name": "UserPromptSubmit"},
            {"id": "on", "kind": "hook", "name": "Stop", "disabled": False},
        ]
    }
    assert [row["id"] for row in hook_safety(data)] == ["on"]


def test_empty_scan_has_no_hooks():
    assert hook_safety({}) == []
    assert hook_safety({"items": [], "relations": [], "hook_weights": {}}) == []
