import sys

import pytest
from fakes import FakeEmbedder, FakeLLM

from constellation import scan
from constellation.embeddings import fastembed_embedder


def _skill(root, name, description):
    (root / "skills" / name).mkdir(parents=True)
    (root / "skills" / name / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n---\n")


def test_items_close_in_embedding_space_form_one_cluster_named_from_a_member_label(tmp_path):
    _skill(tmp_path, "docs-a", "Handles one thing")
    _skill(tmp_path, "docs-b", "Handles another thing")
    _skill(tmp_path, "tests-a", "Handles a third thing")
    llm = FakeLLM({"docs-a": "writing docs", "docs-b": "documentation writing", "tests-a": "test tooling"})
    embedder = FakeEmbedder({"docs": [1.0, 0.1, 0.0], "test": [0.0, 0.0, 1.0]})

    constellation = scan(tmp_path, llm=llm, embedder=embedder)

    by_members = {frozenset(c.item_ids): c.name for c in constellation.clusters}
    docs = frozenset({"claude-code:skill:docs-a", "claude-code:skill:docs-b"})
    assert set(by_members) == {docs, frozenset({"claude-code:skill:tests-a"})}
    assert by_members[docs] in {"writing docs", "documentation writing"}
    assert by_members[frozenset({"claude-code:skill:tests-a"})] == "test tooling"


def test_no_clusters_without_an_embedder(tmp_path):
    _skill(tmp_path, "docs-a", "Handles one thing")

    assert scan(tmp_path, llm=FakeLLM({})).clusters == []


# Pins found by mutation testing. Each case gives every skill a hand-picked embedding vector, keyed by its (unique) name.
def _groups(vectors, labels=None, **kwargs):
    root = kwargs.pop("root")
    for name in vectors:
        _skill(root, name, "Does a thing")
    constellation = scan(root, llm=FakeLLM(labels or {}), embedder=FakeEmbedder(vectors), **kwargs)
    prefix = "claude-code:skill:"
    return {frozenset(i.removeprefix(prefix) for i in c.item_ids): c.name for c in constellation.clusters}


def test_a_third_similar_item_still_joins_the_cluster_of_two(tmp_path):
    vectors = {"same-a": [1.0, 0.1, 0.0], "same-b": [0.95, 0.3, 0.0], "same-c": [1.0, 0.2, 0.0]}

    assert set(_groups(vectors, root=tmp_path)) == {frozenset(vectors)}


def test_an_item_joins_the_closest_cluster_not_the_newest_one(tmp_path):
    vectors = {"alpha-doc": [1.0, 0.0, 0.0], "beta-far": [0.0, 1.0, 0.0], "gamma-near": [0.9, 0.1, 0.0]}

    assert set(_groups(vectors, root=tmp_path)) == {frozenset({"alpha-doc", "gamma-near"}), frozenset({"beta-far"})}


def test_closeness_is_direction_not_size(tmp_path):
    vectors = {"tiny-a": [0.001, 0.0, 0.0], "tiny-b": [0.002, 0.0, 0.0]}

    assert set(_groups(vectors, root=tmp_path)) == {frozenset(vectors)}


def test_a_zero_embedding_gets_its_own_cluster_instead_of_crashing(tmp_path):
    vectors = {"zero-a": [0.0, 0.0, 0.0], "real-b": [1.0, 0.0, 0.0]}

    assert set(_groups(vectors, root=tmp_path)) == {frozenset({"zero-a"}), frozenset({"real-b"})}


def test_a_cluster_is_named_after_the_member_nearest_its_centre_not_the_last_one(tmp_path):
    vectors = {"mid-a": [1.0, 0.3, 0.0], "mid-b": [1.0, 0.0, 0.0], "mid-c": [1.0, -0.3, 0.0]}
    labels = {"mid-a": "A label", "mid-b": "B label", "mid-c": "C label"}

    assert _groups(vectors, labels, root=tmp_path) == {frozenset(vectors): "B label"}


def test_similarity_exactly_at_the_threshold_joins(tmp_path):
    vectors = {"tie-a": [1.0, 0.0, 0.0], "tie-b": [3.0, 4.0, 0.0]}  # cosine is exactly 0.6

    assert set(_groups(vectors, root=tmp_path, cluster_threshold=0.6)) == {frozenset(vectors)}


def test_embeddings_of_mixed_dimensions_are_an_error(tmp_path):
    for name in ("dim-a", "dim-b"):
        _skill(tmp_path, name, "Does a thing")
    embedder = FakeEmbedder({"dim-a": [1.0, 0.0], "dim-b": [1.0, 0.0, 0.0]})

    with pytest.raises(ValueError):
        scan(tmp_path, llm=FakeLLM({}), embedder=embedder)


def test_a_failing_embedder_keeps_the_labels_and_adds_a_warning(tmp_path):
    _skill(tmp_path, "docs-a", "Handles one thing")
    embedder = FakeEmbedder({}, fail_with="download blocked")

    constellation = scan(tmp_path, llm=FakeLLM({"docs-a": "writing docs"}), embedder=embedder)

    assert constellation.clusters == []
    assert constellation.labels == {"claude-code:skill:docs-a": "writing docs"}
    [warning] = constellation.warnings
    assert "ConnectionError" in warning and "download blocked" in warning


def test_the_local_embedder_loads_lazily_and_says_how_to_install_it(monkeypatch):
    monkeypatch.setitem(sys.modules, "fastembed", None)  # as if the optional extra were not installed

    embed = fastembed_embedder()  # building it must not need the model

    with pytest.raises(RuntimeError, match="uv sync --extra local"):
        embed(["a text"])


MID = {"mid-a": [1.0, 0.3, 0.0], "mid-b": [1.0, 0.0, 0.0], "mid-c": [1.0, -0.3, 0.0]}


def test_clusters_need_no_model_and_are_named_after_the_member_nearest_the_centre(tmp_path):
    for name in MID:
        _skill(tmp_path, name, "Does a thing")

    constellation = scan(tmp_path, embedder=FakeEmbedder(MID))

    assert {frozenset(c.item_ids): c.name for c in constellation.clusters} == {frozenset(f"claude-code:skill:{n}" for n in MID): "mid-b"}


def test_the_models_labels_never_enter_the_embedding_text(tmp_path):
    _skill(tmp_path, "mid-a", "Does a thing")
    embedder = FakeEmbedder(MID)

    scan(tmp_path, llm=FakeLLM({"mid-a": "LABEL_MARKER"}), embedder=embedder)

    assert embedder.texts and not any("LABEL_MARKER" in t for t in embedder.texts)


def test_a_cluster_is_named_by_the_nearest_member_that_has_a_label(tmp_path):
    for name in MID:
        _skill(tmp_path, name, "Does a thing")
    llm = FakeLLM({"mid-a": "A label", "mid-c": "C label"}, fail_for={"mid-b": "no answer"})  # the nearest member, mid-b, has no label

    constellation = scan(tmp_path, llm=llm, embedder=FakeEmbedder(MID))

    assert [c.name for c in constellation.clusters] == ["A label"]  # mid-a and mid-c are equally near; ties go to the lower id
