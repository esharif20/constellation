"""Read-only trigger audit over saved skill metadata and usage counts."""

from statistics import median
from typing import Any

GREEDY_MIN = 20


def trigger_audit(data: dict[str, Any]) -> dict[str, Any]:
    window = data.get("usage_window")
    files = window.get("files") if isinstance(window, dict) else 0
    if not files:
        return {"files": 0, "rows": []}

    usage = data.get("usage") or {}
    skills = [item for item in data["items"] if item.get("kind") == "skill" and not item.get("disabled") and item.get("id") in usage]
    positive_counts = [usage[item["id"]]["count"] for item in skills if usage[item["id"]]["count"] > 0]
    greedy_limit = max(GREEDY_MIN, 4 * median(positive_counts)) if positive_counts else GREEDY_MIN

    rows = []
    for item in skills:
        record = usage[item["id"]]
        count = record["count"]
        flags = []
        if count == 0:
            flags.append("never")
            if len(item.get("description", "").split()) < 8:
                flags.append("vague")
        if count >= greedy_limit:
            flags.append("greedy")
        if flags:
            rows.append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "count": count,
                    "last_used": record.get("last_used"),
                    "flags": flags,
                }
            )

    # Greedy rows have positive counts; never rows have zero, so this is also greedy-first.
    rows.sort(key=lambda row: (-row["count"], row["name"], row["id"]))
    return {"files": files, "rows": rows}
