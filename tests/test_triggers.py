import copy

from constellation.triggers import trigger_audit


def test_never_fired_skill_flagged():
    data = {
        "items": [
            {
                "id": "s1",
                "kind": "skill",
                "name": "quiet",
                "description": "A skill with a clear and useful description here",
                "disabled": False,
            }
        ],
        "usage": {"s1": {"count": 0, "last_used": None}},
        "usage_window": {"files": 4},
    }

    assert trigger_audit(data) == {
        "files": 4,
        "rows": [{"id": "s1", "name": "quiet", "count": 0, "last_used": None, "flags": ["never"]}],
    }


def test_no_window_returns_empty():
    data = _audit_data([0, 1, 1, 1, 30])
    del data["usage_window"]
    assert trigger_audit(data) == {"files": 0, "rows": []}
    for window in (None, {}, {"files": 0}):
        data["usage_window"] = window
        assert trigger_audit(data) == {"files": 0, "rows": []}


def test_greedy_boundary_min():
    data = _audit_data([1, 1, 2, 19, 20])

    rows = trigger_audit(data)["rows"]

    assert [row["count"] for row in rows if "greedy" in row["flags"]] == [20]


def test_greedy_boundary_median():
    data = _audit_data([10, 10, 10, 39, 40])

    rows = trigger_audit(data)["rows"]

    assert [row["count"] for row in rows if "greedy" in row["flags"]] == [40]


def test_vague_only_with_never():
    data = {
        "items": [
            _skill("never-short", "A concise description that has seven words"),
            _skill("used-short", "A concise description that has seven words"),
            _skill("never-long", "This description has exactly eight words in total"),
        ],
        "usage": {
            "never-short": {"count": 0},
            "used-short": {"count": 3},
            "never-long": {"count": 0},
        },
        "usage_window": {"files": 1},
    }

    assert trigger_audit(data)["rows"] == [
        {"id": "never-long", "name": "never-long", "count": 0, "last_used": None, "flags": ["never"]},
        {"id": "never-short", "name": "never-short", "count": 0, "last_used": None, "flags": ["never", "vague"]},
    ]


def test_agents_and_hooks_not_audited():
    data = {
        "items": [
            {"id": "agent", "kind": "agent", "name": "agent", "description": "", "disabled": False},
            {"id": "hook", "kind": "hook", "name": "hook", "description": "", "disabled": False},
        ],
        "usage": {"agent": {"count": 0}, "hook": {"count": 0}},
        "usage_window": {"files": 1},
    }

    assert trigger_audit(data) == {"files": 1, "rows": []}


def test_disabled_skill_ignored():
    data = _audit_data([0])
    data["items"][0]["disabled"] = True

    assert trigger_audit(data) == {"files": 7, "rows": []}


def test_audit_order():
    data = {
        "items": [
            _skill("z", "A description with enough words to be considered specific"),
            _skill("a", "A description with enough words to be considered specific"),
            _skill("greedy", "A description with enough words to be considered specific"),
            _skill("same-name-2", "A description with enough words to be considered specific", name="same"),
            _skill("same-name-1", "A description with enough words to be considered specific", name="same"),
            _skill("baseline-1", "A description with enough words to be considered specific"),
            _skill("baseline-2", "A description with enough words to be considered specific"),
            _skill("baseline-3", "A description with enough words to be considered specific"),
        ],
        "usage": {
            "z": {"count": 0},
            "a": {"count": 0},
            "greedy": {"count": 25},
            "same-name-2": {"count": 0},
            "same-name-1": {"count": 0},
            "baseline-1": {"count": 1},
            "baseline-2": {"count": 1},
            "baseline-3": {"count": 1},
        },
        "usage_window": {"files": 2},
    }

    assert [row["id"] for row in trigger_audit(data)["rows"]] == [
        "greedy",
        "a",
        "same-name-1",
        "same-name-2",
        "z",
    ]


def test_missing_usage_entry_is_ignored_and_last_used_is_preserved():
    data = _audit_data([0])
    data["items"].append(_skill("missing", "A description with enough words to be considered specific"))
    data["usage"]["skill-0"]["last_used"] = "2026-11-01"

    rows = trigger_audit(data)["rows"]

    assert rows == [{"id": "skill-0", "name": "skill-0", "count": 0, "last_used": "2026-11-01", "flags": ["never"]}]


def test_positive_median_excludes_zero_non_skill_and_disabled():
    data = {
        "items": [
            _skill("zero", "A description with enough words to be considered specific"),
            _skill("low", "A description with enough words to be considered specific"),
            _skill("low2", "A description with enough words to be considered specific"),
            _skill("disabled", "A description with enough words to be considered specific", disabled=True),
            {"id": "agent", "kind": "agent", "name": "agent", "description": "", "disabled": False},
            _skill("high", "A description with enough words to be considered specific"),
        ],
        "usage": {
            "zero": {"count": 0},
            "low": {"count": 1},
            "low2": {"count": 1},
            "disabled": {"count": 1000},
            "agent": {"count": 2000},
            "high": {"count": 20},
        },
        "usage_window": {"files": 1},
    }

    assert [row["id"] for row in trigger_audit(data)["rows"] if "greedy" in row["flags"]] == ["high"]


def test_even_positive_median():
    data = _audit_data([2, 4, 8, 24])

    assert [row["count"] for row in trigger_audit(data)["rows"] if "greedy" in row["flags"]] == [24]
    assert trigger_audit(_audit_data([2, 4, 8, 23]))["rows"] == []


def test_zero_counts_do_not_lower_the_positive_median():
    assert trigger_audit(_audit_data([0, 0, 0, 1, 20]))["rows"] == [
        {"id": "skill-0", "name": "skill-0", "count": 0, "last_used": None, "flags": ["never"]},
        {"id": "skill-1", "name": "skill-1", "count": 0, "last_used": None, "flags": ["never"]},
        {"id": "skill-2", "name": "skill-2", "count": 0, "last_used": None, "flags": ["never"]},
    ]


def test_audit_has_no_descriptions():
    data = _audit_data([0])
    data["items"][0]["description"] = "sk-ant-api03-PLANTED"

    result = trigger_audit(data)

    assert "description" not in result["rows"][0]
    assert "sk-ant-api03-PLANTED" not in repr(result)


def test_audit_does_not_mutate_input():
    data = _audit_data([0])
    before = copy.deepcopy(data)

    trigger_audit(data)

    assert data == before


def _skill(item_id: str, description: str, *, name: str | None = None, disabled: bool = False) -> dict[str, object]:
    return {
        "id": item_id,
        "kind": "skill",
        "name": name or item_id,
        "description": description,
        "disabled": disabled,
    }


def _audit_data(counts: list[int]) -> dict[str, object]:
    return {
        "items": [_skill(f"skill-{index}", "A description with enough words to be considered specific") for index in range(len(counts))],
        "usage": {f"skill-{index}": {"count": count} for index, count in enumerate(counts)},
        "usage_window": {"files": 7},
    }
