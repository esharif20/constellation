"""Weekly state of your setup (#75): what changed since the last recorded scan, what a session costs now vs then, which Items went
quiet, and the reclaimable range with its confidence. Local and free: no provider call, no transcript read.

history.py keeps only hashed ids and counts, so it cannot name a removed Item or hold a verdict. Each scan therefore also writes one
snapshot per (setup, day) to a private (0600) sidecar file: Item kind, name, tier, the first reason, the always-on cost and a use count,
keyed by hashed id, plus the reclaimable range. It is local like the scan itself and never reaches the public export.
The summary shown to the owner (and copied from the Brief) holds kinds, names, labels, reasons and counts, never a hash or a path.
"""

import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

from . import history
from .answer import clean_name
from .assessment import Assessed, compute
from .brief import build_brief
from .habits import OVERDUE_MULT
from .verdict_types import ItemEvidence

DEFAULT_CACHE = Path.home() / ".cache" / "constellation" / "weekly.json"
KEEP = 60  # snapshots kept
TOP = 5  # rows in the "used most" list
MEDIUM_DAYS, HIGH_DAYS = 14, 30  # active days of history behind the range
FIRST = "Not enough history yet: this is the first scan recorded for this setup. Scan again later and this page compares the two."
_SEVERITY = ("could_go", "redundant", "review", "too_early", "keep_rare", "keep", "untracked", "off")
_ITEM = {"k": str, "n": str, "t": str, "l": str, "w": str, "q": bool}


def _count(n: object) -> bool:
    return type(n) is int and n >= 0


def _day(value: object) -> bool:
    try:
        return isinstance(value, str) and date.fromisoformat(value).isoformat() == value  # 3.13 also accepts 20261105
    except ValueError:
        return False


def _item_ok(v: object) -> bool:
    if not isinstance(v, dict) or v.keys() != {*_ITEM, "c", "u"}:
        return False
    return all(type(v[k]) is t for k, t in _ITEM.items()) and _count(v["u"]) and (v["c"] is None or _count(v["c"]))


def _reclaim_ok(r: object) -> bool:
    if not isinstance(r, dict) or r.keys() != {"low", "high", "unknown", "confidence"}:
        return False
    return all(_count(r[k]) for k in ("low", "high", "unknown")) and r["confidence"] in ("high", "medium", "low")


def _valid(s: object) -> bool:
    if not isinstance(s, dict) or s.keys() != {"setup", "date", "items", "reclaim"}:
        return False
    if not isinstance(s["setup"], str) or not _day(s["date"]) or not isinstance(s["items"], dict):
        return False
    return all(isinstance(h, str) and _item_ok(v) for h, v in s["items"].items()) and _reclaim_ok(s["reclaim"])


def _read(path: Path) -> list[Any] | None:
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError:
        return []
    except (OSError, ValueError, RecursionError):
        return None
    ok = isinstance(raw, dict) and raw.get("v") == 1 and isinstance(raw.get("snapshots"), list)
    return raw["snapshots"] if ok else None


def load(path: Path, *, warn: bool = False) -> list[dict[str, Any]]:
    """Valid snapshots only. A missing file is no history; a corrupt one is no history and says so when asked."""
    raw = _read(path)
    if raw is None:
        if warn:
            print(f"weekly history {path} could not be read; starting it over", file=sys.stderr)
        return []
    return [s for s in raw if _valid(s)]


def record(path: Path, snap: dict[str, Any]) -> None:
    """Replace the same setup and day, keep the newest KEEP, rewrite the file atomically at 0600."""
    kept = [s for s in load(path, warn=True) if (s["setup"], s["date"]) != (snap["setup"], snap["date"])] + [snap]
    kept = sorted(kept, key=lambda s: (s["date"], s["setup"]))[-KEEP:]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".weekly-")  # mkstemp creates the file 0600
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps({"v": 1, "snapshots": kept}))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def _confidence(found: Assessed) -> str:
    days = found.evidence.active_days
    return "low" if days < MEDIUM_DAYS else "medium" if days < HIGH_DAYS or not found.ledger else "high"


def _quiet(ev: ItemEvidence) -> bool:
    """Used before, with a known rhythm, and idle for more than OVERDUE_MULT typical gaps (habits.profile's `overdue`)."""
    return ev.mean_gap is not None and ev.idle_active_days is not None and ev.idle_active_days > OVERDUE_MULT * ev.mean_gap


def snapshot(data: dict[str, Any], found: Assessed, brief: dict[str, Any]) -> dict[str, Any]:
    """This scan as a snapshot (see the module docstring). `brief` is build_brief()'s answer for the same scan."""
    costs = data.get("costs") or {}
    items = {}
    for i in data["items"]:
        a, ev = found.assessments[i["id"]], found.evidence.items.get(i["id"])
        quiet = ev is not None and _quiet(ev)
        items[history.key(i["id"])] = {
            "k": i["kind"], "n": i["name"], "t": a.tier, "l": a.label, "w": a.reasons[0].text, "q": quiet,
            "c": (costs.get(i["id"]) or {}).get("always_on"), "u": ev.sessions_used if ev else 0,
        }  # fmt: skip
    r = brief["range"]
    reclaim = {"low": r["low"], "high": r["high"], "unknown": r["unknown"], "confidence": _confidence(found)}
    return {"setup": data.get("setup"), "date": data.get("scanned_at"), "items": items, "reclaim": reclaim}


def record_scan(data: dict[str, Any], path: Path | None = None) -> list[str]:
    """Called by `scan` after the habit ledger is updated. Never raises: a warning is returned instead."""
    try:
        found = compute(data)
        record(path or DEFAULT_CACHE, snapshot(data, found, build_brief(data, found.assessments, found.evidence)))
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        return [f"could not save the weekly snapshot: {error}"]
    return []


def _row(s: dict[str, Any], h: str) -> dict[str, str]:
    return {"kind": s["items"][h]["k"], "name": clean_name(s["items"][h]["n"])}


def _rows(s: dict[str, Any], hashes: set[str]) -> list[dict[str, str]]:
    return sorted((_row(s, h) for h in hashes), key=lambda r: (r["kind"], r["name"]))


def _start(s: dict[str, Any]) -> tuple[int | None, int]:
    """Always-on tokens of the Items with a known cost (None when no Item has one, never 0) and how many are unknown."""
    costs = [i["c"] for i in s["items"].values()]
    known = [c for c in costs if c is not None]
    return (sum(known) if known else None), len(costs) - len(known)


def _tokens(r: dict[str, Any]) -> str:
    return f"{r['low']:,}" if r["low"] == r["high"] else f"{r['low']:,} to {r['high']:,}"


def summarize(now: dict[str, Any], saved: list[dict[str, Any]], today: str, since: str | None = None) -> dict[str, Any]:
    """Compare `now` with the newest earlier snapshot of the same setup. Snapshots dated after `today` (clock skew) are ignored,
    and with `since` the baseline is the newest one dated on or before it."""
    older = [s for s in saved if s["setup"] == now["setup"] and s["date"] < now["date"] and s["date"] <= today]
    older = [s for s in older if since is None or s["date"] <= since]
    if not older:
        return {"state": "first", "headline": FIRST}
    then = max(older, key=lambda s: s["date"])
    a, b = now["items"], then["items"]
    added, removed = _rows(now, a.keys() - b.keys()), _rows(then, b.keys() - a.keys())
    (total_now, unknown_now), (total_then, unknown_then) = _start(now), _start(then)
    delta = None if total_now is None or total_then is None else total_now - total_then
    flips = sorted((h for h in a.keys() & b.keys() if a[h]["t"] != b[h]["t"]), key=lambda h: (_SEVERITY.index(a[h]["t"]), a[h]["n"], h))
    quiet = {h for h in a.keys() if a[h]["q"] and not (h in b and b[h]["q"])}
    used = [(a[h]["u"] - (b[h]["u"] if h in b else 0), h) for h in a]
    used = sorted((x for x in used if x[0] > 0), key=lambda x: (-x[0], a[x[1]]["n"], x[1]))[:TOP]
    parts = [f"{len(added)} added, {len(removed)} removed" if added or removed else "no Items added or removed"]
    if delta is None:
        parts.append("session start cost not measured")
    else:
        parts.append(
            f"session start {total_then:,} to {total_now:,} tokens ({delta:+,})"
            + (" counting known costs only" if unknown_now + unknown_then else "")
        )
    if quiet:
        parts.append(f"{len(quiet)} went quiet")
    parts.append(f"you could free {_tokens(now['reclaim'])} tokens (was {_tokens(then['reclaim'])})")
    return {
        "state": "ready",
        "since": then["date"],
        "days": (date.fromisoformat(now["date"]) - date.fromisoformat(then["date"])).days,
        "headline": f"Since {then['date']}: " + "; ".join(parts) + ".",
        "added": added,
        "removed": removed,
        "session_start": {"then": total_then, "now": total_now, "delta": delta, "unknown_then": unknown_then, "unknown_now": unknown_now},
        "verdict_changes": [{**_row(now, h), "from": b[h]["l"], "to": a[h]["l"], "why": a[h]["w"]} for h in flips],
        "went_quiet": _rows(now, quiet),
        "used_most": [{**_row(now, h), "uses": n} for n, h in used],
        "reclaim": {"now": now["reclaim"], "then": then["reclaim"]},
    }


def build(
    data: dict[str, Any], found: Assessed, brief: dict[str, Any], path: Path | None = None, since: str | None = None
) -> dict[str, Any]:
    """The summary for a saved scan, read from the sidecar; the first-scan state when this scan cannot be told apart from history."""
    now = snapshot(data, found, brief)
    if not _valid(now):
        return {"state": "first", "headline": FIRST}
    return summarize(now, load(path or DEFAULT_CACHE), history._today(), since)


def render(w: dict[str, Any]) -> str:
    lines = ["Weekly state of your setup", w["headline"]]
    if w["state"] != "ready":
        return "\n".join(lines) + "\n"
    s, r = w["session_start"], w["reclaim"]
    for title, rows in (("Added", w["added"]), ("Removed", w["removed"]), ("Went quiet", w["went_quiet"])):
        if rows:
            lines += ["", f"{title} ({len(rows)})", *(f"  {x['kind']}  {x['name']}" for x in rows)]
    if w["verdict_changes"]:
        lines += ["", "Verdict changes", *(f"  {x['name']}: {x['from']} -> {x['to']}  ({x['why']})" for x in w["verdict_changes"])]
    if w["used_most"]:
        lines += ["", "Used most", *(f"  {x['name']}  {x['uses']} sessions" for x in w["used_most"])]
    start = "not measured" if s["delta"] is None else f"{s['then']:,} -> {s['now']:,} tokens ({s['delta']:+,})"
    lines += ["", f"Session start: {start}; unknown cost {s['unknown_then']} -> {s['unknown_now']}"]
    lines += [f"Reclaimable: {_tokens(r['now'])} tokens, {r['now']['confidence']} confidence; was {_tokens(r['then'])}"]
    if r["now"]["unknown"]:
        lines += [f"  + {r['now']['unknown']} with unknown cost, not counted"]
    return "\n".join(lines) + "\n"


def command(data: dict[str, Any], as_json: bool, since: str | None) -> int:
    """`constellation weekly`. Reads the sidecar and the saved scan's habits; changes nothing."""
    if since is not None and not _day(since):
        print("--since must be a date like 2026-11-01.", file=sys.stderr)
        return 2
    try:
        found = compute(data)
        w = build(data, found, build_brief(data, found.assessments, found.evidence), since=since)
    except (ValueError, TypeError, KeyError, AttributeError):
        print("The saved scan could not be read; run `constellation scan` again.", file=sys.stderr)
        return 2
    print(json.dumps(w, indent=2)) if as_json else print(render(w), end="")
    return 0
