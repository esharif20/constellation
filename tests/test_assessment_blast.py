"""The blast-radius guard must still find references when Items share a name (they are renamed for the engine)."""

from test_assessment import TODAY, ledger_file, scan

from constellation import assessment


def data_with(items, **extra):
    base = scan()
    base["items"] = [base["items"][0], base["items"][1], *items]
    base["items"][1]["name"] = "foo"  # s:b is the unused skill (could_go without a reference)
    return {**base, **extra}


def test_a_shared_name_item_named_in_a_hook_is_not_removable(tmp_path):
    ledger_file(tmp_path / "habits.json")
    items = [
        {"id": "p:foo", "kind": "plugin", "name": "foo", "description": "A plugin", "source": ""},
        {"id": "h:foo", "kind": "hook", "name": "Stop:*", "description": "run the foo helper", "source": ""},
    ]
    data = data_with(items)
    found = assessment.compute(data, tmp_path / "habits.json", tmp_path / "none.json", TODAY)
    skill = found.assessments["s:b"]
    assert skill.tier == "review" and skill.reasons[0].code == "referenced"
    assert "Stop:*" in skill.reasons[0].text


def test_an_item_a_hook_triggers_by_relation_is_referenced_even_when_no_description_names_it(tmp_path):
    ledger_file(tmp_path / "habits.json")
    items = [
        {"id": "h:x", "kind": "hook", "name": "Stop:x", "description": "srv.tool", "source": ""},
    ]
    data = data_with(items, relations=[{"source": "h:x", "target": "s:b", "kind": "triggers"}])
    found = assessment.compute(data, tmp_path / "habits.json", tmp_path / "none.json", TODAY)
    assert found.assessments["s:b"].tier == "review" and found.assessments["s:b"].reasons[0].text.startswith("Stop:x calls it")
