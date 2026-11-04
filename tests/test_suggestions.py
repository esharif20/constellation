import copy
import json
from pathlib import Path

import pytest

from constellation.suggestions import Suggestion, suggest

FIXTURE = Path(__file__).parent / "fixtures" / "scan.json"
SECRET = "".join(["ghp_", "aB3dE5gH" * 4, "7jK9"])


@pytest.fixture
def data():
    return json.loads(FIXTURE.read_text())


def test_one_suggestion_per_duplicate_and_wrapper_none_for_overlap_or_distinct(data):
    got = suggest(data)
    assert [(s.kind, s.item_ids) for s in got] == [
        ("remove_duplicate", ("skill:deploy", "skill:ship")),
        ("use_underlying", ("agent:reviewer", "skill:review")),
    ]


def test_duplicate_reason_names_both_items_and_keeps_the_verdict_reason(data):
    s = suggest(data)[0]
    assert s.reason == (
        "Remove one of these two: deploy (skill) and ship (skill). "
        "The two have identical instructions under different names, so keeping both only costs tokens."
    )


def test_wrapper_reason_and_tokens(data):
    s = suggest(data)[1]
    assert (
        s.reason == "reviewer (agent) only calls review (skill); consider using review (skill) directly. "
        "The reviewer agent only forwards to the review skill."
    )
    assert s.tokens_saved == 60  # the wrapper's own always-on cost


def test_duplicate_saves_the_cheaper_of_the_two(data):
    assert suggest(data)[0].tokens_saved == 415


def test_unknown_cost_is_none_never_zero(data):
    data["costs"]["skill:ship"]["always_on"] = None
    data["costs"]["agent:reviewer"] = None
    first, second = suggest(data)
    assert first.tokens_saved is None
    assert second.tokens_saved is None
    del data["costs"]
    assert [s.tokens_saved for s in suggest(data)] == [None, None]


def test_order_is_known_savings_descending_then_unknown_then_id(data):
    data["costs"]["skill:ship"]["always_on"] = None  # duplicate becomes unknown
    assert [s.kind for s in suggest(data)] == ["use_underlying", "remove_duplicate"]
    data["overlaps"].append({"a_id": "skill:a", "b_id": "skill:b", "verdict": "duplicate", "reason": "same"})
    data["items"] += [{"id": i, "kind": "skill", "name": i, "description": "", "source": ""} for i in ("skill:a", "skill:b")]
    data["overlaps"].append({"a_id": "skill:0", "b_id": "skill:z", "verdict": "duplicate", "reason": "same"})
    ids = [s.item_ids for s in suggest(data)]
    assert ids[0] == ("agent:reviewer", "skill:review")
    assert ids[1:] == [("skill:0", "skill:z"), ("skill:a", "skill:b"), ("skill:deploy", "skill:ship")]  # unknowns, by id


def test_ids_are_stable_across_reordered_input_and_unique(data):
    reordered = copy.deepcopy(data)
    reordered["overlaps"].reverse()
    reordered["overlaps"][0]["a_id"], reordered["overlaps"][0]["b_id"] = "skill:ship", "skill:deploy"  # pair order flipped
    reordered["items"].reverse()
    a, b = suggest(data), suggest(reordered)
    assert [s.id for s in a] == [s.id for s in b]
    assert len({s.id for s in a}) == 2
    assert all(len(s.id) == 12 for s in a)


def test_wrapper_id_depends_on_direction_and_kind(data):
    s = suggest(data)[1]
    flipped = copy.deepcopy(data)
    o = next(o for o in flipped["overlaps"] if o["verdict"] == "wrapper")
    o["a_id"], o["b_id"] = o["b_id"], o["a_id"]
    assert suggest(flipped)[1].id != s.id
    same_pair_as_duplicate = copy.deepcopy(data)
    o = next(o for o in same_pair_as_duplicate["overlaps"] if o["verdict"] == "wrapper")
    o["verdict"] = "duplicate"
    o["a_id"], o["b_id"] = "agent:reviewer", "skill:review"
    assert {x.id for x in suggest(same_pair_as_duplicate)} != {x.id for x in suggest(data)}


def test_known_id_value_is_pinned(data):
    # sha256("remove_duplicate\0skill:deploy\0skill:ship")[:12]; saved decisions depend on this staying put
    import hashlib

    assert suggest(data)[0].id == hashlib.sha256(b"remove_duplicate\0skill:deploy\0skill:ship").hexdigest()[:12]


def test_reasons_are_redacted(data):
    data["overlaps"][1]["reason"] = f"Same token {SECRET} in both."
    assert SECRET not in suggest(data)[0].reason


def test_no_overlaps_no_suggestions(data):
    data["overlaps"] = None
    assert suggest(data) == []
    del data["overlaps"]
    assert suggest(data) == []


def test_unknown_item_id_falls_back_to_the_id(data):
    data["overlaps"] = [{"a_id": "x:1", "b_id": "x:2", "verdict": "duplicate", "reason": "same"}]
    assert suggest(data)[0].reason == "Remove one of these two: x:1 and x:2. same"


def test_unknown_item_ids_in_a_wrapper_fall_back_to_the_ids_on_both_sides(data):
    data["overlaps"] = [{"a_id": "x:1", "b_id": "x:2", "verdict": "wrapper", "reason": "forwards"}]
    assert suggest(data)[0].reason == "x:1 only calls x:2; consider using x:2 directly. forwards"


def test_a_known_zero_saving_sorts_after_a_one_token_saving(data):
    data["items"] = []
    data["costs"] = {"a": {"always_on": 0}, "b": {"always_on": 0}, "c": {"always_on": 1}, "d": {"always_on": 1}}
    data["overlaps"] = [
        {"a_id": "a", "b_id": "b", "verdict": "duplicate", "reason": "r"},
        {"a_id": "c", "b_id": "d", "verdict": "duplicate", "reason": "r"},
    ]
    assert [s.tokens_saved for s in suggest(data)] == [1, 0]


def test_suggestion_is_frozen():
    s = Suggestion("i", "remove_duplicate", ("a", "b"), "r", None)
    with pytest.raises(AttributeError):
        s.id = "j"  # type: ignore[misc]
