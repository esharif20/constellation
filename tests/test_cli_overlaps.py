import json
from pathlib import Path

import pytest
from fakes import FakeEmbedder, FakeLLM, FakeVerifier, verdict

from constellation import cli, overlaps
from constellation.cli import main

FIXTURE = Path(__file__).parent / "fixtures" / "overlap_config"
VECTORS = {"PDF": [1.0, 0.0, 0.0], "loaf": [0.0, 1.0, 0.0]}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # so load_env never finds the real project .env
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(overlaps, "DEFAULT_CACHE", tmp_path / "default-verdicts.json")  # never the real home
    monkeypatch.setattr(cli, "_local_embedder", lambda: None)


def test_a_scan_without_providers_still_writes_the_overlaps_found_without_a_model(tmp_path):
    out = tmp_path / "out.json"

    assert main(["scan", str(FIXTURE), "--out", str(out)], llm=FakeLLM({}), embedder=FakeEmbedder(VECTORS)) == 0

    found = {(o["a_id"].rsplit(":", 1)[-1], o["b_id"].rsplit(":", 1)[-1], o["verdict"]) for o in json.loads(out.read_text())["overlaps"]}
    assert found == {("stop-slop", "tidy-prose", "duplicate"), ("deep-read", "pdf-reader", "wrapper")}


def test_a_real_run_prints_the_estimate_then_verifies_without_asking(tmp_path, capsys):
    out = tmp_path / "out.json"
    verifier = FakeVerifier(default=verdict("overlap", "both read PDFs"))

    code = main(["scan", str(FIXTURE), "--out", str(out)], llm=FakeLLM({}), embedder=FakeEmbedder(VECTORS), verifier=verifier)

    err = capsys.readouterr().err
    assert code == 0
    assert "verifying 2 pairs with claude-sonnet-5-5, about $0.0" in err and "(cached pairs are free)" in err
    verdicts = [o["verdict"] for o in json.loads(out.read_text())["overlaps"]]
    assert sorted(verdicts) == ["duplicate", "overlap", "overlap", "wrapper"]
    assert len(verifier.prompts) == 2


def test_one_pair_is_not_pluralised(tmp_path, capsys):
    from fakes import write_skill

    root = tmp_path / "claude"
    write_skill(root, "pdf-a", "One.", description="Reads PDF files")
    write_skill(root, "pdf-b", "Two words.", description="Views PDF files")

    main(["scan", str(root), "--out", str(tmp_path / "o.json")], llm=FakeLLM({}), embedder=FakeEmbedder(VECTORS), verifier=FakeVerifier())

    assert "verifying 1 pair with" in capsys.readouterr().err


def test_a_second_run_asks_nothing_and_prints_no_estimate(tmp_path, capsys):
    args = ["scan", str(FIXTURE), "--out", str(tmp_path / "out.json")]
    main(args, llm=FakeLLM({}), embedder=FakeEmbedder(VECTORS), verifier=FakeVerifier())
    capsys.readouterr()
    second = FakeVerifier()

    main(args, llm=FakeLLM({}), embedder=FakeEmbedder(VECTORS), verifier=second)

    assert second.prompts == [] and "verifying" not in capsys.readouterr().err


def test_no_verify_skips_the_strong_model_and_the_estimate(tmp_path, capsys):
    verifier = FakeVerifier()

    code = main(
        ["scan", str(FIXTURE), "--out", str(tmp_path / "out.json"), "--no-verify"],
        llm=FakeLLM({}),
        embedder=FakeEmbedder(VECTORS),
        verifier=verifier,
    )

    assert code == 0 and verifier.prompts == [] and "verifying" not in capsys.readouterr().err


def test_a_real_run_builds_the_sonnet_verifier_from_the_key(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")
    built = []
    monkeypatch.setattr("constellation.anthropic_llm.anthropic_llm", lambda **kw: built.append(kw) or FakeLLM({}))
    monkeypatch.setattr("constellation.anthropic_llm.anthropic_counter", lambda: lambda texts: [1] * len(texts))

    main(["scan", str(FIXTURE), "--out", str(tmp_path / "out.json")], embedder=FakeEmbedder(VECTORS))

    assert built == [{}, {"model": "claude-sonnet-5-5", "max_tokens": 2048}]  # the labeller, then the verifier


def test_the_dry_run_shows_the_exact_verifier_prompts_and_writes_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    out = tmp_path / "out.json"

    code = main(["scan", str(FIXTURE), "--out", str(out), "--dry-run"], embedder=FakeEmbedder(VECTORS))

    printed = capsys.readouterr().out
    assert code == 0 and printed.count("--- VERIFY ---") == 2
    assert "Name: pdf-reader" in printed and "Name: pdf-viewer" in printed
    assert "Check every page carefully" not in printed  # bodies stay on the machine
    assert "item_a is" in printed  # the local signals are what is sent
    assert not out.exists() and not (tmp_path / "home").exists() and not (tmp_path / "default-verdicts.json").exists()


def test_the_dry_run_uses_the_real_local_embedder_when_it_is_installed(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_local_embedder", lambda: FakeEmbedder(VECTORS))

    main(["scan", str(FIXTURE), "--dry-run"])

    printed = capsys.readouterr().out
    assert printed.count("--- VERIFY ---") == 2 and "--- EMBED TEXT ---\npdf-reader: Reads PDF files" in printed


def test_the_dry_run_says_so_when_the_local_embedder_is_missing(capsys):
    main(["scan", str(FIXTURE), "--dry-run"])

    printed = capsys.readouterr().out
    assert "--- VERIFY ---" not in printed
    assert "uv sync --extra local" in printed and "verifier prompts" in printed


def test_the_dry_run_says_why_when_the_embedder_fails(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_local_embedder", lambda: FakeEmbedder({}, fail_with="model download blocked"))

    main(["scan", str(FIXTURE), "--dry-run"])

    assert "model download blocked" in capsys.readouterr().err


def test_no_verify_dry_run_shows_no_verifier_prompts(capsys):
    main(["scan", str(FIXTURE), "--dry-run", "--no-verify"], embedder=FakeEmbedder(VECTORS))

    printed = capsys.readouterr().out
    assert "--- VERIFY ---" not in printed and "uv sync --extra local" not in printed
