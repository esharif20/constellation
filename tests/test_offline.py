import json
import stat

import pytest
from fakes import FakeCounter, FakeEmbedder, FakeLLM, FakeVerifier, write_skill

from constellation import cli, scan
from constellation.cli import main
from constellation.models import Cost

VECTORS = {"PDF": [1.0, 0.0, 0.0], "loaf": [0.0, 1.0, 0.0]}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # so load_env never finds the real project .env
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(cli, "_local_embedder", lambda: None)


@pytest.fixture
def config(tmp_path):
    root = tmp_path / "claude"
    write_skill(root, "pdf-reader", "Same body.", description="Reads PDF files")
    write_skill(root, "pdf-copy", "Same body.", description="Reads PDF files too")
    write_skill(root, "bread", "Bake it.", description="Makes a loaf")
    return root


def providers():
    return FakeLLM({}), FakeCounter(), FakeVerifier()


def untouched(llm, counter, verifier):
    return llm.prompts == [] and counter.texts == [] and verifier.prompts == []


def test_an_offline_scan_calls_no_provider_but_still_clusters_and_finds_free_overlaps(config):
    llm, counter, verifier = providers()
    embedder = FakeEmbedder(VECTORS)

    result = scan(config, llm=llm, counter=counter, verifier=verifier, embedder=embedder, offline=True)

    assert untouched(llm, counter, verifier)
    assert result.labels == {}
    assert sorted(c.name for c in result.clusters) == ["bread", "pdf"]  # named from the token its members share
    assert [o.verdict for o in result.overlaps] == ["duplicate"]
    assert any(w.startswith("Offline") for w in result.warnings)


def test_an_offline_scan_without_an_embedder_has_no_clusters_and_no_error(config):
    result = scan(config, offline=True)

    assert result.clusters == [] and len(result.items) == 3 and [o.verdict for o in result.overlaps] == ["duplicate"]


def test_offline_costs_come_only_from_the_cache(config, tmp_path):
    cache = tmp_path / "counts.json"
    scan(config, counter=FakeCounter(), cost_cache=cache)
    write_skill(config, "newcomer", "Fresh body.", description="Brand new")
    counter = FakeCounter()

    result = scan(config, counter=counter, cost_cache=cache, offline=True)

    assert counter.texts == []
    known = {i.name: result.costs[i.id] for i in result.items}
    assert known["bread"] == Cost(4, None) and known["newcomer"] == Cost(None, None)  # "bread: Makes a loaf" is 4 words


def test_an_offline_scan_does_not_write_the_cost_cache(config, tmp_path):
    cache = tmp_path / "counts.json"

    scan(config, cost_cache=cache, offline=True)

    assert not cache.exists()


def test_the_offline_flag_runs_the_whole_command_without_provider_calls(config, tmp_path, capsys):
    out = tmp_path / "out.json"
    llm, counter, verifier = providers()

    code = main(
        ["scan", str(config), "--out", str(out), "--offline"], llm=llm, counter=counter, verifier=verifier, embedder=FakeEmbedder(VECTORS)
    )

    data = json.loads(out.read_text())
    assert code == 0 and untouched(llm, counter, verifier)
    assert data["labels"] == {} and len(data["items"]) == 3 and data["clusters"]
    assert any(w.startswith("Offline") for w in data["warnings"])
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    assert "running offline" not in capsys.readouterr().err  # the user asked for it, so no explanation


def test_no_api_key_runs_offline_instead_of_exiting_and_says_so(config, tmp_path, capsys):
    out = tmp_path / "out.json"

    code = main(["scan", str(config), "--out", str(out)], embedder=FakeEmbedder(VECTORS))

    err = capsys.readouterr().err
    assert code == 0 and json.loads(out.read_text())["labels"] == {}
    assert err.count("ANTHROPIC_API_KEY is not set: running offline") == 1


def test_offline_without_the_local_embedder_says_clustering_is_skipped(config, tmp_path, capsys):
    out = tmp_path / "out.json"

    code = main(["scan", str(config), "--out", str(out), "--offline"])

    assert code == 0 and json.loads(out.read_text())["clusters"] == []
    assert "uv sync --extra local" in capsys.readouterr().err


def test_offline_with_count_bodies_is_an_error_and_writes_nothing(config, tmp_path, capsys):
    out = tmp_path / "out.json"

    assert main(["scan", str(config), "--out", str(out), "--offline", "--count-bodies"]) == 2
    assert "--count-bodies" in capsys.readouterr().err and not out.exists()


def test_a_dry_run_still_shows_what_a_real_run_would_send_even_with_no_key(config, capsys):
    assert main(["scan", str(config), "--dry-run"]) == 0

    printed = capsys.readouterr().out
    assert "--- PROMPT ---" in printed and "running offline" not in printed


def test_with_a_key_a_second_real_run_labels_nothing_and_a_new_model_id_relabels(config, tmp_path, monkeypatch):
    from constellation import anthropic_llm as provider

    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")
    llm, other = FakeLLM({}), FakeLLM({})
    monkeypatch.setattr(provider, "anthropic_llm", lambda **kwargs: llm if "model" not in kwargs else FakeVerifier())
    monkeypatch.setattr(provider, "anthropic_counter", lambda: FakeCounter())
    out = tmp_path / "out.json"

    assert main(["scan", str(config), "--out", str(out)], embedder=FakeEmbedder(VECTORS)) == 0
    first = len(llm.prompts)
    assert main(["scan", str(config), "--out", str(out)], embedder=FakeEmbedder(VECTORS)) == 0
    assert (first, len(llm.prompts)) == (3, 3)

    monkeypatch.setattr(provider, "MODEL", "another-model")
    monkeypatch.setattr(provider, "anthropic_llm", lambda **kwargs: other if "model" not in kwargs else FakeVerifier())
    assert main(["scan", str(config), "--out", str(out)], embedder=FakeEmbedder(VECTORS)) == 0
    assert len(other.prompts) == 3


def test_an_injected_model_stands_in_for_the_key(config, tmp_path):
    out = tmp_path / "out.json"

    assert main(["scan", str(config), "--out", str(out)], llm=FakeLLM({"bread": "baking"}), embedder=FakeEmbedder(VECTORS)) == 0
    assert "baking" in json.loads(out.read_text())["labels"].values()
