import argparse
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from constellation import cli, cli_help, completion, public_export
from constellation.cli import main

CONFIG = Path(__file__).parent / "fixtures" / "claude_config"
PACK = Path(__file__).parent / "fixtures" / "preview_pack" / "pdf-kit"
DEMO = Path(__file__).parents[1] / "docs" / "design" / "demo.json"


@pytest.fixture
def parser(monkeypatch):
    captured = {}
    real = argparse.ArgumentParser.parse_args

    def grab(self, *a, **k):
        captured["p"] = self
        return real(self, *a, **k)

    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", grab)
    main(["completion", "bash"])
    return captured["p"]


def verbs(parser):
    return completion.table(parser)


def subparsers(parser):
    return next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction)).choices


def test_every_verb_help_has_a_description_and_examples(parser, capsys):
    for name, sub in subparsers(parser).items():
        assert sub.description, name
        assert sub.epilog and sub.epilog.startswith("examples:\n  constellation "), name
        with pytest.raises(SystemExit) as stop:
            main([name, "--help"])
        assert stop.value.code == 0
        assert "examples:" in capsys.readouterr().out


def test_top_level_help_groups_every_verb_and_lists_exit_codes(parser, capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    assert out.index("Look:") < out.index("Act:") < out.index("Map:") < out.index("Manage:")
    assert all(f"  {name} " in out for name in subparsers(parser))
    assert "completion  Print a shell completion script" in out
    assert "Exit codes: 0 ok, 1 runtime error, 2 usage error or missing input, 130 interrupted." in out


def test_every_writer_is_marked_and_takes_dry_run(parser):
    writers = {n for n, s in subparsers(parser).items() if s.get_default("writes")}
    assert writers == cli_help.WRITERS
    for name in writers:
        assert any("--dry-run" in a.option_strings for a in subparsers(parser)[name]._actions), name


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    monkeypatch.setattr(cli, "_local_embedder", lambda: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    shutil.copy(DEMO, work / "constellation.json")
    static = tmp_path / "build"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html><head></head><body></body></html>")
    (static / "assets/app.js").write_text("1")
    monkeypatch.setattr(public_export, "STATIC", static)
    return tmp_path


def tree(root):
    return sorted((str(p.relative_to(root)), p.stat().st_size) for p in root.rglob("*"))


WRITER_RUNS = {
    "scan": lambda: ["scan", str(CONFIG), "--out", "new-scan.json"],
    "clean": lambda: ["clean", "--out", "list.md"],
    "share": lambda: ["share", "--out", "shared"],
    "export": lambda: ["export", "--public", "--out", "snap"],
    "review": lambda: ["review", "--out", "list.md"],
    "report": lambda: ["report", "--cleanup", "list.md"],
    "preview": lambda: ["preview", str(PACK), "--out", "pv.json"],
}


def test_the_run_table_covers_every_writer():
    assert set(WRITER_RUNS) == cli_help.WRITERS


@pytest.mark.parametrize("name", sorted(WRITER_RUNS))
def test_dry_run_leaves_the_disk_unchanged(name, home, capsys):
    before = tree(home)
    assert main(WRITER_RUNS[name]() + ["--dry-run"]) == 0
    assert tree(home) == before
    assert capsys.readouterr().out.strip()


def test_clean_dry_run_prints_the_checklist(home, capsys):
    main(["clean", "--dry-run"])
    out = capsys.readouterr().out
    assert "Wrote" not in out and "- [ ]" in out


def test_export_dry_run_lists_files_with_sizes(home, capsys):
    assert main(["export", "--public", "--out", "snap", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "would write snap/index.html  " in out and " bytes" in out
    assert "files, nothing written." in out


def test_export_dry_run_refuses_an_existing_output(home, capsys):
    (home / "work" / "snap").mkdir()
    assert main(["export", "--public", "--out", "snap", "--dry-run"]) == 2
    assert "already exists" in capsys.readouterr().err


def test_scan_dry_run_lists_the_files_it_would_write(home, capsys):
    main(["scan", str(CONFIG), "--out", "x.json", "--dry-run"])
    line = next(ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("would write: "))
    assert line.startswith("would write: x.json, ") and "history.json" in line and "habits.json" in line and "weekly.json" in line


def test_scan_writes_skips_what_is_switched_off():
    assert cli_help.scan_writes(Path("o"), None, None, None) == ["o"]
    assert cli_help.scan_writes(Path("o"), Path("h"), Path("b"), Path("w")) == ["o", "h", "b", "w"]


def test_export_disk_error_is_a_runtime_error_exit_1(home, monkeypatch, capsys):
    def boom(*a, **k):
        raise OSError("x")

    monkeypatch.setattr(cli, "write_snapshot", boom)
    assert main(["export", "--public", "--out", "snap"]) == 1
    assert "Could not export" in capsys.readouterr().err


def test_missing_input_is_exit_2(home, capsys):
    assert main(["report", "nope.json"]) == 2


@pytest.mark.parametrize("shell", completion.SHELLS)
def test_each_completion_script_names_every_verb_and_option(parser, shell, capsys):
    assert main(["completion", shell]) == 0
    script = capsys.readouterr().out
    for name, (_, words) in verbs(parser).items():
        assert name in script
        for w in words:
            assert (w[2:] if shell == "fish" else w) in script
    assert "constellation completion" not in script  # a script, not the install hint


def test_completion_rejects_an_unknown_shell(capsys):
    with pytest.raises(SystemExit) as stop:
        main(["completion", "powershell"])
    assert stop.value.code == 2


@pytest.mark.parametrize("shell", ["bash", "zsh"])
def test_completion_scripts_parse(shell, tmp_path, capsys):
    if shutil.which(shell) is None:
        pytest.skip(f"{shell} not installed")
    main(["completion", shell])
    script = tmp_path / "c.sh"
    script.write_text(capsys.readouterr().out)
    assert subprocess.run([shell, "-n", str(script)], capture_output=True).returncode == 0


def test_completion_table_reports_options_and_fixed_choices(parser):
    t = verbs(parser)
    assert t["completion"] == ("Print a shell completion script (bash, zsh or fish) to stdout", ["--help", "bash", "zsh", "fish"])
    assert "--dry-run" in t["clean"][1] and "-h" not in t["clean"][1]
    json.dumps(t)
