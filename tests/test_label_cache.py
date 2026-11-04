import importlib
import json
import stat

import pytest
from fakes import FakeLLM, write_skill

from constellation import scan
from constellation.classify import classify
from constellation.claude_code import read_items


@pytest.fixture
def config(tmp_path):
    write_skill(tmp_path / "claude", "alpha", "Body.", description="Does alpha")
    write_skill(tmp_path / "claude", "beta", "Body.", description="Does beta")
    return tmp_path / "claude"


def run(config, llm, cache, **kwargs):
    return scan(config, llm=llm, label_cache=cache, **kwargs)


def named(llm):
    return sorted(p.split("\n")[0] for p in llm.prompts)


def test_a_rescan_of_an_unchanged_setup_makes_no_labelling_calls_and_gives_the_same_labels(config, tmp_path):
    cache = tmp_path / "labels.json"
    first, second = FakeLLM({"alpha": "first topic", "beta": "second topic"}), FakeLLM({})

    one, two = run(config, first, cache), run(config, second, cache)

    assert len(first.prompts) == 2 and second.prompts == []
    assert one.labels == two.labels and sorted(two.labels.values()) == ["first topic", "second topic"]


def test_only_new_or_changed_items_are_labelled_on_a_rescan(config, tmp_path):
    cache = tmp_path / "labels.json"
    run(config, FakeLLM({}), cache)
    write_skill(config, "gamma", "Body.")
    write_skill(config, "delta", "Body.")
    write_skill(config, "beta", "Body.", description="Does beta differently")
    llm = FakeLLM({})

    run(config, llm, cache)

    assert named(llm) == ["Name: beta", "Name: delta", "Name: gamma"]


def test_changing_the_label_prompt_invalidates_old_entries(config, tmp_path, monkeypatch):
    cache = tmp_path / "labels.json"
    run(config, FakeLLM({}), cache)
    module = importlib.import_module("constellation.classify")
    old = module._prompt
    monkeypatch.setattr(module, "_prompt", lambda item: old(item) + " Be terse.")
    llm = FakeLLM({})

    run(config, llm, cache)

    assert len(llm.prompts) == 2


def test_a_different_model_id_is_not_served_the_old_models_labels(config, tmp_path):
    cache = tmp_path / "labels.json"
    run(config, FakeLLM({}), cache, label_model="model-a")
    same, other = FakeLLM({}), FakeLLM({})

    run(config, same, cache, label_model="model-a")
    run(config, other, cache, label_model="model-b")

    assert same.prompts == [] and len(other.prompts) == 2


def test_the_cache_file_is_private_and_holds_no_secret(tmp_path):
    secret = "ghp_" + "aB3dE5gH" * 4 + "7jK9"
    root, cache = tmp_path / "claude", tmp_path / "cache" / "labels.json"
    write_skill(root, "leaky", "Body.", description=f"Deploys using {secret}")

    run(root, FakeLLM({}), cache)

    assert stat.S_IMODE(cache.stat().st_mode) == 0o600
    assert secret not in cache.read_text() and "leaky" not in cache.read_text()  # keys are hashes of the redacted prompt


def test_failed_and_empty_labels_are_not_cached(config, tmp_path):
    cache = tmp_path / "labels.json"
    run(config, FakeLLM({"beta": " \n"}, fail_for={"alpha": "network blocked"}), cache)
    llm = FakeLLM({})

    run(config, llm, cache)

    assert named(llm) == ["Name: alpha", "Name: beta"]


def test_a_partial_failure_caches_what_succeeded(config, tmp_path):
    cache = tmp_path / "labels.json"
    run(config, FakeLLM({"beta": "fine"}, fail_for={"alpha": "network blocked"}), cache)
    llm = FakeLLM({})

    run(config, llm, cache)

    assert named(llm) == ["Name: alpha"]


@pytest.mark.parametrize("content", ["", "not json", "[1, 2]"])
def test_a_damaged_cache_is_ignored(config, tmp_path, content):
    cache = tmp_path / "labels.json"
    cache.write_text(content)
    llm = FakeLLM({})

    assert len(run(config, llm, cache).labels) == 2 and len(llm.prompts) == 2


def test_cached_labels_are_cleaned_like_fresh_ones(config, tmp_path):
    cache = tmp_path / "labels.json"
    run(config, FakeLLM({}), cache)
    cache.write_text(json.dumps({key: "  " + "x" * 100 + "\nsecond line" for key in json.loads(cache.read_text())}))
    llm = FakeLLM({})

    labels = run(config, llm, cache).labels

    assert llm.prompts == [] and set(labels.values()) == {"x" * 60}


def test_a_cached_blank_label_is_asked_again(config, tmp_path):
    cache = tmp_path / "labels.json"
    run(config, FakeLLM({}), cache)
    cache.write_text(json.dumps({key: " " for key in json.loads(cache.read_text())}))
    llm = FakeLLM({})

    run(config, llm, cache)

    assert len(llm.prompts) == 2


def test_an_unwritable_cache_is_a_warning_and_the_labels_still_come_out(config, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("a file where a directory is needed")

    constellation = run(config, FakeLLM({}), blocker / "labels.json")

    assert len(constellation.labels) == 2
    assert len(constellation.warnings) == 1 and constellation.warnings[0].startswith("could not save the label cache: ")


def test_nothing_is_written_when_nothing_was_labelled(config, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("x")

    constellation = run(config, FakeLLM({}, fail_for={"alpha": "down", "beta": "down"}), blocker / "labels.json")

    assert len(constellation.warnings) == 2 and not any("cache" in w for w in constellation.warnings)


def test_without_a_path_the_default_cache_location_is_used(config):
    module = importlib.import_module("constellation.classify")

    scan(config, llm=FakeLLM({}))

    assert len(json.loads(module.DEFAULT_CACHE.read_text())) == 2


def test_the_default_salt_is_no_salt(config, tmp_path):
    items = read_items(config)[0]
    cache = tmp_path / "labels.json"
    classify(items, FakeLLM({}), cache_path=cache)
    llm = FakeLLM({})

    classify(items, llm, cache_path=cache, salt="")

    assert llm.prompts == []


def test_a_secret_changing_between_scans_does_not_make_the_item_new(tmp_path):
    root, cache = tmp_path / "claude", tmp_path / "labels.json"
    write_skill(root, "leaky", "Body.", description="Uses hunter2hunter2 here")
    (root / ".env").write_text("TOKEN=hunter2hunter2\n")
    run(root, FakeLLM({}), cache)
    write_skill(root, "leaky", "Body.", description="Uses hunter3hunter3 here")
    (root / ".env").write_text("TOKEN=hunter3hunter3\n")
    llm = FakeLLM({})

    run(root, llm, cache)

    assert llm.prompts == []  # the key is the hash of the redacted prompt, in which both secrets are the same placeholder
