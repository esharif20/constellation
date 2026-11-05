import os
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .report import CAVEAT, _known_costs, _names, _ranked, _saving
from .suggestions import Suggestion, _make, suggest

HEADER = "Constellation never edits your config. Every change below is yours to make by hand.\n\n# Constellation cleanup checklist\n\n"


def checklist_ids(text: str) -> list[str]:
    ids = []
    for line in text.splitlines():
        match = re.fullmatch(r"- \[[ xX]\] .+ \(id ([0-9a-f]{12})\)", line)
        if match:
            ids.append(match[1])
    return list(dict.fromkeys(ids))


def append_line(path: Path, s: Suggestion) -> bool:
    """Append a server-selected Suggestion; the caller serialises concurrent updates."""
    try:
        text = path.read_text()
    except FileNotFoundError:
        text = ""
    if s.id in checklist_ids(text):
        if path.exists():
            path.chmod(0o600)  # a loose file is tightened even when nothing is added
        return False
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    reason = " ".join(s.reason.splitlines())
    line = f"- [ ] {reason} {_saving(s)} (id {s.id})\n"
    if not text:
        line = f"{HEADER}{line}"
    elif not text.endswith("\n"):
        line = f"\n{line}"
    # O_APPEND, never truncate: a user's edit made since the read above survives, and one write keeps the line whole.
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    fd = os.open(path, flags, 0o600)  # pragma: no mutate
    os.chmod(path, 0o600)  # the mode above applies only to a new file
    with os.fdopen(fd, "a") as f:
        f.write(line)
    return True


def frees(rows: list[dict[str, Any]], known: dict[str, int]) -> int | None:
    """Count each removable Item once, excluding rows whose saving is unknown."""
    ids = {row["removes"] for row in rows if row["tokens_saved"] is not None and row["removes"] in known}
    return sum(known[id_] for id_ in ids) if ids else None


def brief(data: dict[str, Any], top: int = 5) -> dict[str, Any]:
    """Rank the saved scan locally; unknown costs are never treated as zero."""
    known, names = _known_costs(data), _names(data)
    rows = []
    for item in _ranked(data, known)[:top]:
        id_ = item["id"]
        reason = f"{names[id_]}: {known[id_]:,} always-on tokens every session. Is it worth it?"
        s = _make("review_cost", (id_,), reason, known[id_])
        rows.append({**asdict(s), "item_ids": list(s.item_ids), "removes": id_})
    pairs = []
    candidates = [s for s in suggest(data) if s.kind in ("remove_duplicate", "use_underlying")]
    for s in candidates[:top]:
        removes = None
        if s.kind == "use_underlying":
            removes = s.item_ids[0]
        elif all(id_ in known for id_ in s.item_ids):
            removes = min(s.item_ids, key=lambda id_: (known[id_], id_))
        pairs.append({**asdict(s), "item_ids": list(s.item_ids), "removes": removes})
    scope = [
        {**asdict(s), "item_ids": list(s.item_ids), "removes": None, "project_label": (data.get("projects") or {}).get(s.project)}
        for s in suggest(data)
        if s.kind == "move_to_project"
    ][:top]
    unknown_pairs = sum(row["tokens_saved"] is None for row in pairs)
    return {
        "cost": {
            "rows": rows,
            "unknown": sum(i["id"] not in known for i in data["items"]),
            "measured": bool(known),
            "unknown_rows": 0,
            "frees": frees(rows, known),
        },
        "scope": {"rows": scope, "caveat": CAVEAT},
        "pairs": {"rows": pairs, "unknown": unknown_pairs, "unknown_rows": unknown_pairs, "frees": frees(pairs, known)},
    }
