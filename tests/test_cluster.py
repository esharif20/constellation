import sys

import pytest
from fakes import FakeEmbedder, FakeLLM

from constellation import scan
from constellation.embeddings import fastembed_embedder
from constellation.models import Item


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


# Pins found by mutation testing. Each case gives every skill a hand-picked embedding vector, keyed by its (unique) name.


def test_embeddings_of_mixed_dimensions_are_an_error(tmp_path):
    for name in ("dim-a", "dim-b"):
        _skill(tmp_path, name, "Does a thing")
    embedder = FakeEmbedder({"dim-a": [1.0, 0.0], "dim-b": [1.0, 0.0, 0.0]})

    with pytest.raises(ValueError):
        scan(tmp_path, llm=FakeLLM({}), embedder=embedder)


def test_the_local_embedder_loads_lazily_and_says_how_to_install_it(monkeypatch):
    monkeypatch.setitem(sys.modules, "fastembed", None)  # as if the optional extra were not installed

    embed = fastembed_embedder()  # building it must not need the model

    with pytest.raises(RuntimeError, match="uv sync --extra local"):
        embed(["a text"])


MID = {"mid-a": [1.0, 0.3, 0.0], "mid-b": [1.0, 0.0, 0.0], "mid-c": [1.0, -0.3, 0.0]}


def test_the_models_labels_never_enter_the_embedding_text(tmp_path):
    _skill(tmp_path, "mid-a", "Does a thing")
    embedder = FakeEmbedder(MID)

    scan(tmp_path, llm=FakeLLM({"mid-a": "LABEL_MARKER"}), embedder=embedder)

    assert embedder.texts and not any("LABEL_MARKER" in t for t in embedder.texts)


def test_vectors_of_different_sizes_are_an_error_even_when_they_would_be_centred(tmp_path):
    for n in range(10):
        _skill(tmp_path, f"s{n}", "Handles it")
    sizes = iter([3, 2, 3, 3, 3, 3, 3, 3, 3, 3])

    def uneven(texts):
        return [[1.0] * next(sizes) for _ in texts]

    with pytest.raises(ValueError):
        scan(tmp_path, embedder=uneven)


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


# Plugins join the cluster of their contents (docs/design/mcp-and-hubs.md, Slice 3). Invented data, no scan needed.


def test_unit_and_centre_helpers_are_exact():
    from constellation.cluster import _centre, _unit

    assert _unit([3.0, 4.0]) == [0.6, 0.8] and _unit([0.0, 0.0]) == [0.0, 0.0]
    first, second = _centre([[1.0, 0.0], [0.0, 1.0]])
    assert first == pytest.approx([0.7071, -0.7071], abs=1e-3) and second == pytest.approx([-0.7071, 0.7071], abs=1e-3)
    with pytest.raises(ValueError):
        _centre([[1.0, 0.0], [1.0]])


def test_item_vectors_rejects_uneven_dimensions_and_missing_vectors():
    from constellation.cluster import item_vectors

    items = [Item(f"id{n}", "skill", f"s{n}", "d", "claude-code") for n in range(2)]
    with pytest.raises(ValueError, match="^embeddings have different dimensions$"):
        item_vectors(items, lambda texts: [[1.0, 0.0], [1.0]])
    with pytest.raises(ValueError):
        item_vectors(items, lambda texts: [[1.0, 0.0]])
