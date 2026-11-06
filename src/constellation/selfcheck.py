"""Self-management: install-method detection, `update` advice, `uninstall` and `doctor --env`. It never runs an installer."""

import os
import shutil
import stat
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

DIST = "constellation-cli"
KEY_VARS = ("ANTHROPIC_API_KEY",)
CONFIRM = "delete"  # the word a user must type before any data is removed
_UPGRADE = {
    "uv tool": f"uv tool upgrade {DIST}",
    "pipx": f"pipx upgrade {DIST}",
    "brew": f"brew upgrade {DIST}",
    "pip": f"python -m pip install --upgrade {DIST}",
    "dev": "git pull && uv sync",
}
_REMOVE = {
    "uv tool": f"uv tool uninstall {DIST}",
    "pipx": f"pipx uninstall {DIST}",
    "brew": f"brew uninstall {DIST}",
    "pip": f"python -m pip uninstall {DIST}",
    "dev": "delete this checkout (nothing was installed system-wide)",
}


def cache_dir() -> Path:
    return Path.home() / ".cache" / "constellation"  # read at call time so a test can point HOME elsewhere


def detect_method(prefix: str) -> str:
    """Guess how this copy was installed from `sys.prefix`; a path guess, so it can be wrong for unusual layouts."""
    p = prefix.replace("\\", "/")
    if "/uv/tools/" in p:
        return "uv tool"
    if "pipx/venvs" in p:
        return "pipx"
    if "/Cellar/" in p or "/homebrew/" in p:
        return "brew"
    if p.endswith("/.venv"):
        return "dev"
    return "pip"


def update_text(method: str) -> str:
    return (
        f"To upgrade Constellation ({method} install), run:\n  {_UPGRADE[method]}\n"
        "This command only prints it; nothing is downloaded or installed."
    )


def uninstall_text(method: str, cache: Path) -> str:
    return (
        "To remove Constellation:\n"
        f"  {_REMOVE[method]}\n"
        "Data it may have written (yours to keep or delete):\n"
        f"  {cache}/    caches, history, pins, habits\n"
        "  ./constellation.json    and any other --out files you chose\n"
        "  ~/.claude is never written or removed by Constellation."
    )


def uninstall(method: str, cache: Path, dry_run: bool, ask: Callable[[str], str], out: Callable[[str], None] = print) -> int:
    """Explain, then delete only `cache` after the user types CONFIRM. Exit 0 done or declined, 1 refused or failed."""
    out(uninstall_text(method, cache))
    if not cache.exists() and not cache.is_symlink():
        out("\nNo Constellation data found; nothing to delete.")
        return 0
    if cache.is_symlink() or not cache.is_dir() or cache.name != "constellation" or ".claude" in cache.resolve().parts:
        out(f"\nRefusing to delete {cache}: not a plain 'constellation' data directory.")
        return 1
    if dry_run:
        out(f"\nDry run: would delete {cache}. Nothing was changed.")
        return 0
    try:
        answer = ask(f"\nType '{CONFIRM}' to delete {cache} (anything else keeps it): ")
    except EOFError:  # no terminal to confirm on: keep the data
        out("Kept. Nothing was deleted.")
        return 0
    if answer.strip() != CONFIRM:
        out("Kept. Nothing was deleted.")
        return 0
    try:
        shutil.rmtree(cache)
    except OSError as e:
        out(f"Could not delete {cache}: {e.strerror or e}")
        return 1
    out(f"Deleted {cache}. Run the command above to remove the program itself.")
    return 0


@dataclass(frozen=True)
class Check:
    name: str
    status: str  # "ok" or "warn"
    detail: str


def _cache_check(cache: Path) -> Check:
    if not cache.is_dir():
        return Check("Cache dir", "ok", f"{cache} not created yet")
    loose = [str(p) for p in [cache, *cache.rglob("*")] if not p.is_symlink() and stat.S_IMODE(p.stat().st_mode) & 0o077]
    if loose:
        return Check("Cache dir", "warn", f"{len(loose)} path(s) readable by others (want 0700 dirs, 0600 files): {loose[0]}")
    if not os.access(cache, os.W_OK):
        return Check("Cache dir", "warn", f"{cache} is not writable; caches will be skipped")
    return Check("Cache dir", "ok", f"{cache} private and writable")


def env_checks(prefix: str, version: tuple[int, int], environ: Mapping[str, str], cache: Path) -> list[Check]:
    """Presence only: a key's value is never read into the output."""
    py = ".".join(map(str, version))
    checks = [
        Check("Python", "ok" if version >= (3, 13) else "warn", f"{py} (needs 3.13 or newer)" if version < (3, 13) else py),
        Check("Install method", "ok", detect_method(prefix)),
        _cache_check(cache),
    ]
    checks += [Check(k, "ok", "set" if environ.get(k) else "not set (offline mode is fine)") for k in KEY_VARS]
    return checks


def env_report(out: Callable[[str], None] = print) -> int:
    v = sys.version_info
    for c in env_checks(sys.prefix, (v.major, v.minor), os.environ, cache_dir()):
        out(f"  [{c.status:<4}] {c.name}: {c.detail}")
    return 0
