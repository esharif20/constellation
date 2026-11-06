"""Pins: Item ids the owner marked "keep" (smarter-verdict O4). A private (0600) local file: ids and a day, never sent anywhere."""

import json
import os
import tempfile
from datetime import date
from pathlib import Path

DEFAULT_CACHE = Path.home() / ".cache" / "constellation" / "pins.json"
MAX_PINS = 5000
MAX_ID = 400


def load(path: Path) -> dict[str, str]:
    """Item id -> day pinned. A missing, corrupt or odd file means no pins (never a crash)."""
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError, RecursionError):
        return {}
    pins = raw.get("pins") if isinstance(raw, dict) and raw.get("version") == 1 else None
    if not isinstance(pins, dict) or len(pins) > MAX_PINS:
        return {}
    ok = {k: v for k, v in pins.items() if isinstance(k, str) and len(k) <= MAX_ID and isinstance(v, str)}
    return ok


def add(path: Path, id_: str, day: str | None = None) -> bool:
    """Pin `id_` (validated by the caller against the current scan). False when it was already pinned. The caller serialises writers."""
    pins = load(path)
    if id_ in pins:
        return False
    if len(pins) >= MAX_PINS:
        raise ValueError("too many pins")
    pins[id_] = day or date.today().isoformat()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".pins-")  # mkstemp creates the file 0600
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps({"version": 1, "pins": pins}, sort_keys=True))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise
    return True
