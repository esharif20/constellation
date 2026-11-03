from pathlib import Path

from constellation import scan
from constellation.models import Overlap

FIXTURE = Path(__file__).parent / "fixtures" / "claude_config"


def _skill(root, name, body, description="Does a thing"):
    (root / "skills" / name).mkdir(parents=True, exist_ok=True)
    (root / "skills" / name / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n---\n{body}\n")


def _pairs(constellation):
    return [(o.a_id.rsplit(":", 1)[-1], o.b_id.rsplit(":", 1)[-1], o.verdict) for o in constellation.overlaps]


def test_a_setup_with_no_copies_has_no_overlaps():
    assert scan(FIXTURE).overlaps == []


def test_an_overlap_is_a_frozen_pair_with_a_verdict_and_reason():
    overlap = Overlap("a", "b", "duplicate", "identical instructions")

    assert (overlap.a_id, overlap.b_id, overlap.verdict, overlap.reason) == ("a", "b", "duplicate", "identical instructions")


# Layer 1: exact content, no model.
def test_copies_that_differ_only_in_whitespace_are_a_duplicate_without_any_provider(tmp_path):
    _skill(tmp_path, "one", "Step 1.\nStep 2.")
    _skill(tmp_path, "two", "\n\nStep 1.   \nStep 2.\n\n")

    constellation = scan(tmp_path)

    assert _pairs(constellation) == [("one", "two", "duplicate")]
    assert constellation.overlaps[0].reason == "identical instructions"


def test_a_different_description_does_not_stop_a_body_match(tmp_path):
    _skill(tmp_path, "one", "Same text.", description="First")
    _skill(tmp_path, "two", "Same text.", description="Second")

    assert _pairs(scan(tmp_path)) == [("one", "two", "duplicate")]


def test_a_changed_word_is_not_a_duplicate(tmp_path):
    _skill(tmp_path, "one", "Step 1.")
    _skill(tmp_path, "two", "Step 2.")

    assert scan(tmp_path).overlaps == []


def test_empty_bodies_do_not_match_each_other(tmp_path):
    _skill(tmp_path, "one", "")
    _skill(tmp_path, "two", "  ")

    assert scan(tmp_path).overlaps == []


def test_three_copies_give_two_pairs_anchored_on_the_lowest_id(tmp_path):
    for name in ("c", "a", "b"):
        _skill(tmp_path, name, "Same text.")

    assert _pairs(scan(tmp_path)) == [("a", "b", "duplicate"), ("a", "c", "duplicate")]


def test_a_skill_and_an_agent_with_the_same_text_are_a_duplicate(tmp_path):
    _skill(tmp_path, "reviewer", "Review the code.")
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "critic.md").write_text("---\nname: critic\ndescription: Critiques\n---\nReview the code.\n")

    assert _pairs(scan(tmp_path)) == [("critic", "reviewer", "duplicate")]  # agent ids sort before skill ids
