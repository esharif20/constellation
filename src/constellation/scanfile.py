"""Which saved scan a command reads: an explicit path, else ./constellation.json, else the one the last scan remembered."""

from pathlib import Path

LOCAL = Path("constellation.json")


def default_out() -> Path:
    return Path.home() / ".cache" / "constellation" / "scan.json"


def _pointer() -> Path:
    return default_out().with_name("latest")


def target() -> Path:
    """Where `scan` writes with no --out: ./constellation.json if it already exists, else the per-user file."""
    return LOCAL if LOCAL.is_file() else default_out()


def latest_scan(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit
    if LOCAL.is_file():
        return LOCAL
    try:
        remembered = Path(_pointer().read_text().strip())
    except (OSError, ValueError):
        return LOCAL  # the caller reports the missing file as it always has
    return remembered if remembered.is_file() else LOCAL


def remember(path: Path) -> None:
    """Best effort: failing to remember must never fail a scan."""
    try:
        pointer = _pointer()
        pointer.parent.mkdir(parents=True, exist_ok=True)
        pointer.write_text(str(path.resolve()))
        pointer.chmod(0o600)
    except OSError:
        pass


def shown(path: Path) -> str:
    """`~/...` for paths under home."""
    try:
        return "~/" + str(path.resolve().relative_to(Path.home().resolve()))
    except ValueError:
        return str(path)
