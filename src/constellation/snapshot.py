"""Pure public Snapshot privacy foundation; static bundle integration is separate."""

import re
import unicodedata
from typing import Any
from urllib.parse import unquote

from .redact import REDACTED, redact

_KINDS = ("skill", "agent", "plugin", "hook", "mcp_server", "connector", "mcp_tool", "command")
_RELATIONS = ("contains", "triggers")
_VERDICTS = ("duplicate", "wrapper", "overlap", "distinct")
_EXECUTABLE_DESCRIPTIONS = {"hook": "Hook", "mcp_server": "MCP server", "connector": "Connector"}


# Public Snapshots hide identifying text as well as credentials. Remove whole URLs
# so userinfo, hostnames and private endpoint paths cannot survive independently.
_SCHEME = r"[a-z][a-z0-9+.-]*://"
_PATH_START = (
    r"(?:[a-z]:[\\/]+"  # C:\work, C:\\work, D:/work
    r"|\\\\+[^\s\\/]"  # UNC \\host\share
    r"|/(?:Users|home|root|var|etc|tmp|opt|private|mnt|srv|Volumes|Library)\b"
    r"|~[\w.-]*[\\/]"  # ~/x, ~user/x
    rf"|{_SCHEME})"
)
_UNQUOTED = r"[^\s<>\"'`]+"
_PUBLIC_IDENTIFIERS = re.compile(
    rf"""(?P<q>["'`])(?={_PATH_START})[^\n]*?(?P=q)"""  # a quoted path, spaces and all, goes whole
    rf"|(?<![\w]){_PATH_START}{_UNQUOTED}"
    rf"|[^\s<>\"'`@]+@[^\s<>\"'`@]+"
    r"|\b\d{1,3}(?:\.\d{1,3}){3}\b(?::\d+)?"  # IPv4
    r"|(?<![\w:])(?:[0-9a-f]{1,4}:){7}[0-9a-f]{1,4}(?![\w:])"  # full IPv6
    r"|(?<![\w:])(?:[0-9a-f]{1,4}(?::[0-9a-f]{1,4}){0,6})?::(?:[0-9a-f]{1,4}(?::[0-9a-f]{1,4}){0,6})?(?![\w:])"  # compressed IPv6
    r"|\b(?:[\w-]+\.)+(?:local|internal|corp|lan)\b(?:\.[\w-]+)*(?::\d+)?"  # internal TLDs
    r"|\b[a-z][\w-]*:\d{2,5}\b"  # dotless host with a port
    r"|\blocalhost\b",
    re.IGNORECASE,
)
_DOTS = str.maketrans({"\u3002": ".", "\uff61": ".", "\uff0e": "."})


def _public_text(text: str) -> str:
    # Normalise first so fullwidth, ideographic-dot, zero-width and percent-encoded forms hit the same patterns.
    text = unicodedata.normalize("NFKC", text).translate(_DOTS)
    text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    for _ in range(8):  # pragma: no mutate  (repeated encoding; any bound above the tested depth is equivalent)
        if (decoded := unquote(text)) == text:
            break
        text = decoded
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
                **({"disabled": True} if i.get("disabled") is True else {}),
            }
            for i in items
        ],
        "relations": [
            {"source": source, "target": target, "kind": r["kind"]}
            for r in data.get("relations") or []
            if r.get("kind") in _RELATIONS
            and (source := public_id(r.get("source"))) is not None
            and (target := public_id(r.get("target"))) is not None
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
            {"a_id": a_id, "b_id": b_id, "verdict": o["verdict"], "reason": _public_text(o["reason"])}
            for o in data.get("overlaps") or []
            if o.get("verdict") in _VERDICTS
            and (a_id := public_id(o.get("a_id"))) is not None
            and (b_id := public_id(o.get("b_id"))) is not None
        ],
    }
