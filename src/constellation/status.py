"""`constellation status`: one screen of setup health (the counterpart of Mole's `mo status`). Local and free: no provider call.

`build` is pure: it takes the saved scan, its verdicts, the weekly summary (or None when there is no earlier scan), the pin count and
today's date, and returns a Status. `render` draws it with the same Style as the other terminal reports.
"""

import json
import sys
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from . import history, weekly
from . import pins as pin_file
from .assessment import Assessed, compute
from .brief import build_brief
from .cli_reports import BAD, OK, WARN, WINDOW, Style
from .receipt import receipt
from .redact import redact

TOP = 8  # bars shown
BAR = 24  # width of the longest bar
STALE_DAYS = 14  # a scan older than this is called stale
_TIERS = (  # (label, tiers counted under it)
    ("Keep", ("keep", "keep_rare")),
    ("Review", ("review",)),
    ("Likely redundant", ("redundant",)),
    ("Could go", ("could_go",)),
    ("Not enough history", ("too_early",)),
)


@dataclass(frozen=True)
class Status:
    total: int | None  # always-on tokens at session start; None when nothing is measured
    unknown: int  # Items whose cost is not measured
    percent: float | None  # of the context window
    bars: list[tuple[str, int]]  # (plugin or kind, tokens), biggest first, at most TOP
    more: int  # groups not shown
    verdicts: list[tuple[str, int]]  # (label, count) in the order of _TIERS
    week: dict[str, Any] | None  # None: no earlier scan to compare with
    pins: int
    age_days: int | None  # None: the scan carries no date
    summary: str


def _bars(data: dict[str, Any]) -> tuple[list[tuple[str, int]], int]:
    """Always-on tokens grouped by owning plugin, or by kind for Items outside a plugin."""
    owner = {r["target"]: r["source"] for r in data.get("relations") or [] if r["kind"] == "contains"}
    names = {i["id"]: i["name"] for i in data["items"]}
    groups: dict[str, int] = {}
    for row in receipt(data)["rows"]:
        if row["tokens"] is not None:
            label = names.get(owner.get(row["id"])) or f"{row['kind']} (no plugin)"
            groups[label] = groups.get(label, 0) + row["tokens"]
    ranked = sorted(groups.items(), key=lambda g: (-g[1], g[0]))
    return [(redact(n), t) for n, t in ranked[:TOP]], max(0, len(ranked) - TOP)


def _week(w: dict[str, Any] | None) -> dict[str, Any] | None:
    if not w or w.get("state") != "ready":
        return None
    return {
        "since": w["since"],
        "delta": w["session_start"]["delta"],
        "added": len(w["added"]),
        "removed": len(w["removed"]),
        "quiet": [x["name"] for x in w["went_quiet"]],
    }


def _summary(count: dict[str, int], percent: float | None, age: int | None) -> str:
    removable = count["Likely redundant"] + count["Could go"]
    parts = [f"{removable} Items look removable" if removable else "nothing looks removable"]
    if percent is not None and percent >= 10:
        parts.append(f"session start takes {percent}% of the window")
    if age is not None and age > STALE_DAYS:
        parts.append(f"the scan is {age} days old, scan again")
    return ("Healthy: " if len(parts) == 1 and not removable else "Needs a look: ") + ", ".join(parts) + "."


def build(data: dict[str, Any], found: Assessed, week: dict[str, Any] | None, pins: int, today: str) -> Status:
    r = receipt(data)
    total = r["total_tokens"]
    percent = None if total is None else round(100 * total / WINDOW, 1)
    bars, more = _bars(data)
    tiers = [a.tier for a in found.assessments.values()]
    verdicts = [(label, sum(t in group for t in tiers)) for label, group in _TIERS]
    scanned = data.get("scanned_at")
    age = None if not isinstance(scanned, str) else max(0, (date.fromisoformat(today) - date.fromisoformat(scanned)).days)
    return Status(total, r["unknown"], percent, bars, more, verdicts, _week(week), pins, age, _summary(dict(verdicts), percent, age))


def _bar(tokens: int, top: int) -> str:
    return "█" * max(1, round(BAR * tokens / top))


def render(s: Status, st: Style) -> str:
    start = "not measured" if s.total is None else f"{s.total:,} tokens, {s.percent}% of a {WINDOW // 1000}k window"
    lines = [st.title("Constellation status"), "", f"  Session start: {start}" + (f" ({s.unknown} Items unmeasured)" if s.unknown else "")]
    if s.bars:
        lines.append(st.head("Always on, biggest first"))
        rows = [[n, _bar(t, s.bars[0][1]), f"{t:,}"] for n, t in s.bars]
        lines += st.table(rows)
        if s.more:
            lines.append(f"  and {s.more} more")
    lines += [st.head("Verdicts"), "  " + "   ".join(f"{label} {n}" for label, n in s.verdicts)]
    lines.append(st.head("This week"))
    w = s.week
    if w is None:
        lines.append("  No earlier scan to compare with yet. Scan again later.")
    else:
        cost = "session start not measured" if w["delta"] is None else f"session start {w['delta']:+,} tokens"
        lines.append(f"  Since {w['since']}: {w['added']} added, {w['removed']} removed, {cost}")
        lines.append("  Went quiet: " + (", ".join(w["quiet"]) or "nothing"))
    age = "unknown" if s.age_days is None else "today" if s.age_days == 0 else f"{s.age_days} days ago"
    stale = s.age_days is not None and s.age_days > STALE_DAYS
    lines += ["", f"  Pins: {s.pins}   Last scan: {age}"]
    mark = OK if s.summary.startswith("Healthy") else BAD if stale else WARN
    lines.append(f"  {st.mark(mark)} {s.summary}")
    return "\n".join(lines) + "\n"


def command(data: dict[str, Any], as_json: bool, st: Style) -> int:
    """`constellation status`. Reads the saved scan, the weekly sidecar and the pins; changes nothing."""
    try:
        found = compute(data)
        w = weekly.build(data, found, build_brief(data, found.assessments, found.evidence))
        ids = {i["id"] for i in data["items"]}
        status = build(data, found, w, sum(i in ids for i in pin_file.load(pin_file.DEFAULT_CACHE)), history._today())
    except (ValueError, TypeError, KeyError, AttributeError):
        print("The saved scan could not be read; run `constellation scan` again.", file=sys.stderr)
        return 2
    print(json.dumps(asdict(status), indent=2) if as_json else render(status, st), end="" if not as_json else "\n")
    return 0
