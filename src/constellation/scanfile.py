"""Which saved scan a command reads: an explicit path, else ./constellation.json, else the one the last scan remembered."""

import os
import stat
import sys
import tempfile
from pathlib import Path

LOCAL = Path("constellation.json")


def default_out() -> Path:
    return Path.home() / ".cache" / "constellation" / "scan.json"


def _pointer() -> Path:
    return default_out().with_name("latest")


def private_dir(path: Path) -> None:
    """Create the cache folder owner-only; mkdir's mode is masked by umask and ignored for a folder that exists."""
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def write_atomic(path: Path, text: str) -> None:
    """Write whole then move into place: O_EXCL 0600 temp (never follows a planted link), so a cancelled run leaves no partial file."""
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(name, path)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise


def _trusted_local() -> bool:
    """./constellation.json is trusted only if it is our own private regular file: not a link, ours, and not group/world readable."""
    try:
        st = LOCAL.lstat()
    except OSError:
        return False
    if stat.S_ISREG(st.st_mode) and st.st_uid == os.getuid() and not st.st_mode & 0o077:
        return True
    print(f"ignoring ./{LOCAL} (not a private file of yours); using the remembered scan. chmod 600 it to use it.", file=sys.stderr)
    return False


def target() -> Path:
    """Where `scan` writes with no --out: ./constellation.json if it is ours and private, else the per-user file."""
    return LOCAL if _trusted_local() else default_out()


def latest_scan(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit
    if _trusted_local():
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
        private_dir(pointer.parent)
        fd = os.open(pointer, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(str(path.resolve()))
    except OSError:
        pass


def shown(path: Path) -> str:
    """`~/...` for paths under home."""
    try:
        return "~/" + str(path.resolve().relative_to(Path.home().resolve()))
    except ValueError:
        return str(path)
