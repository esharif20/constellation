import os
from pathlib import Path

import pytest

from constellation import cli, selfcheck
from constellation.selfcheck import CONFIRM, Check, detect_method, env_checks, env_report, model_hint, uninstall, update_text


@pytest.mark.parametrize(
    "prefix,method",
    [
        ("/h/.local/share/uv/tools/constellation-cli", "uv tool"),
        ("/h/.local/pipx/venvs/constellation-cli", "pipx"),
        ("/opt/homebrew/Cellar/x/1/libexec", "brew"),
        ("/usr/local/Cellar/x/1", "brew"),
        ("/opt/homebrew/lib", "brew"),
        ("/src/constellation/.venv", "dev"),
        ("C:\\Users\\a\\pipx\\venvs\\c", "pipx"),
        ("/usr/lib/python3", "pip"),
        ("/x/.venv/lib", "pip"),
    ],
)
def test_detect_method(prefix, method):
    assert detect_method(prefix) == method


def test_update_text_exact_for_every_method():
    assert update_text("uv tool") == (
        "To upgrade Constellation (uv tool install), run:\n  uv tool upgrade constellation-cli\n"
        "This command only prints it; nothing is downloaded or installed."
    )
    assert "pipx upgrade constellation-cli" in update_text("pipx")
    assert "brew upgrade constellation-cli" in update_text("brew")
    assert "python -m pip install --upgrade constellation-cli" in update_text("pip")
    assert "git pull && uv sync" in update_text("dev")


def _run(method, cache, dry_run, answer):
    lines: list[str] = []
    asked: list[str] = []

    def ask(prompt):
        asked.append(prompt)
        if isinstance(answer, Exception):
            raise answer
        return answer

    return uninstall(method, cache, dry_run, ask, lines.append), "\n".join(lines), asked


def _data(tmp_path):
    cache = tmp_path / "constellation"
    cache.mkdir()
    (cache / "history.json").write_text("{}")
    return cache


def test_uninstall_prompts_then_deletes_only_after_confirmation(tmp_path):
    cache = _data(tmp_path)
    claude = tmp_path / ".claude"
    claude.mkdir()
    code, text, asked = _run("pipx", cache, False, f" {CONFIRM} ")
    assert code == 0 and not cache.exists() and claude.is_dir()
    assert text.startswith("To remove Constellation:\n  pipx uninstall constellation-cli\n")
    assert f"  {cache}/    caches, history, pins, habits\n" in text
    assert "~/.claude is never written or removed" in text
    assert text.endswith(f"Deleted {cache}. Run the command above to remove the program itself.")
    assert asked == [f"\nType '{CONFIRM}' to delete {cache} (anything else keeps it): "]


@pytest.mark.parametrize("answer", ["", "yes", "y", "Delete", EOFError()])
def test_uninstall_keeps_data_on_anything_else(tmp_path, answer):
    cache = _data(tmp_path)
    code, text, _ = _run("uv tool", cache, False, answer)
    assert code == 0 and (cache / "history.json").exists() and text.endswith("Kept. Nothing was deleted.")


def test_uninstall_dry_run_never_asks_or_deletes(tmp_path):
    cache = _data(tmp_path)
    code, text, asked = _run("uv tool", cache, True, CONFIRM)
    assert code == 0 and asked == [] and cache.exists()
    assert text.endswith(f"Dry run: would delete {cache}. Nothing was changed.")


def test_uninstall_without_data(tmp_path):
    code, text, asked = _run("brew", tmp_path / "constellation", False, CONFIRM)
    assert code == 0 and asked == [] and text.endswith("No Constellation data found; nothing to delete.")


def test_uninstall_refuses_odd_targets(tmp_path):
    victim = tmp_path / ".claude"
    victim.mkdir()
    (victim / "settings.json").write_text("{}")
    link = tmp_path / "constellation"
    link.symlink_to(victim)
    other = tmp_path / "other"
    other.mkdir()
    inside = victim / "constellation"
    inside.mkdir()
    file = tmp_path / "f" / "constellation"
    file.parent.mkdir()
    file.write_text("x")
    for target in (link, other, inside, file):
        code, text, asked = _run("pip", target, False, CONFIRM)
        assert (
            code == 1
            and asked == []
            and target.exists()
            and f"Refusing to delete {target}: not a plain 'constellation' data directory." in text
        )
    assert (victim / "settings.json").exists()


def test_uninstall_reports_failed_delete(tmp_path, monkeypatch):
    cache = _data(tmp_path)

    def boom(_):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(selfcheck.shutil, "rmtree", boom)
    code, text, _ = _run("pip", cache, False, CONFIRM)
    assert code == 1 and text.endswith(f"Could not delete {cache}: Permission denied")


def test_uninstall_failure_without_strerror(tmp_path, monkeypatch):
    cache = _data(tmp_path)
    monkeypatch.setattr(selfcheck.shutil, "rmtree", lambda _: (_ for _ in ()).throw(OSError("odd")))
    assert _run("pip", cache, False, CONFIRM)[1].endswith(f"Could not delete {cache}: odd")


def _private(tmp_path):
    cache = tmp_path / "constellation"
    cache.mkdir(mode=0o700)
    cache.chmod(0o700)
    f = cache / "a.json"
    f.write_text("{}")
    f.chmod(0o600)
    return cache


def _checks(tmp_path, cache, version=(3, 13), env=None, prefix="/x/uv/tools/c"):
    return {c.name: c for c in env_checks(prefix, version, env or {}, cache)}


def test_env_checks_all_pass_and_exact(tmp_path):
    got = env_checks("/x/uv/tools/c", (3, 14), {"ANTHROPIC_API_KEY": "sk-secret"}, _private(tmp_path), model=False)
    assert got == [
        Check("Python", "ok", "3.14"),
        Check("Install method", "ok", "uv tool"),
        Check("Cache dir", "ok", f"{tmp_path / 'constellation'} private and writable"),
        Check("ANTHROPIC_API_KEY", "ok", "set"),
        Check(
            "Clustering",
            "ok",
            "words only; for the local model run: uv tool install --force --editable <path to constellation> --with fastembed",
        ),
    ]
    assert "sk-secret" not in repr(got)


def test_clustering_row_names_the_model_or_the_install_command_for_each_method():
    assert env_checks("/x/c", (3, 13), {}, Path("/nope"), model=True)[-1] == Check("Clustering", "ok", "local model")
    pipx = env_checks("/home/pipx/venvs/c", (3, 13), {}, Path("/nope"), model=False)[-1]
    assert pipx.detail == "words only; for the local model run: pipx inject constellation-cli fastembed"
    assert model_hint("/x/.venv") == "uv sync --extra local" and model_hint("/usr/lib/py") == "python -m pip install fastembed"


def test_python_boundary(tmp_path):
    assert _checks(tmp_path, tmp_path / "n", (3, 13))["Python"] == Check("Python", "ok", "3.13")
    assert _checks(tmp_path, tmp_path / "n", (3, 12))["Python"] == Check("Python", "warn", "3.12 (needs 3.13 or newer)")
    assert _checks(tmp_path, tmp_path / "n", (4, 0))["Python"].status == "ok"


def test_key_not_set_or_empty(tmp_path):
    for env in ({}, {"ANTHROPIC_API_KEY": ""}):
        assert _checks(tmp_path, tmp_path / "n", env=env)["ANTHROPIC_API_KEY"] == Check(
            "ANTHROPIC_API_KEY", "ok", "not set (offline mode is fine)"
        )


def test_missing_cache_is_fine(tmp_path):
    assert _checks(tmp_path, tmp_path / "n")["Cache dir"] == Check("Cache dir", "ok", f"{tmp_path / 'n'} not created yet")


def test_cache_modes(tmp_path):
    cache = _private(tmp_path)
    (cache / "a.json").chmod(0o640)
    c = _checks(tmp_path, cache)["Cache dir"]
    assert c.status == "warn" and c.detail == f"1 path(s) readable by others (want 0700 dirs, 0600 files): {cache / 'a.json'}"
    (cache / "a.json").chmod(0o600)
    cache.chmod(0o755)
    assert _checks(tmp_path, cache)["Cache dir"].detail.startswith("1 path(s)")
    cache.chmod(0o707)  # only "other" bits set
    assert _checks(tmp_path, cache)["Cache dir"].status == "warn"
    cache.chmod(0o770)  # only "group" bits set
    assert _checks(tmp_path, cache)["Cache dir"].status == "warn"
    cache.chmod(0o700)


def test_cache_symlinks_ignored_and_unwritable(tmp_path):
    cache = _private(tmp_path)
    (cache / "link").symlink_to(tmp_path / "missing")
    assert _checks(tmp_path, cache)["Cache dir"].status == "ok"
    (cache / "link").unlink()
    cache.chmod(0o500)
    try:
        if os.access(cache, os.W_OK):
            pytest.skip("running as a user that ignores modes")
        assert _checks(tmp_path, cache)["Cache dir"] == Check("Cache dir", "warn", f"{cache} is not writable; caches will be skipped")
    finally:
        cache.chmod(0o700)


def test_env_report_text_hides_key(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-topsecret")
    lines: list[str] = []
    assert env_report(lines.append) == 0
    assert len(lines) == 5
    assert lines[0].startswith("  [ok  ] Python: ") and "  [ok  ] ANTHROPIC_API_KEY: set" in lines
    assert f"  [ok  ] Cache dir: {tmp_path}/.cache/constellation not created yet" in lines
    assert "sk-topsecret" not in "".join(lines)


def test_cli_update_prints_and_runs_nothing(monkeypatch, capsys):
    monkeypatch.setattr(cli.sys, "prefix", "/h/.local/share/uv/tools/constellation-cli")
    assert cli.main(["update"]) == 0
    assert capsys.readouterr().out == update_text("uv tool") + "\n"


def test_cli_uninstall_flow_with_temp_home(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    cache = tmp_path / ".cache" / "constellation"
    cache.mkdir(parents=True)
    (cache / "x.json").write_text("{}")
    assert cli.main(["uninstall", "--dry-run"]) == 0 and cache.exists()
    monkeypatch.setattr("builtins.input", lambda _: "no")
    assert cli.main(["uninstall"]) == 0 and cache.exists()
    monkeypatch.setattr("builtins.input", lambda _: CONFIRM)
    assert cli.main(["uninstall"]) == 0 and not cache.exists()
    assert "Deleted" in capsys.readouterr().out


def test_cli_doctor_env_needs_no_scan(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    assert cli.main(["doctor", "--env"]) == 0
    assert "Install method" in capsys.readouterr().out


def test_uninstall_text_exact():
    assert selfcheck.uninstall_text("dev", Path("/c/constellation")) == (
        "To remove Constellation:\n"
        "  delete this checkout (nothing was installed system-wide)\n"
        "Data it may have written (yours to keep or delete):\n"
        "  /c/constellation/    caches, history, pins, habits\n"
        "  ./constellation.json    and any other --out files you chose\n"
        "  ~/.claude is never written or removed by Constellation."
    )
    for m, cmd in {
        "uv tool": "uv tool uninstall",
        "pipx": "pipx uninstall",
        "brew": "brew uninstall",
        "pip": "python -m pip uninstall",
    }.items():
        assert selfcheck.uninstall_text(m, Path("/c")).splitlines()[1] == f"  {cmd} constellation-cli"
