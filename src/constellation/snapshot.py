"""Pure public Snapshot privacy foundation; static bundle integration is separate."""

import re
from typing import Any

from .redact import REDACTED, redact

_KINDS = ("skill", "agent", "plugin", "hook", "mcp_server", "connector", "mcp_tool")
_EXECUTABLE_DESCRIPTIONS = {"hook": "Hook", "mcp_server": "MCP server", "connector": "Connector"}


# Public Snapshots hide identifying text as well as credentials. Remove whole URLs
# so userinfo, hostnames and private endpoint paths cannot survive independently.
_PUBLIC_IDENTIFIERS = re.compile(
    r"""\b[a-z][a-z0-9+.-]*://[^\s<>\"']+"""
    r"""|(?:[a-z]:[\\/]Users[\\/]|/(?:Users|home)/|~/)[^\s<>\"']+"""
    r"""|[^\s<>\"'@]+@[^\s<>\"'@]+"""
    r"|\b(?:[a-z0-9-]+\.)+[a-z0-9-]+\b|\blocalhost\b",
    re.IGNORECASE,
)


def _public_text(text: str) -> str:
    return redact(_PUBLIC_IDENTIFIERS.sub(REDACTED, text))


def _cost(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


def snapshot(data: dict[str, Any]) -> dict[str, Any]:
    """Allowlist saved scan fields and scrub public identifiers without reading credentials.

    Item ids are opaque ordinals assigned in sorted original-id order. List order is
    preserved, and filesystem provenance is replaced with an empty source string.
    Orphan or invalid references are dropped, including clusters with no members.
    """
    items = [i for i in data["items"] if i.get("kind") in _KINDS]
    ids = {id_: f"item-{n}" for n, id_ in enumerate(sorted({i["id"] for i in items}), 1)}

    def public_id(value: object) -> str | None:
        return ids.get(value) if isinstance(value, str) else None

    return {
        "items": [
            {
                "id": ids[i["id"]],
                "kind": _public_text(i["kind"]),
                "name": _public_text(i["name"]),
                "description": _public_text(
                    _EXECUTABLE_DESCRIPTIONS[i["kind"]] if i["kind"] in _EXECUTABLE_DESCRIPTIONS else i["description"]
                ),
                "source": "",
            }
            for i in items
        ],
        "relations": [
            {"source": source, "target": target, "kind": _public_text(r["kind"])}
            for r in data.get("relations") or []
            if (source := public_id(r.get("source"))) is not None and (target := public_id(r.get("target"))) is not None
        ],
        "labels": {id_: _public_text(label) for ref, label in (data.get("labels") or {}).items() if (id_ := public_id(ref)) is not None},
        "clusters": [
            {"name": _public_text(c["name"]), "item_ids": members}
            for c in data.get("clusters") or []
            if (members := [id_ for ref in c["item_ids"] if (id_ := public_id(ref)) is not None])
        ],
        "costs": {
            id_: {"always_on": _cost((c or {}).get("always_on")), "on_use": _cost((c or {}).get("on_use"))}
            for ref, c in (data.get("costs") or {}).items()
            if (id_ := public_id(ref)) is not None
        },
        "overlaps": [
            {"a_id": a_id, "b_id": b_id, "verdict": _public_text(o["verdict"]), "reason": _public_text(o["reason"])}
            for o in data.get("overlaps") or []
            if (a_id := public_id(o.get("a_id"))) is not None and (b_id := public_id(o.get("b_id"))) is not None
        ],
    }
