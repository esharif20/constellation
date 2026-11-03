import json
import stat
import sys

import pytest
from fakes import FakeEmbedder, FakeLLM

from constellation.cli import main


def _t(*parts: str) -> str:
    return "".join(parts)  # assembled at runtime so no token-shaped string sits in the repo


SECRET = _t("ghp_", "aB3dE5gH" * 4, "7jK9")


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # so load_env never finds the real project .env
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)  # tests never see a real key
    root = tmp_path / "claude"
    (root / "skills" / "leaky").mkdir(parents=True)
    (root / "skills" / "leaky" / "SKILL.md").write_text(f"---\nname: leaky\ndescription: Deploys using {SECRET} inline\n---\n")
    return root


def test_dry_run_prints_what_would_be_sent_without_secrets(config, tmp_path, capsys):
    out = tmp_path / "out.json"

    code = main(["scan", str(config), "--out", str(out), "--dry-run"])

    printed = capsys.readouterr().out
    assert code == 0
    assert "leaky" in printed
    assert SECRET not in printed
    assert not out.exists()


def test_scan_writes_redacted_private_json(config, tmp_path):
    out = tmp_path / "out.json"
    llm, embedder = FakeLLM({"leaky": "ships code"}), FakeEmbedder({})

    code = main(["scan", str(config), "--out", str(out)], llm=llm, embedder=embedder)

    data = json.loads(out.read_text())
    assert code == 0
    assert [i["name"] for i in data["items"]] == ["leaky"]
    assert list(data["labels"].values()) == ["ships code"]
    assert {"warnings", "clusters", "overlaps"} <= data.keys()
    assert SECRET not in out.read_text()
    assert stat.S_IMODE(out.stat().st_mode) == 0o600


def test_missing_api_key_exits_2_and_writes_nothing(config, tmp_path, capsys):
    out = tmp_path / "out.json"

    assert main(["scan", str(config), "--out", str(out)]) == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
    assert not out.exists()


def test_a_folder_that_does_not_exist_is_an_error_not_an_empty_scan(tmp_path, capsys):
    code = main(["scan", str(tmp_path / "nope"), "--dry-run"])

    assert code == 2
    assert "not a directory" in capsys.readouterr().err


def test_when_every_model_call_fails_the_command_fails_clearly_and_writes_nothing(config, tmp_path, capsys):
    out = tmp_path / "out.json"
    llm = FakeLLM({}, fail_for={"leaky": "network blocked"})

    code = main(["scan", str(config), "--out", str(out)], llm=llm, embedder=FakeEmbedder({}))

    assert code == 1
    assert "network blocked" in capsys.readouterr().err
    assert not out.exists()


def test_a_key_without_the_llm_extra_says_how_to_install_it_instead_of_crashing(config, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")  # the provider is never built, so it is never used
    monkeypatch.setitem(sys.modules, "anthropic", None)  # as if the optional extra were not installed

    code = main(["scan", str(config), "--out", str(tmp_path / "out.json")], embedder=FakeEmbedder({}))

    assert code == 2
    assert "uv sync --extra llm" in capsys.readouterr().err


def test_dry_run_prints_every_prompt_whole_and_in_a_repeatable_order(tmp_path, capsys):
    root = tmp_path / "claude"
    for n in range(300):  # many Items, so interleaved printing from parallel model calls would show up
        (root / "skills" / f"s{n:03d}").mkdir(parents=True)
        (root / "skills" / f"s{n:03d}" / "SKILL.md").write_text(f"---\nname: s{n:03d}\ndescription: Does thing {n}\n---\n")

    assert main(["scan", str(root), "--dry-run"]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines.count("--- PROMPT ---") == 300 == sum("--- PROMPT ---" in line for line in lines)  # none glued onto another line
    names = [line for line in lines if line.startswith("Name: ")]
    assert names == sorted(names)


def test_dry_run_also_prints_the_texts_that_would_be_counted_and_leaves_the_cache_alone(config, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    assert main(["scan", str(config), "--dry-run"]) == 0

    printed = capsys.readouterr().out
    assert "--- COUNT ---\nleaky: Deploys using" in printed and SECRET not in printed
    assert not (tmp_path / "home").exists()


def test_a_real_run_passes_the_counter_to_the_scan_and_writes_the_costs(config, tmp_path):
    out = tmp_path / "out.json"
    cache = tmp_path / "counts.json"
    from fakes import FakeCounter

    code = main(
        ["scan", str(config), "--out", str(out)], llm=FakeLLM({"leaky": "ships code"}), embedder=FakeEmbedder({}), counter=FakeCounter()
    )

    assert code == 0 and json.loads(out.read_text())["costs"] and not cache.exists()
