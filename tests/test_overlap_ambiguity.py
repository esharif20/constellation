import pytest
from fakes import FakeEmbedder, FakeVerifier, verdict, write_skill

import constellation
from constellation import overlaps, scan, scan_graph
from constellation.models import Item
from constellation.overlaps import BAND_LOW, ambiguity, rank


def _item(name, description="d", kind="skill"):
    return Item(f"claude-code:{kind}:{name}", kind, name, description, "claude-code")


def test_same_name_always_scores_one():
    assert ambiguity(_item("x", "red"), _item("x", "blue"), -1.0, "", "") == 1.0


def test_each_term_has_its_weight():
    a, b = _item("a", "alpha beta"), _item("b", "gamma delta")
    assert ambiguity(a, b, 0.0, "", "") == 0.0
    assert ambiguity(a, b, 1.0, "", "") == pytest.approx(0.5)
    assert ambiguity(a, b, 2.0, "", "") == pytest.approx(0.5)  # clamped
    assert ambiguity(a, b, -0.4, "", "") == 0.0
    assert ambiguity(_item("a", "alpha beta"), _item("b", "alpha gamma"), 0.0, "", "") == pytest.approx(0.25 / 3)
    assert ambiguity(a, b, 0.0, "# one\n# two\n# three\n# four", "# One\n# two\n# three\n# four") == pytest.approx(0.1)
    assert ambiguity(a, b, 0.0, "# one", "# one\n# two") == pytest.approx(0.1 / 3)
    assert ambiguity(a, b, 0.0, "run /b now", "") == pytest.approx(0.15)
    assert ambiguity(a, b, 0.0, "", "use `a`") == pytest.approx(0.15)


def test_short_words_do_not_count_as_description_overlap():
    assert ambiguity(_item("a", "to do it"), _item("b", "to do it"), 0.0, "", "") == 0.0
    assert ambiguity(_item("a", "pdf"), _item("b", "pdf"), 0.0, "", "") == 0.25  # three letters count


def _bodies(items, **text):
    return {i.id: text.get(i.name, "") for i in items}


def test_rank_orders_by_score_not_cosine_and_keeps_scores():
    items = [_item("a", "pdf reader"), _item("b", "pdf reader"), _item("c", "unrelated words")]
    vectors = {"claude-code:skill:a": [1.0, 0.0], "claude-code:skill:b": [0.6, 0.8], "claude-code:skill:c": [0.8, 0.6]}
    ranked, warnings = rank(items, vectors, _bodies(items), set())
    assert ranked[0][:2] == ("claude-code:skill:a", "claude-code:skill:b")  # same words, though a-c has the higher cosine
    assert [s for *_, s in ranked] == sorted((s for *_, s in ranked), reverse=True)
    assert warnings == []


def test_rank_skips_decided_pairs():
    items = [_item("a"), _item("b")]
    vectors = {"claude-code:skill:a": [1.0, 0.0], "claude-code:skill:b": [1.0, 0.0]}
    assert rank(items, vectors, _bodies(items), {frozenset(("claude-code:skill:a", "claude-code:skill:b"))}) == ([], [])


def test_rank_caps_at_max_pairs_keeping_the_best(monkeypatch):
    monkeypatch.setattr(overlaps, "MAX_PAIRS", 1)
    items = [_item("a", "pdf reader"), _item("b", "pdf reader"), _item("c", "zzz")]
    vectors = {i.id: [1.0, 0.0] for i in items}
    ranked, warnings = rank(items, vectors, _bodies(items), set())
    assert [(a[-1], b[-1]) for a, b, _ in ranked] == [("a", "b")]
    assert warnings and "2 more" in warnings[0]


def _cos(c):
    return [c, (1 - c * c) ** 0.5]


def _two(tmp_path, cosine, desc_b):
    write_skill(tmp_path, "left", "x", description="alpha topic")
    write_skill(tmp_path, "right", "y", description=desc_b)
    embedder = FakeEmbedder({"left:": [1.0, 0.0]}, default=_cos(cosine))
    verifier = FakeVerifier(default=verdict("overlap", "same"))
    sent = []
    result = scan(tmp_path, verifier=verifier, embedder=embedder, verdict_cache=tmp_path / "v.json", on_verify=lambda n, t: sent.append(n))
    return result, verifier, sent


def test_a_clearly_distinct_pair_never_reaches_the_verifier(tmp_path):
    _, verifier, sent = _two(tmp_path, 0.55, "omega stuff")  # 0.5 * 0.55 = 0.275 < BAND_LOW
    assert verifier.prompts == [] and sent == []


def test_an_ambiguous_pair_is_sent(tmp_path):
    result, verifier, sent = _two(tmp_path, 0.7, "omega stuff")  # 0.35 >= BAND_LOW
    assert len(verifier.prompts) == 1 and sent == [1] and len(result.overlaps) == 1


def test_the_band_edge_is_inclusive(tmp_path, monkeypatch):
    monkeypatch.setattr("constellation.scan_graph.BAND_LOW", 0.275)
    _, verifier, _ = _two(tmp_path, 0.55, "omega stuff")
    assert len(verifier.prompts) == 1


def test_a_skipped_pair_has_a_route_reason(tmp_path, monkeypatch):
    seen = {}
    real = scan_graph.run
    monkeypatch.setattr(constellation, "run", lambda *a, **k: seen.update(real(*a, **k)) or seen)
    _two(tmp_path, 0.55, "omega stuff")
    assert seen["routes"] == [("claude-code:skill:left / claude-code:skill:right", f"below ambiguity band, 0.28 < {BAND_LOW:.2f}")]
    assert seen["ranked"][0][2] == pytest.approx(0.275)


def test_a_cached_verdict_is_still_used_below_the_band(tmp_path):
    _two(tmp_path, 0.7, "omega stuff")  # fills the cache
    _, verifier, _ = _two(tmp_path, 0.55, "omega stuff")  # now below the band, but the answer is free
    assert verifier.prompts == []


def test_rank_scores_use_both_bodies():
    items = [_item("a"), _item("b")]
    vectors = {i.id: [1.0, 0.0] for i in items}
    base = rank(items, vectors, _bodies(items), set())[0][0][2]
    assert rank(items, vectors, _bodies(items, a="run /b"), set())[0][0][2] == pytest.approx(base + 0.15)
    assert rank(items, vectors, _bodies(items, b="run /a"), set())[0][0][2] == pytest.approx(base + 0.15)
