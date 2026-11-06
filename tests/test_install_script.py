import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run_script(tmp_path, tools, *args):
    """Run install.sh with a PATH holding only stub tools, so nothing real is installed or touched."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    for tool in tools:
        stub = bin_dir / tool
        stub.write_text("#!/bin/sh\necho STUB-RAN >&2\nexit 99\n")
        stub.chmod(0o755)
    (bin_dir / "id").symlink_to(shutil.which("id"))
    home = tmp_path / "home"
    home.mkdir()
    result = subprocess.run(
        ["/bin/sh", str(ROOT / "install.sh"), *args],
        env={"PATH": str(bin_dir), "HOME": str(home)},
        capture_output=True,
        text=True,
    )
    return result, home


def test_dry_run_with_uv_prints_the_command_and_runs_nothing(tmp_path):
    result, home = run_script(tmp_path, ["uv"], "--dry-run")

    assert result.returncode == 0
    assert "would run: uv tool install --force constellation-cli" in result.stdout
    assert "STUB-RAN" not in result.stderr
    assert list(home.iterdir()) == []


def test_git_flag_uses_the_github_source(tmp_path):
    result, _ = run_script(tmp_path, ["uv"], "--dry-run", "--git")

    assert "git+https://github.com/esharif20/constellation" in result.stdout


def test_pipx_needs_python313(tmp_path):
    result, _ = run_script(tmp_path / "a", ["pipx"], "--dry-run")
    assert result.returncode == 1
    assert "python3.13" in result.stderr

    result, _ = run_script(tmp_path / "b", ["pipx", "python3.13"], "--dry-run")
    assert result.returncode == 0
    assert "would run: pipx install --force constellation-cli" in result.stdout


def test_no_installer_found_explains_and_fails(tmp_path):
    result, _ = run_script(tmp_path, [], "--dry-run")

    assert result.returncode == 1
    assert "install uv" in result.stderr.lower()


def test_unknown_option_is_rejected(tmp_path):
    result, _ = run_script(tmp_path, ["uv"], "--bogus")

    assert result.returncode == 1
    assert "unknown option" in result.stderr
