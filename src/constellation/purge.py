"""Purge candidates: Items only dead projects ever used (read-only; nothing here deletes or writes).

Pure: reads one habit-ledger record, the scan's Item rows and costs, and the pinned ids handed in. The ledger holds only salted
project hashes, so output carries counts and digit dates, never a project label, hash or path.
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from . import habits, history, pins
from .habits import NEW_DAYS, Ledger
from .usage import TRACKED, mac

IDLE_DAYS = 60  # a project with no session for longer than this is called idle
SHOWN = 15


def build(ledger: Ledger, today: str, items: list[dict[str, Any]], costs: dict[str, Any], pinned: frozenset[str]) -> dict[str, Any]:
    now = date.fromisoformat(today)
    last: dict[str, str] = {}  # project hash -> last day it had a session
    for day, rec in ledger["days"].items():
        if day <= today:
            for p, n in rec["projects"].items():
                if n:
                    last[p] = max(last.get(p, day), day)
    cutoff = (now - timedelta(days=IDLE_DAYS)).isoformat()
    idle = {p for p, day in last.items() if day < cutoff}
    found: list[dict[str, Any]] = []
    for i in items:
        record = ledger["items"].get(mac(ledger["salt"], i["id"], 12))
        if i["kind"] not in TRACKED or i.get("scope", "global") != "global" or i.get("disabled") or i["id"] in pinned or record is None:
            continue
        if (now - date.fromisoformat(record["first_seen"])).days <= NEW_DAYS:
            continue
        users = {p for d, c in record["days"].items() if d <= today for p, n in c["p"].items() if n}
        if not users or not users <= idle:  # unused, or also used in an active (or unknown) project
            continue
        tokens = (costs.get(i["id"]) or {}).get("always_on")
        known = isinstance(tokens, int) and not isinstance(tokens, bool)
        since = max(last[p] for p in users)
        found.append(
            {
                "name": i["name"],
                "kind": i["kind"],
                "tokens": tokens if known else None,
                "idle_projects": len(users),
                "idle_since": since,
                "why": f"only used in {len(users)} idle project{'' if len(users) == 1 else 's'}, none active since {since}",
            }
        )
    found.sort(key=lambda r: (-(r["tokens"] or 0), r["name"]))
    return {"candidates": found, "tokens_saved": sum(r["tokens"] or 0 for r in found), "idle_days": IDLE_DAYS}


def render(p: dict[str, Any]) -> str:
    rows = p["candidates"]
    if not rows:
        return f"Nothing to purge: no Item is used only by projects idle for more than {p['idle_days']} days."
    lines = [f"{len(rows)} Item(s) only used by idle projects; removing all would save {p['tokens_saved']} tokens every session.", ""]
    for r in rows[:SHOWN]:
        cost = "unknown tokens" if r["tokens"] is None else f"{r['tokens']} tokens"
        lines.append(f"  {r['name']} ({r['kind']}): {cost}, {r['why']}")
    if len(rows) > SHOWN:
        lines.append(f"  ...and {len(rows) - SHOWN} more (see --json)")
    lines += ["", "Nothing was changed. Use `constellation remove-preview <name>` before removing anything."]
    return "\n".join(lines)


def command(habits_path: Path, as_json: bool, data: dict[str, Any] | None) -> int:
    """Print the candidates for an already-loaded saved scan (None: it was unreadable, the caller said why)."""
    if data is None:
        return 2
    ledger = habits.load(habits_path)[0].get(data.get("setup") or "")
    if ledger is None:
        print("No habit ledger for this scan yet. Run `constellation scan` first.", file=sys.stderr)
        return 2
    result = build(ledger, history._today(), data["items"], data.get("costs") or {}, frozenset(pins.load(pins.DEFAULT_CACHE)))
    print(json.dumps(result, indent=2) if as_json else render(result))
    return 0
