import pytest

from constellation import overlaps
from constellation.models import Item
from constellation.overlaps import candidates


def _item(name, kind="skill", scope=""):
    return Item(f"claude-code:{kind}:{scope}{name}", kind, name, "d", "claude-code")


def _ids(pairs):
    return [(a.rsplit(":", 1)[-1], b.rsplit(":", 1)[-1]) for a, b in pairs]


def _unit_at(angle_cosine):
    """A 2-d unit vector whose dot with [1, 0] is the given cosine."""
    return [angle_cosine, (1 - angle_cosine**2) ** 0.5]


def test_each_item_proposes_its_three_nearest_neighbours_at_or_above_the_threshold():
    items = [_item(n) for n in ("a", "b", "c", "d", "e", "far")]
    vectors = {"claude-code:skill:a": [1.0, 0.0]}
    for name, cosine in {"b": 0.95, "c": 0.9, "d": 0.8, "e": 0.7, "far": 0.4}.items():
        vectors[f"claude-code:skill:{name}"] = _unit_at(cosine)

    pairs, warnings = candidates(items, vectors, set())

    from_a = [p for p in _ids(pairs) if "a" in p]
    assert from_a == [("a", "b"), ("a", "c"), ("a", "d")]  # e is the fourth nearest, far is under 0.5
    assert warnings == []


def test_a_neighbour_exactly_at_the_threshold_counts():
    items = [_item("a"), _item("b")]
    vectors = {"claude-code:skill:a": [1.0, 0.0], "claude-code:skill:b": [0.5, 0.0]}

    assert _ids(candidates(items, vectors, set())[0]) == [("a", "b")]


def test_a_pair_is_listed_once_with_the_lower_id_first():
    items = [_item("b"), _item("a")]
    vectors = {"claude-code:skill:a": [1.0, 0.0], "claude-code:skill:b": [1.0, 0.0]}

    assert _ids(candidates(items, vectors, set())[0]) == [("a", "b")]


def test_only_skills_and_agents_are_proposed():
    items = [_item("a"), _item("b", "agent"), _item("srv", "mcp_server"), _item("PreToolUse:Bash", "hook"), _item("plug", "plugin")]
    vectors = {i.id: [1.0, 0.0] for i in items}

    assert _ids(candidates(items, vectors, set())[0]) == [("b", "a")]  # agent ids sort before skill ids


def test_pairs_already_decided_are_skipped_even_when_they_share_a_name():
    items = [_item("a"), _item("b"), _item("same"), _item("same", scope="p/")]
    vectors = {i.id: [1.0, 0.0] for i in items}
    decided = {frozenset({"claude-code:skill:a", "claude-code:skill:b"}), frozenset({"claude-code:skill:same", "claude-code:skill:p/same"})}

    pairs = _ids(candidates(items, vectors, decided)[0])

    assert ("a", "b") not in pairs and ("p/same", "same") not in pairs and ("same", "p/same") not in pairs
    assert ("a", "same") in pairs


def test_same_name_pairs_are_added_even_when_their_vectors_are_far_apart():
    items = [_item("stop-slop"), _item("stop-slop", scope="p/"), _item("other")]
    vectors = {"claude-code:skill:stop-slop": [1.0, 0.0], "claude-code:skill:p/stop-slop": [0.0, 1.0], "claude-code:skill:other": [-1.0, 0.0]}

    assert _ids(candidates(items, vectors, set())[0]) == [("p/stop-slop", "stop-slop")]


def test_same_name_pairs_are_still_found_when_there_are_no_vectors():
    items = [_item("stop-slop"), _item("stop-slop", scope="p/"), _item("other")]

    assert _ids(candidates(items, {}, set())[0]) == [("p/stop-slop", "stop-slop")]


def test_past_the_cap_the_most_similar_pairs_win_and_one_warning_counts_the_rest(monkeypatch):
    monkeypatch.setattr(overlaps, "MAX_PAIRS", 2)
    items = [_item(n) for n in ("a", "b", "c", "d")]
    vectors = {
        "claude-code:skill:a": [1.0, 0.0],
        "claude-code:skill:b": _unit_at(0.99),
        "claude-code:skill:c": _unit_at(0.98),
        "claude-code:skill:d": _unit_at(0.97),
    }

    pairs, warnings = candidates(items, vectors, set())

    assert _ids(pairs) == [("c", "d"), ("b", "c")]  # most similar first
    assert warnings == ["checked the 2 most similar pairs; 4 more were not checked"]


def test_ties_are_broken_by_id(monkeypatch):
    monkeypatch.setattr(overlaps, "MAX_PAIRS", 1)
    items = [_item(n) for n in ("a", "b", "c")]
    vectors = {i.id: [1.0, 0.0] for i in items}

    assert _ids(candidates(items, vectors, set())[0]) == [("a", "b")]


@pytest.mark.parametrize("count", [2, 3])  # 1 and 3 pairs
def test_at_most_the_cap_gives_no_warning(monkeypatch, count):
    monkeypatch.setattr(overlaps, "MAX_PAIRS", 3)
    items = [_item(n) for n in "abc"[:count]]
    vectors = {i.id: [1.0, 0.0] for i in items}

    assert candidates(items, vectors, set())[1] == []
