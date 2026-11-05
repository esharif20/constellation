from __future__ import annotations

from collections import Counter
from typing import Any

from .report import _fit, _paint

_SIGN = {"+": "overlap", "-": "duplicate", "~": "wrapper"}  # green/red/yellow would be nicer, but reuse report's palette


def _cost(data: dict[str, Any], id: str, key: str) -> int | None:
    return ((data.get("costs") or {}).get(id) or {}).get(key)


def _row(data: dict[str, Any], it: dict[str, Any]) -> dict[str, Any]:
    return {"id": it["id"], "kind": it["kind"], "name": it["name"], "always_on": _cost(data, it["id"], "always_on")}


def _totals(data: dict[str, Any]) -> tuple[int, int]:
    known = [_cost(data, i["id"], "always_on") for i in data["items"]]
    return sum(k for k in known if k is not None), sum(k is None for k in known)


def _unique(items: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    counts = Counter((i["kind"], i["name"]) for i in items)
    return {(i["kind"], i["name"]): i for i in items if counts[(i["kind"], i["name"])] == 1}


def _order(r: dict[str, Any]) -> tuple[str, str, str]:
    return r["kind"], r["name"], r["id"]


def diff_scans(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Added, removed and changed Items between two saved scans, plus the always-on change. Descriptions are compared, never output."""
    new_by_id = {i["id"]: i for i in new["items"]}
    pairs = [(o, new_by_id[o["id"]]) for o in old["items"] if o["id"] in new_by_id]
    gone = [o for o in old["items"] if o["id"] not in new_by_id]
    fresh = [n for n in new["items"] if n["id"] not in {o["id"] for o in old["items"]}]
    new_names = _unique(fresh)
    for key, o in _unique(gone).items():  # same kind and name under another id: other machine, shifted local/<n>/ scope
        if key in new_names:
            pairs.append((o, new_names[key]))
    matched_old = {o["id"] for o, _ in pairs}
    matched_new = {n["id"] for _, n in pairs}
    changed = []
    for o, n in pairs:
        before = {"always_on": _cost(old, o["id"], "always_on"), "on_use": _cost(old, o["id"], "on_use")}
        after = {"always_on": _cost(new, n["id"], "always_on"), "on_use": _cost(new, n["id"], "on_use")}
        before.update(description=o.get("description"), disabled=bool(o.get("disabled")))
        after.update(description=n.get("description"), disabled=bool(n.get("disabled")))
        fields = [f for f in ("always_on", "on_use", "description", "disabled") if before[f] != after[f]]
        if fields:
            changed.append(
                {
                    **_row(new, n),
                    "fields": fields,
                    "always_on": [before["always_on"], after["always_on"]],
                    "on_use": [before["on_use"], after["on_use"]],
                }
            )
    (total_old, unknown_old), (total_new, unknown_new) = _totals(old), _totals(new)
    return {
        "added": sorted((_row(new, n) for n in new["items"] if n["id"] not in matched_new), key=_order),
        "removed": sorted((_row(old, o) for o in old["items"] if o["id"] not in matched_old), key=_order),
        "changed": sorted(changed, key=_order),
        "always_on": {
            "old": total_old,
            "new": total_new,
            "delta": total_new - total_old,
            "unknown_old": unknown_old,
            "unknown_new": unknown_new,
        },
        "dates": [old.get("scanned_at"), new.get("scanned_at")],
    }


def _tokens(n: int | None) -> str:
    return "unknown" if n is None else f"{n:,} tokens"


def _shift(label: str, pair: list[int | None]) -> str:
    return f"{label} {' -> '.join('unknown' if v is None else str(v) for v in pair)}"


def render_diff(d: dict[str, Any], *, color: bool, width: int) -> str:
    o, n = (x or "unknown date" for x in d["dates"])
    t = d["always_on"]
    lines = [
        _paint(f"Setup diff: {o} -> {n}", "bold", color),
        f"Always-on: {t['old']:,} -> {t['new']:,} tokens ({t['delta']:+,}); unknown {t['unknown_old']} -> {t['unknown_new']}",
    ]
    for title, key, sign in (("Added", "added", "+"), ("Removed", "removed", "-"), ("Changed", "changed", "~")):
        if not d[key]:
            continue
        lines += ["", _paint(f"{title} ({len(d[key])})", "bold", color)]
        for r in d[key]:
            if key == "changed":
                detail = ", ".join(_shift(f.replace("_", "-"), r[f]) if f in ("always_on", "on_use") else f for f in r["fields"])
            else:
                detail = _tokens(r["always_on"])
            lines.append(_paint(_fit(f"{sign} {r['kind']}  {r['name']}  {detail}", width), _SIGN[sign], color))
    if not (d["added"] or d["removed"] or d["changed"]):
        lines += ["", "No differences."]
    return "\n".join(lines) + "\n"
