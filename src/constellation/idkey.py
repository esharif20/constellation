"""The per-install random key that makes saved Item ids unique without letting a guessed secret be checked against them."""

import os
import secrets
from pathlib import Path


def id_key(path: Path) -> bytes:
    """Read the key, creating it (0600, in a 0700 directory) on first use. An unwritable cache gives a one-run key, never a crash."""
    try:
        return bytes.fromhex(path.read_text().strip())[:32] if path.is_file() and len(path.read_text().strip()) == 64 else _make(path)
    except (OSError, ValueError):
        return secrets.token_bytes(32)


def _make(path: Path) -> bytes:
    key = secrets.token_bytes(32)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "w") as f:
        f.write(key.hex())
    return key
