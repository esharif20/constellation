from pathlib import Path

from constellation import scan

FIXTURE = Path(__file__).parent / "fixtures" / "claude_config"


def test_scan_lists_every_skill_as_an_item():
    constellation = scan(FIXTURE)

    items = {i.name: i for i in constellation.items}
    assert set(items) == {"alpha", "beta"}
    assert items["alpha"].description == "Does the alpha thing when asked."
    assert items["beta"].description == "Handles beta: with a colon in the text."
    assert {i.kind for i in items.values()} == {"skill"}
    assert {i.source for i in items.values()} == {"claude-code"}


def test_skill_without_description_is_skipped_with_a_warning():
    constellation = scan(FIXTURE)

    assert "nodesc" not in {i.name for i in constellation.items}
    assert len(constellation.warnings) == 1
    assert "nodesc" in constellation.warnings[0]
