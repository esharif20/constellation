import json
import stat

import pytest
from fakes import FakeEmbedder, FakeLLM

from constellation.cli import main


def _t(*parts: str) -> str:
    return "".join(parts)  # assembled at runtime so no token-shaped string sits in the repo


SECRET = _t("ghp_", "aB3dE5gH" * 4, "7jK9")


@pytest.fixture
def config(tmp_path, monkeypatch):
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
    assert {"warnings", "clusters"} <= data.keys()
    assert SECRET not in out.read_text()
    assert stat.S_IMODE(out.stat().st_mode) == 0o600


def test_missing_api_key_exits_2_and_writes_nothing(config, tmp_path, capsys):
    out = tmp_path / "out.json"

    assert main(["scan", str(config), "--out", str(out)]) == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
    assert not out.exists()
