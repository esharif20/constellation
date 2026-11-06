"""Read-only safe-removal preview for one Item, built from the saved (already redacted) scan. Nothing is deleted, read or sent."""

import re
from typing import Any

MIN_NAME = 3  # shortcut: a shorter name would match inside ordinary words; upgrade when scans carry real file references
MAX_NEIGHBOURS = 6
SAME_JOB = {"duplicate", "overlap"}


def _row(item: dict[str, Any], why: str) -> dict[str, Any]:
    return {"id": item["id"], "name": item["name"], "kind": item["kind"], "why": why}


def removal_preview(data: dict[str, Any], item_id: str) -> dict[str, Any]:
    """What loses coverage, what refers to the Item and which hooks call it. Raises KeyError for an id the scan does not hold."""
    items = {i["id"]: i for i in data["items"]}
    item = items[item_id]
    relations = data.get("relations") or []
    live = {i: o for i, o in items.items() if i != item_id and not o.get("disabled")}

    covered: dict[str, dict[str, Any]] = {}
    wrappers: set[str] = set()
    for o in data.get("overlaps") or []:
        if item_id not in (o["a_id"], o["b_id"]):
            continue
        other = o["b_id"] if o["a_id"] == item_id else o["a_id"]
        if o["verdict"] == "wrapper" and o["b_id"] == item_id:
            wrappers.add(other)  # a wrapper over this Item stops working without it
        elif o["verdict"] in SAME_JOB and other in live:
            covered[other] = {**_row(live[other], o["reason"]), "verdict": o["verdict"]}
    cluster = next((c for c in data.get("clusters") or [] if item_id in c["item_ids"]), None)
    neighbours = [live[i]["name"] for i in (cluster["item_ids"] if cluster else []) if i in live and i not in covered]

    callers: dict[str, str] = {i: "calls it" for i in wrappers if i in live}
    callers |= {
        r["source"]: "calls it" for r in relations if r["target"] == item_id and r["kind"] in ("triggers", "uses") and r["source"] in live
    }
    name = item["name"]
    if len(name) >= MIN_NAME:
        pattern = re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])", re.IGNORECASE)
        for i, other in live.items():
            if i not in callers and pattern.search(other.get("description") or ""):
                callers[i] = "mentions its name"
    hooks = [_row(live[i], why) for i, why in callers.items() if live[i]["kind"] == "hook"]
    refs = [_row(live[i], why) for i, why in callers.items() if live[i]["kind"] != "hook"]
    parts = [
        _row(items[r["target"]], "goes with it")
        for r in relations
        if r["source"] == item_id and r["kind"] == "contains" and r["target"] in items
    ]

    uses = (data.get("usage") or {}).get(item_id) or {}
    count = uses.get("count")
    loses = not covered
    reasons = []
    if refs:
        reasons.append("1 other Item refers to it." if len(refs) == 1 else f"{len(refs)} other Items refer to it.")
    if hooks:
        reasons.append("1 hook calls or names it." if len(hooks) == 1 else f"{len(hooks)} hooks call or name it.")
    if parts:
        reasons.append(f"Removing it also removes its {len(parts)} part{'s' if len(parts) > 1 else ''}.")
    if loses and isinstance(count, int) and count > 0:
        reasons.append(f"Nothing else does the same job, and you used it {count} time{'s' if count > 1 else ''}.")
    safe = not reasons
    for sort_rows in (hooks, refs, parts):
        sort_rows.sort(key=lambda r: (r["name"], r["id"]))
    return {
        "id": item_id,
        "name": name,
        "kind": item["kind"],
        "safe": safe,
        "verdict": "Safe to remove" if safe else "Check these first",
        "reasons": reasons or ["Nothing refers to it and nothing relies on it alone."],
        "loses_coverage": loses,
        "covered_by": sorted(covered.values(), key=lambda r: (r["name"], r["id"])),
        "cluster": {
            "name": cluster["name"],
            "others": sorted(neighbours)[:MAX_NEIGHBOURS],
            "more": max(0, len(neighbours) - MAX_NEIGHBOURS),
        }
        if cluster and neighbours
        else None,
        "referenced_by": refs,
        "hooks": hooks,
        "contains": parts,
        "used": count if isinstance(count, int) else None,
        "last_used": uses.get("last_used"),
    }
