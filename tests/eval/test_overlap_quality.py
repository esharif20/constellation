"""Scores the Overlap verifier on hand-labelled invented pairs.

The first tests check the scoring code with a fake verifier and run in the fast suite. The last one calls the real model, so it is marked
`eval` and skipped without a key: run it with `uv run pytest -m eval -s tests/eval/test_overlap_quality.py` (about $0.20)."""

import json
import os
import re

import pytest
from overlap_pairs import PAIRS, evaluate, report

from constellation.anthropic_llm import VERIFIER_MODEL, anthropic_llm
from constellation.overlaps import BAND_LOW
from constellation.redact import guarded

EXPECTED = {frozenset({a, b}): expected for a, _, b, _, expected in PAIRS}


def _oracle(wrong: set[frozenset[str]] = frozenset()):  # type: ignore[assignment]
    """A fake verifier that answers every pair with its hand label, except the pairs in `wrong`, which it calls distinct."""

    def verifier(prompt: str) -> str:
        names = frozenset(re.findall(r"^Name: (.*)$", prompt, re.MULTILINE))
        verdict = "distinct" if names in wrong else EXPECTED[names]
        return json.dumps({"verdict": verdict, "reason": "fake"})

    return verifier


def test_there_are_twenty_labelled_pairs_five_per_verdict():
    assert len(PAIRS) == 20
    assert {v: sum(p[4] == v for p in PAIRS) for v in ("duplicate", "wrapper", "overlap", "distinct")} == {
        "duplicate": 5,
        "wrapper": 5,
        "overlap": 5,
        "distinct": 5,
    }


def test_the_scoring_is_perfect_for_a_perfect_verifier_and_drops_when_it_misses_pairs():
    confusion, precision, recall = evaluate(_oracle())
    assert (precision, recall) == (1.0, 1.0) and confusion["overlap", "overlap"] == 5

    missed = {frozenset({"tidy-prose", "plain-writing"}), frozenset({"quick-review", "code-review"})}
    confusion, precision, recall = evaluate(_oracle(missed))
    assert precision == 1.0 and recall == pytest.approx(13 / 15)
    assert confusion["duplicate", "distinct"] == 1 and "flagged precision 1.00, recall 0.87" in report(confusion, precision, recall)


def test_a_verifier_that_flags_distinct_pairs_loses_precision():
    flag_all = lambda prompt: json.dumps({"verdict": "overlap", "reason": "x"})  # noqa: E731

    _, precision, recall = evaluate(flag_all)

    assert recall == 1.0 and precision == pytest.approx(15 / 20)


@pytest.mark.eval
@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY and spends a few cents")
def test_the_real_verifier_flags_overlapping_pairs_accurately():
    confusion, precision, recall = evaluate(guarded(anthropic_llm(model=VERIFIER_MODEL, max_tokens=2048)))

    print("\n" + report(confusion, precision, recall))
    assert precision >= 0.8 and recall >= 0.7  # a regression guard on invented data, not proof of quality on a real setup


def test_the_ambiguity_band_keeps_every_non_distinct_labelled_pair():
    """Recall guard for #18. Real candidates already have a centred cosine of at least 0.5, so the stand-in similarity is the
    description word cosine floored at that."""
    from overlap_pairs import ambiguity_scores

    scores = ambiguity_scores()
    assert min(s for expected, s in scores if expected != "distinct") >= BAND_LOW
    assert any(s < BAND_LOW for expected, s in scores if expected == "distinct")  # the band does skip something
