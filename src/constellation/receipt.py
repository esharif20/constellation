"""The session-start receipt: what loads before the first prompt, from the saved scan. Read-only, no provider call."""

from typing import Any

ORDER = ("hook", "memory", "skill", "agent", "command", "mcp_server", "connector")
COSTED = ("skill", "agent", "command")
UNMEASURED = ("mcp_server", "connector")  # tool schemas need Expansion (#9)


def _row(id_: str | None, kind: str, name: str, tokens: int | None, bytes_: int | None) -> dict[str, Any]:
    return {"id": id_, "kind": kind, "name": name, "tokens": tokens, "bytes": bytes_}


def receipt(data: dict[str, Any]) -> dict[str, Any]:
    costs = data.get("costs") or {}
    weights = data.get("hook_weights") or {}
    rows = []
    for item in data["items"]:
        if item.get("disabled"):
            continue
        id_, kind, name = item["id"], item["kind"], item["name"]
        if kind in COSTED:
            rows.append(_row(id_, kind, name, (costs.get(id_) or {}).get("always_on"), None))
        elif kind == "hook" and id_ in weights:
            tokens = weights[id_].get("tokens")
            rows.append(_row(id_, kind, name, tokens, None if tokens is not None else weights[id_].get("bytes")))
        elif kind in UNMEASURED:
            rows.append(_row(id_, kind, name, None, None))
    if data.get("memory_bytes") is not None:
        rows.append(_row(None, "memory", "CLAUDE.md", None, data["memory_bytes"]))
    groups = []
    for kind in ORDER:
        mine = [r for r in rows if r["kind"] == kind]
        if not mine:
            continue
        known = [r["tokens"] for r in mine if r["tokens"] is not None]
        groups.append(
            {
                "kind": kind,
                "count": len(mine),
                "tokens": sum(known) if known else None,
                "bytes": sum(r["bytes"] or 0 for r in mine),
                "unknown": sum(r["tokens"] is None and r["bytes"] is None for r in mine),
            }
        )
    known_groups = [g["tokens"] for g in groups if g["tokens"] is not None]
    rows.sort(key=lambda r: (r["tokens"] is None, -(r["tokens"] or 0), -(r["bytes"] or 0), r["name"], r["id"] or ""))
    return {
        "total_tokens": sum(known_groups) if known_groups else None,
        "uncounted_bytes": sum(g["bytes"] for g in groups),
        "unknown": sum(g["unknown"] for g in groups),
        "groups": groups,
        "rows": rows,
    }
