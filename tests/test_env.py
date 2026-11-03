import os
import sys

from fakes import FakeEmbedder

from constellation.cli import main
from constellation.env import load_env


def test_loads_key_value_lines_and_ignores_comments_blanks_quotes_and_export(tmp_path, monkeypatch):
    for name in ("PLAIN_KEY", "QUOTED_KEY", "EXPORTED_KEY", "A_COMMENT", "EQUALS_KEY", "EDGE_KEY"):
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / ".env"
    lines = ["# a comment", "# A_COMMENT=nope", "", "PLAIN_KEY=abc123", 'QUOTED_KEY="with spaces"', "export EXPORTED_KEY=exp"]
    lines += ["EQUALS_KEY=ab=cd==", "EDGE_KEY=XmarkerX", "not a pair"]
    env.write_text("\n".join(lines) + "\n")

    load_env(env)

    assert (os.environ["PLAIN_KEY"], os.environ["QUOTED_KEY"], os.environ["EXPORTED_KEY"]) == ("abc123", "with spaces", "exp")
    assert (os.environ["EQUALS_KEY"], os.environ["EDGE_KEY"]) == ("ab=cd==", "XmarkerX")
    assert "A_COMMENT" not in os.environ and not any(key.startswith("#") for key in os.environ)


def test_a_variable_already_set_wins_over_the_file(tmp_path, monkeypatch):
    monkeypatch.setenv("ALREADY_SET", "from-the-shell")
    (tmp_path / ".env").write_text("ALREADY_SET=from-the-file\n")

    load_env(tmp_path / ".env")

    assert os.environ["ALREADY_SET"] == "from-the-shell"


def test_a_missing_file_is_fine(tmp_path):
    load_env(tmp_path / "no-such.env")  # must not raise


def test_scan_picks_up_the_key_from_a_dot_env_file_in_the_working_directory(tmp_path, monkeypatch, capsys):
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=not-a-real-key\n")
    config = tmp_path / "claude"
    config.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setitem(sys.modules, "anthropic", None)  # stop before any real client is built: we only need to know the key was found

    code = main(["scan", str(config)], embedder=FakeEmbedder({}))

    err = capsys.readouterr().err
    assert code == 2 and "not set" not in err and "uv sync --extra llm" in err
    assert "not-a-real-key" not in err
