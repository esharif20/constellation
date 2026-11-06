"""Per-project profile (#77): which global Items one project really uses and which are noise there.

Pure: reads one habit-ledger record and Item ids/names handed in; no I/O. The ledger holds only salted project hashes, so the
caller resolves what the user typed to a hash. Nothing here returns a hash or a path: output has Item names, counts and
digit dates, and the project only as the text the user typed.
"""

import re
from collections.abc import Callable
from datetime import date
from typing import Any

from .habits import NEW_DAYS, Ledger
from .usage import mac

MIN_SESSIONS = 5  # project sessions needed before anything is called noise there
LOCAL_MIN_USES = 5  # uses in the project before a skill is called a local-skill candidate
LOCAL_SHARE = 0.8  # share of all its uses that happen in this project
SHOWN = 15


def encode(text: str) -> str:
    """Claude Code's project folder naming (as usage._encode): every non-alphanumeric character becomes a dash."""
    return re.sub(r"[^A-Za-z0-9]", "-", text)


def resolve(typed: str, resolved_path: str | None, folders: list[str]) -> tuple[str | None, str | None]:
    """(folder, error). `resolved_path` is the typed text as an absolute path when it looks like one, else None (a bare name,
    which matches the end of a folder name and must be unambiguous)."""
    if resolved_path is not None:
        want = encode(resolved_path)
        return (want, None) if want in folders else (None, f"No history for '{typed}'. Pass the project folder you open Claude Code in.")
    tail = "-" + encode(typed).strip("-")
    hits = sorted(f for f in folders if f.endswith(tail))
    if len(hits) == 1:
        return hits[0], None
    if hits:
        return None, f"'{typed}' matches {len(hits)} projects. Pass the full folder path."
    return None, f"No history for '{typed}'. Pass the project folder you open Claude Code in."


def build(ledger: Ledger, today: str, tracked: dict[str, tuple[str, str]], folder: str, typed: str) -> dict[str, Any]:
    """`tracked` maps every global tracked Item id to (kind, name)."""
    key = mac(ledger["salt"], folder, 6)
    days = {d: r for d, r in ledger["days"].items() if d <= today and key in r["projects"]}
    out: dict[str, Any] = {
        "project": typed,
        "sessions": sum(r["projects"][key] for r in days.values()),
        "active_days": len(days),
        "state": "ok",
        "used": [],
        "noise": [],
        "local_candidates": [],
        "too_new": 0,
        "note": "",
    }
    if out["sessions"] < MIN_SESSIONS:
        out["state"] = "not_enough_history"
        out["note"] = f"Not enough history yet: {out['sessions']} session(s) seen here, {MIN_SESSIONS} needed."
        return out
    names = {mac(ledger["salt"], id_, 12): id_ for id_ in tracked}
    now = date.fromisoformat(today)
    for h, id_ in sorted(names.items(), key=lambda x: tracked[x[1]][1]):
        kind, name = tracked[id_]
        record = ledger["items"].get(h)
        if record is None or (now - date.fromisoformat(record["first_seen"])).days <= NEW_DAYS:
            out["too_new"] += 1  # it may not have existed while this project was active
            continue
        here = [(d, c["p"].get(key, 0)) for d, c in record["days"].items() if d <= today]
        uses = sum(n for _, n in here)
        total = sum(n for c in record["days"].values() for n in c["p"].values())
        row = {"name": name, "kind": kind, "uses": uses, "elsewhere": max(total - uses, 0)}
        if uses:
            out["used"].append({**row, "last_used": max(d for d, n in here if n)})
            if uses >= LOCAL_MIN_USES and uses >= LOCAL_SHARE * total:
                out["local_candidates"].append(row)
        else:
            out["noise"].append({**row, "why": "used only in other projects" if total else "not seen in any transcript"})
    out["used"].sort(key=lambda r: (-r["uses"], r["name"]))
    out["local_candidates"].sort(key=lambda r: (-r["uses"], r["name"]))
    return out


def render(p: dict[str, Any]) -> str:
    lines = [f"Profile of {p['project']}: {p['sessions']} session(s) over {p['active_days']} active day(s)."]
    if p["state"] != "ok":
        return "\n".join([*lines, p["note"]])
    sections: list[tuple[str, list[dict[str, Any]], Callable[[dict[str, Any]], str]]] = [
        (
            "Used here",
            p["used"],
            lambda r: f"{r['name']} ({r['kind']}): {r['uses']} here, {r['elsewhere']} elsewhere, last {r['last_used']}",
        ),
        ("Noise here (global, never used in this project)", p["noise"], lambda r: f"{r['name']} ({r['kind']}): {r['why']}"),
        (
            "Could be local to this project",
            p["local_candidates"],
            lambda r: f"{r['name']} ({r['kind']}): {r['uses']} uses here, {r['elsewhere']} elsewhere",
        ),
    ]
    for title, rows, fmt in sections:
        if rows:
            more = f"\n  ...and {len(rows) - SHOWN} more (see --json)" if len(rows) > SHOWN else ""
            lines += ["", f"{title}:", *(f"  {fmt(r)}" for r in rows[:SHOWN])]
            lines[-1] += more
    if p["too_new"]:
        lines += ["", f"{p['too_new']} Item(s) too new to judge for this project."]
    return "\n".join(lines)
