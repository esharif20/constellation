"""Pure public Snapshot privacy foundation; static bundle integration is separate."""

from typing import Any

from .redact import redact


def _cost(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


def snapshot(data: dict[str, Any]) -> dict[str, Any]:
    """Allowlist saved scan fields and redact patterns only, without reading credentials.

    Item ids are opaque ordinals assigned in sorted original-id order. List order is
    preserved, and filesystem provenance is replaced with an empty source string.
    Orphan or invalid references are dropped, including clusters with no members.
    """
    ids = {id_: f"item-{n}" for n, id_ in enumerate(sorted({i["id"] for i in data["items"]}), 1)}

    def public_id(value: object) -> str | None:
        return ids.get(value) if isinstance(value, str) else None

    return {
        "items": [
            {
                "id": ids[i["id"]],
                "kind": redact(i["kind"]),
                "name": redact(i["name"]),
                "description": redact(i["description"]),
                "source": "",
            }
            for i in data["items"]
        ],
        "relations": [
            {"source": source, "target": target, "kind": redact(r["kind"])}
            for r in data.get("relations", [])
            if (source := public_id(r.get("source"))) is not None and (target := public_id(r.get("target"))) is not None
        ],
        "labels": {id_: redact(label) for ref, label in data.get("labels", {}).items() if (id_ := public_id(ref)) is not None},
        "clusters": [
            {"name": redact(c["name"]), "item_ids": members}
            for c in data.get("clusters", [])
            if (members := [id_ for ref in c["item_ids"] if (id_ := public_id(ref)) is not None])
        ],
        "costs": {
            id_: {"always_on": _cost((c or {}).get("always_on")), "on_use": _cost((c or {}).get("on_use"))}
            for ref, c in data.get("costs", {}).items()
            if (id_ := public_id(ref)) is not None
        },
        "overlaps": [
            {"a_id": a_id, "b_id": b_id, "verdict": redact(o["verdict"]), "reason": redact(o["reason"])}
            for o in data.get("overlaps", [])
            if (a_id := public_id(o.get("a_id"))) is not None and (b_id := public_id(o.get("b_id"))) is not None
        ],
    }
