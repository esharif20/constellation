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

    assert {frozenset(c.item_ids): c.name for c in constellation.clusters} == {frozenset(f"claude-code:skill:{n}" for n in MID): "mid"}


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


def _two_squeezed_groups(root, a, b):
    """a items about 'alpha' and b about 'beta' whose raw vectors nearly coincide: only subtracting the common part tells them apart."""
    for n in range(a):
        _skill(root, f"alpha-{n}", "Handles alpha")
    for n in range(b):
        _skill(root, f"beta-{n}", "Handles beta")
    return FakeEmbedder({"alpha": [10.0, 1.0, 0.0], "beta": [10.0, 0.0, 1.0]})


def _cluster_sizes(root, embedder):
    return sorted(len(c.item_ids) for c in scan(root, embedder=embedder).clusters)


def test_with_enough_items_the_common_direction_is_removed_so_squeezed_groups_separate(tmp_path):
    assert _cluster_sizes(tmp_path, _two_squeezed_groups(tmp_path, 5, 5)) == [5, 5]


def test_with_too_few_items_to_average_the_vectors_are_used_raw(tmp_path):
    assert _cluster_sizes(tmp_path, _two_squeezed_groups(tmp_path, 5, 4)) == [9]


def test_vectors_of_different_sizes_are_an_error_even_when_they_would_be_centred(tmp_path):
    for n in range(10):
        _skill(tmp_path, f"s{n}", "Handles it")
    sizes = iter([3, 2, 3, 3, 3, 3, 3, 3, 3, 3])

    def uneven(texts):
        return [[1.0] * next(sizes) for _ in texts]

    with pytest.raises(ValueError):
        scan(tmp_path, embedder=uneven)


def test_the_default_threshold_depends_on_whether_the_vectors_were_centred(tmp_path, monkeypatch):
    cluster_module = sys.modules["constellation.cluster"]
    monkeypatch.setattr(cluster_module, "CENTRED_THRESHOLD", -2.0)  # merges everything
    monkeypatch.setattr(cluster_module, "RAW_THRESHOLD", 2.0)  # merges nothing
    assert _cluster_sizes(tmp_path, _two_squeezed_groups(tmp_path, 5, 5)) == [10]
    other = tmp_path / "other"
    assert _cluster_sizes(other, _two_squeezed_groups(other, 5, 4)) == [1] * 9


def test_a_hook_is_embedded_by_its_name_only_because_its_description_is_just_a_command(tmp_path):
    (tmp_path / "settings.json").write_text(
        '{"hooks": {"PostToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "run-the-thing.sh"}]}]}}'
    )
    _skill(tmp_path, "docs", "Writes documentation")
    embedder = FakeEmbedder({})

    scan(tmp_path, embedder=embedder)

    assert "PostToolUse:Bash" in embedder.texts and "docs: Writes documentation" in embedder.texts
    assert not any("run-the-thing" in text for text in embedder.texts)


def test_item_vectors_returns_unit_vectors_by_id_and_whether_they_were_centred():
    from constellation.cluster import item_vectors
    from constellation.models import Item

    items = [Item(f"id{n}", "skill", f"s{n}", "d", "claude-code") for n in range(2)]

    vectors, centred = item_vectors(items, lambda texts: [[3.0, 4.0], [0.0, 2.0]])

    assert vectors == {"id0": [0.6, 0.8], "id1": [0.0, 1.0]}
    assert centred is False


def test_ten_or_more_items_are_centred_on_their_mean():
    from constellation.cluster import item_vectors
    from constellation.models import Item

    items = [Item(f"id{n:02}", "skill", f"s{n}", "d", "claude-code") for n in range(10)]

    vectors, centred = item_vectors(items, lambda texts: [[1.0, 0.0] if n % 2 else [0.0, 1.0] for n in range(10)])

    assert centred is True
    assert vectors["id00"] == pytest.approx([-0.7071, 0.7071], abs=1e-3)


def _together(names, root, labels=None, vectors=None):
    """One cluster of invented skills with identical vectors, so the name is the only thing under test. Offline unless labelled."""
    root = root / str(len(list(root.iterdir())))  # a fresh config dir per call
    root.mkdir()
    for n in names:
        _skill(root, n, "Does a thing")
    embedder = FakeEmbedder(vectors or {n: [1.0, 0.0, 0.0] for n in names})
    [cluster] = scan(root, llm=FakeLLM(labels) if labels else None, embedder=embedder).clusters
    return cluster.name


def test_a_shared_name_token_names_the_cluster_offline(tmp_path):
    assert _together(["ask-pat", "setup-pat-skills", "loop-me"], tmp_path) == "pat"


def test_the_most_common_token_comes_first_and_tokens_are_counted_once_per_member(tmp_path):
    assert _together(["alpha-review", "beta-review", "gamma-review", "delta"], tmp_path) == "review"
    assert _together(["pat-pat-one", "pat-two", "xx-x"], tmp_path) == "pat"  # a repeat inside one name is one vote


def test_two_tokens_join_by_count_then_first_appearance_and_a_third_is_dropped(tmp_path):
    names = ["git_deploy_mon", "git:deploy:mon", "git deploy mon", "git/deploy/zzz"]  # separators: _ : space /
    assert _together(names, tmp_path) == "git deploy"
    assert _together(["aaa-bbb", "ccc-bbb", "aaa-bbb-x", "bbb-q"], tmp_path) == "bbb aaa"


def test_no_shared_token_falls_back_to_the_nearest_member_name(tmp_path):
    vectors = {"alpha-one": [1.0, 0.3, 0.0], "beta-two": [1.0, 0.0, 0.0], "gamma-three": [1.0, -0.3, 0.0]}
    assert _together(list(vectors), tmp_path, vectors=vectors) == "beta-two"


def test_a_label_still_wins_over_a_shared_token(tmp_path):
    assert _together(["ask-pat", "setup-pat", "loop-pat"], tmp_path, {"ask-pat": "Pat helpers"}) == "Pat helpers"


def test_a_token_in_exactly_a_third_of_the_members_qualifies_and_one_fewer_does_not(tmp_path):
    others = ["b1-x1y", "c2-x2y", "d3-x3y", "e4-x4y", "f5-x5y", "g6-x6y"]
    assert _together(["zzz-aaa", "zzz-bbb", "zzz-ccc", *others], tmp_path) == "zzz"  # 3 of 9 = ceil(9/3)
    assert _together(["zzz-aaa", "zzz-bbb", "ccc-ccc", *others], tmp_path) != "zzz"  # 2 of 9
    assert _together(["zzz-aaa", "zzz-bbb", *others[:5]], tmp_path) != "zzz"  # 2 of 7: ceil(7/3) = 3
    assert _together(["zzz-aaa", "zzz-bbb", *others[:4]], tmp_path) == "zzz"  # 2 of 6: the floor of 2 still applies


def test_stop_words_and_short_tokens_never_name_a_cluster_but_ai_and_ui_may(tmp_path):
    assert _together(["the-skill-a", "the-skill-b", "my-setup-x"], tmp_path) in {"the-skill-a", "the-skill-b", "my-setup-x"}
    assert _together(["ab-one", "ab-two"], tmp_path) in {"ab-one", "ab-two"}
    assert _together(["ai-one", "ai-two"], tmp_path) == "ai"
    assert _together(["ui-one", "ui-two"], tmp_path) == "ui"
