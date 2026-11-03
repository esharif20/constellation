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
