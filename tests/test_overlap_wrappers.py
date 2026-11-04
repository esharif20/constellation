from fakes import pairs, write_skill

from constellation import scan

LONG = "Check the diff carefully. " * 30


def test_a_short_skill_that_only_calls_another_is_a_wrapper(tmp_path):
    write_skill(tmp_path, "deep-review", "Run /code-review on the changes and report back.")
    write_skill(tmp_path, "code-review", LONG)

    constellation = scan(tmp_path)

    assert pairs(constellation) == [("deep-review", "code-review", "wrapper")]  # a is the wrapper, not the lower id
    assert constellation.overlaps[0].reason == "'deep-review' is 8 words and only hands off to 'code-review'"


def test_other_invocation_forms_count(tmp_path):
    write_skill(tmp_path, "w1", "Use the `code-review` helper.")
    write_skill(tmp_path, "w2", "Hand off to the code-review skill now.")
    write_skill(tmp_path, "w3", "Hand off to the code-review agent now.")
    write_skill(tmp_path, "code-review", LONG)

    assert {a for a, _, _ in pairs(scan(tmp_path))} == {"w1", "w2", "w3"}


def test_a_long_body_that_mentions_another_skill_is_not_a_wrapper(tmp_path):
    write_skill(tmp_path, "big", "Run /code-review now. " + "More words here. " * 40)
    write_skill(tmp_path, "code-review", LONG * 3)

    assert scan(tmp_path).overlaps == []


def test_a_body_of_exactly_the_word_limit_still_counts(tmp_path):
    write_skill(tmp_path, "edge", "Run /code-review " + "now " * 78)  # 80 words
    write_skill(tmp_path, "over", "Run /code-review " + "now " * 79)  # 81 words
    write_skill(tmp_path, "code-review", LONG)

    assert pairs(scan(tmp_path)) == [("edge", "code-review", "wrapper")]


def test_a_short_body_that_names_two_skills_is_not_a_wrapper(tmp_path):
    write_skill(tmp_path, "both", "Run /code-review then /lint please.")
    write_skill(tmp_path, "code-review", LONG)
    write_skill(tmp_path, "lint", LONG + "extra")

    assert scan(tmp_path).overlaps == []


def test_a_bare_word_is_not_a_mention(tmp_path):
    write_skill(tmp_path, "other", "Please do a code-review of this today.")
    write_skill(tmp_path, "code-review", LONG)

    assert scan(tmp_path).overlaps == []


def test_a_name_inside_a_longer_name_is_not_a_mention(tmp_path):
    write_skill(tmp_path, "other", "Run /code-review-extra now.")
    write_skill(tmp_path, "code-review", LONG)
    write_skill(tmp_path, "pre-code-review", LONG + "more")
    write_skill(tmp_path, "third", "Run /pre-code-review now.")

    assert pairs(scan(tmp_path)) == [("third", "pre-code-review", "wrapper")]


def test_the_target_must_have_a_longer_body(tmp_path):
    write_skill(tmp_path, "a-short", "Run /b-short now.")
    write_skill(tmp_path, "b-short", "Run something else entirely, with more words.")
    write_skill(tmp_path, "c-short", "Run /d-short now please.")
    write_skill(tmp_path, "d-short", "Do it.")

    assert pairs(scan(tmp_path)) == [("a-short", "b-short", "wrapper")]


def test_a_skill_never_wraps_itself(tmp_path):
    write_skill(tmp_path, "loop", "Run /loop again.")

    assert scan(tmp_path).overlaps == []


def test_a_target_name_shared_by_two_items_is_ambiguous_and_skipped(tmp_path):
    write_skill(tmp_path, "wrap", "Run /code-review now.")
    write_skill(tmp_path, "code-review", LONG)
    plugin = tmp_path / "plugins" / "cache" / "mkt" / "tool" / "1.0.0"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text('{"name": "tool", "description": "A tool."}')
    write_skill(plugin, "code-review", LONG + "different")

    assert pairs(scan(tmp_path)) == []
