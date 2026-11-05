import copy
import json

import pytest

from constellation.conflicts import conflicts


def test_two_hooks_same_event_and_matcher_conflict():
    data = {
        "items": [
            {"id": "hook:b", "kind": "hook", "name": "PreToolUse:Bash"},
            {"id": "hook:a", "kind": "hook", "name": "PreToolUse:Bash"},
        ]
    }
    assert conflicts(data) == [
        {
            "kind": "hook",
            "key": "PreToolUse:Bash",
            "item_ids": ["hook:a", "hook:b"],
            "reason": "2 hooks run on PreToolUse (Bash). Claude Code runs them in parallel, so their order is not fixed.",
        }
    ]


def test_same_event_different_matcher_no_conflict():
    assert (
        conflicts(
            {
                "items": [
                    {"id": "a", "kind": "hook", "name": "PreToolUse:Bash"},
                    {"id": "b", "kind": "hook", "name": "PreToolUse:Edit"},
                ]
            }
        )
        == []
    )


def test_single_hook_no_conflict():
    assert conflicts({"items": [{"id": "a", "kind": "hook", "name": "SessionStart"}]}) == []


@pytest.mark.parametrize("name, detail", [("SessionStart", "SessionStart (every match)"), ("PreToolUse:mcp__x:y", "PreToolUse (mcp__x:y)")])
def test_hook_reason_preserves_matcher_and_handles_no_matcher(name, detail):
    data = {"items": [{"id": id_, "kind": "hook", "name": name} for id_ in ("c", "a", "b")]}
    assert conflicts(data) == [
        {
            "kind": "hook",
            "key": name,
            "item_ids": ["a", "b", "c"],
            "reason": f"3 hooks run on {detail}. Claude Code runs them in parallel, so their order is not fixed.",
        }
    ]


def test_same_named_servers_conflict():
    data = {
        "items": [
            {"id": "user/git-helper", "kind": "mcp_server", "name": "git-helper"},
            {"id": "local/1/git-helper", "kind": "mcp_server", "name": "git-helper"},
            {"id": "user/other", "kind": "mcp_server", "name": "other"},
        ]
    }
    assert conflicts(data) == [
        {
            "kind": "mcp_name",
            "key": "git-helper",
            "item_ids": ["local/1/git-helper", "user/git-helper"],
            "reason": "2 MCP servers are named git-helper. Only one is used: local scope wins over project, project over user.",
        }
    ]


def test_plugin_server_name_not_a_conflict():
    data = {
        "items": [
            {"id": "plugin:pack", "kind": "plugin", "name": "pack"},
            {"id": "plugin/server", "kind": "mcp_server", "name": "git-helper"},
            {"id": "user/server", "kind": "mcp_server", "name": "git-helper"},
        ],
        "relations": [{"source": "plugin:pack", "target": "plugin/server", "kind": "contains"}],
    }
    assert conflicts(data) == []
    data["relations"][0]["kind"] = "triggers"
    assert len(conflicts(data)) == 1
    data["relations"][0] = {"source": "user/server", "target": "plugin:pack", "kind": "contains"}
    assert len(conflicts(data)) == 1


def test_shared_quoted_phrase_conflict():
    data = {
        "items": [
            {"id": "skill:b", "kind": "skill", "name": "notes", "description": 'Use for "  Draft   The\nRelease Notes  ".'},
            {"id": "skill:a", "kind": "skill", "name": "changelog", "description": "Say “draft the release notes” to start."},
        ]
    }
    assert conflicts(data) == [
        {
            "kind": "trigger",
            "key": "draft the release notes",
            "item_ids": ["skill:a", "skill:b"],
            "reason": '2 skills claim the phrase "draft the release notes", so either may answer it.',
        }
    ]


@pytest.mark.parametrize("description", ['"pdf" "ab"', '"a "', '"   "', "draft the release notes", "'draft the release notes'"])
def test_one_word_or_short_phrase_ignored(description):
    data = {"items": [{"id": id_, "kind": "skill", "name": id_, "description": description} for id_ in ("a", "b")]}
    assert conflicts(data) == []


def test_phrase_in_one_skill_ignored():
    assert conflicts({"items": [{"id": "a", "kind": "skill", "name": "notes", "description": 'Use "write notes".'}]}) == []


def test_duplicate_phrase_in_one_skill_counts_once():
    data = {"items": [{"id": "a", "kind": "skill", "name": "notes", "description": '"write notes" and “WRITE NOTES”'}]}
    assert conflicts(data) == []
    data["items"].append({"id": "b", "kind": "skill", "name": "draft", "description": '"write notes"'})
    assert conflicts(data) == [
        {
            "kind": "trigger",
            "key": "write notes",
            "item_ids": ["a", "b"],
            "reason": '2 skills claim the phrase "write notes", so either may answer it.',
        }
    ]


@pytest.mark.parametrize("kind", ["hook", "mcp_server", "skill"])
def test_disabled_items_ignored(kind):
    data = {
        "items": [
            {"id": "a", "kind": kind, "name": "same", "description": 'Use "write notes".', "disabled": False},
            {"id": "b", "kind": kind, "name": "same", "description": 'Use "write notes".', "disabled": True},
        ]
    }
    assert conflicts(data) == []
    data["items"][0]["disabled"] = True
    assert conflicts(data) == []


@pytest.mark.parametrize("phrase, included", [("a b", True), ("a " + "b" * 77, True), ("a " + "b" * 78, True), ("a " + "b" * 79, False)])
def test_quoted_phrase_length_boundaries(phrase, included):
    data = {"items": [{"id": id_, "kind": "skill", "name": id_, "description": f'"{phrase}"'} for id_ in ("a", "b")]}
    result = conflicts(data)
    if included:
        assert result == [
            {
                "kind": "trigger",
                "key": phrase,
                "item_ids": ["a", "b"],
                "reason": f'2 skills claim the phrase "{phrase}", so either may answer it.',
            }
        ]
    else:
        assert result == []


def test_conflict_order_and_sorted_ids():
    data = {
        "items": [
            {"id": f"{kind}:{name}:{id_}", "kind": kind, "name": name, "description": f'Use "{name} phrase".'}
            for kind in ("skill", "mcp_server", "hook")
            for name in ("zulu", "alpha")
            for id_ in ("z", "a")
        ]
    }
    before = copy.deepcopy(data)
    result = conflicts(data)
    assert [(row["kind"], row["key"], row["item_ids"]) for row in result] == [
        ("hook", "alpha", ["hook:alpha:a", "hook:alpha:z"]),
        ("hook", "zulu", ["hook:zulu:a", "hook:zulu:z"]),
        ("mcp_name", "alpha", ["mcp_server:alpha:a", "mcp_server:alpha:z"]),
        ("mcp_name", "zulu", ["mcp_server:zulu:a", "mcp_server:zulu:z"]),
        ("trigger", "alpha phrase", ["skill:alpha:a", "skill:alpha:z"]),
        ("trigger", "zulu phrase", ["skill:zulu:a", "skill:zulu:z"]),
    ]
    assert data == before
    data["items"].reverse()
    assert conflicts(data) == result


def test_conflicts_omit_all_description_fields_except_shared_phrase():
    secret = "sk-ant-api03-INVENTED-DESCRIPTION-SECRET"
    data = {
        "items": [
            {
                "id": f"{kind}:{id_}",
                "kind": kind,
                "name": "same",
                "description": f'{secret} "write notes" "private phrase {id_}"',
            }
            for kind in ("hook", "mcp_server", "skill", "plugin", "agent", "mcp_tool", "command", "connector")
            for id_ in ("b", "a")
        ]
    }
    result = conflicts(data)
    assert result == [
        {
            "kind": "hook",
            "key": "same",
            "item_ids": ["hook:a", "hook:b"],
            "reason": "2 hooks run on same (every match). Claude Code runs them in parallel, so their order is not fixed.",
        },
        {
            "kind": "mcp_name",
            "key": "same",
            "item_ids": ["mcp_server:a", "mcp_server:b"],
            "reason": "2 MCP servers are named same. Only one is used: local scope wins over project, project over user.",
        },
        {
            "kind": "trigger",
            "key": "write notes",
            "item_ids": ["skill:a", "skill:b"],
            "reason": '2 skills claim the phrase "write notes", so either may answer it.',
        },
    ]
    assert secret not in json.dumps(result)
    assert "private phrase" not in json.dumps(result)


@pytest.mark.parametrize("kind", ["hook", "mcp_server"])
def test_names_are_grouped_exactly(kind):
    data = {
        "items": [{"id": id_, "kind": kind, "name": name} for id_, name in (("a", "PreToolUse"), ("b", "pretooluse"), ("c", "PreToolUse:"))]
    }
    assert conflicts(data) == []


def test_missing_descriptions_and_empty_items_have_no_conflicts():
    assert conflicts({"items": []}) == []
    assert conflicts({"items": [{"id": "a", "kind": "skill", "name": "notes"}, {"id": "b", "kind": "skill", "name": "notes"}]}) == []


def test_three_skills_share_multiple_phrases():
    data = {
        "items": [
            {"id": id_, "kind": "skill", "name": id_, "description": '"write notes" and “draft changes” and “WRITE NOTES”'}
            for id_ in ("c", "b", "a")
        ]
    }
    assert conflicts(data) == [
        {
            "kind": "trigger",
            "key": "draft changes",
            "item_ids": ["a", "b", "c"],
            "reason": '3 skills claim the phrase "draft changes", so either may answer it.',
        },
        {
            "kind": "trigger",
            "key": "write notes",
            "item_ids": ["a", "b", "c"],
            "reason": '3 skills claim the phrase "write notes", so either may answer it.',
        },
    ]


@pytest.mark.parametrize("kind, expected_kind", [("hook", "hook"), ("mcp_server", "mcp_name"), ("skill", "trigger")])
def test_disabled_item_does_not_hide_later_conflicts(kind, expected_kind):
    data = {
        "items": [
            {"id": "disabled", "kind": kind, "name": "same", "description": '"write notes"', "disabled": True},
            {"id": "a", "kind": kind, "name": "same", "description": '"write notes"'},
            {"id": "b", "kind": kind, "name": "same", "description": '"write notes"'},
        ]
    }
    result = conflicts(data)
    assert len(result) == 1
    assert result[0]["kind"] == expected_kind
    assert result[0]["item_ids"] == ["a", "b"]
