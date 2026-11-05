"""Scan history: one counts-only entry per (setup, UTC day), for the always-on cost time-lapse.

Privacy: an entry holds the setup key, a date, three counts and sorted hashed Item ids. It NEVER holds Item names,
descriptions, labels, cluster names, Overlap reasons, paths (the config dir only as a hash), origins, usage, warnings,
per-Item costs or file bodies. Hashed ids keep names out of a long-lived file; they are not a defence against someone
guessing names. The file is private (0600 in a 0700 directory) like the scan itself.
"""

import hashlib
import json
import os
import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from .report import _known_costs

DEFAULT_CACHE = Path.home() / ".cache" / "constellation" / "history.json"
KEEP_DAYS = 400
_KEYS = {"setup": str, "date": str, "items": int, "always_on": int, "unknown": int, "ids": list}


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def entry(data: dict[str, Any], setup: str, day: str) -> dict[str, Any]:
    known = _known_costs(data)
    ids = [i["id"] for i in data["items"]]
    return {
        "setup": setup,
        "date": day,
        "items": len(ids),
        "always_on": sum(known.values()),
        "unknown": sum(i not in known for i in ids),
        "ids": sorted(key(i) for i in ids),
    }


def _valid(e: object) -> bool:
    if not isinstance(e, dict) or e.keys() != _KEYS.keys() or any(type(e[k]) is not t for k, t in _KEYS.items()):
        return False
    try:
        date.fromisoformat(e["date"])
    except ValueError:
        return False
    return all(isinstance(i, str) for i in e["ids"])


def load(path: Path) -> list[dict[str, Any]]:
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    if not isinstance(raw, dict) or raw.get("v") != 1 or not isinstance(raw.get("entries"), list):
        return []
    return [e for e in raw["entries"] if _valid(e)]


def record(path: Path, e: dict[str, Any]) -> None:
    """Replace the same setup+date, drop entries over KEEP_DAYS older than the newest, then rewrite the whole file atomically."""
    entries = [x for x in load(path) if (x["setup"], x["date"]) != (e["setup"], e["date"])] + [e]
    cutoff = (date.fromisoformat(max(x["date"] for x in entries)) - timedelta(days=KEEP_DAYS)).isoformat()
    entries = sorted((x for x in entries if x["date"] >= cutoff), key=lambda x: (x["date"], x["setup"]))
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".history-")  # mkstemp creates the file 0600
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps({"v": 1, "entries": entries}))
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def timeline(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    """The API view: dates and counts only, never hashes, the setup key or a path."""
    setup, day = data.get("setup"), data.get("scanned_at")
    if not setup or not day:
        return {"entries": [], "first_seen": {}}
    mine = sorted((x for x in load(path) if x["setup"] == setup and x["date"] <= day), key=lambda x: x["date"])
    current = {i["id"]: key(i["id"]) for i in data["items"]}
    now = set(current.values())
    rows: list[dict[str, Any]] = []
    previous = set(mine[0]["ids"]) if mine else set()  # the first entry has nothing to be compared to
    for x in mine:
        ids = set(x["ids"])
        rows.append(
            {
                "date": x["date"],
                "items": x["items"],
                "always_on": x["always_on"],
                "unknown": x["unknown"],
                "added": len(ids - previous),
                "removed": len(previous - ids),
                "gone": len(ids - now),
            }
        )
        previous = ids
    # shortcut: `local/<n>/` MCP ids shift when the project set changes, so they show as removed + added; upgrade with a name fallback
    return {"entries": rows, "first_seen": {i: _first_seen(mine, h) for i, h in current.items()} if mine else {}}


def _first_seen(entries: list[dict[str, Any]], hashed: str) -> str:
    """Start of the latest unbroken run of entries holding the Item; an Item missing from the newest entry gets the newest date."""
    seen: str = entries[-1]["date"]
    for x in reversed(entries):
        if hashed not in x["ids"]:
            break
        seen = x["date"]
    return seen
