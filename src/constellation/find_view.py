"""`constellation find` output: small cards, one dim warnings line. Pure: callers print the returned lines."""

import re
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # cli_reports imports chat, which imports this module
    from .cli_reports import Style

LIMIT = 8
FETCH = 200  # pragma: no mutate  # search at most this many so the header can count every match
DESCRIPTION_CHARS = 100
LOOSE = "frontmatter is not valid YAML"
FORGOTTEN_DAYS = 30
KINDS = {"skill": "skill", "agent": "agent", "command": "command", "mcp": "mcp_server"}  # --kind word -> Item kind
_REDACTED = re.compile(r"\s*\[REDACTED\]\s*")


def clean(text: str) -> str:
    """One line: the home folder as `~`, redaction markers dropped, whitespace collapsed."""
    home = str(Path.home())
    return " ".join(_REDACTED.sub(" ", text.replace(home, "~")).split())


def trim(text: str, chars: int) -> str:
    """At most `chars` characters plus an ellipsis, cut at a word boundary."""
    if len(text) <= chars:
        return text
    head = text[:chars]
    if text[chars] != " " and " " in head:
        head = head.rsplit(" ", 1)[0]
    return head.rstrip(" ,;:.-") + "…"


def fit(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def origin(invoke: str) -> str:
    """`/plugin:name` comes from a plugin; a bare `/name` is the user's own."""
    head, colon, _ = invoke[1:].partition(":")
    return head if colon else "yours"


def annotate(hits: Sequence[dict[str, Any]], scan: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Add last_used (a day or None), usage_known and always_on from the saved scan; hit ids are the scan's ids."""
    scan = scan or {}
    usage, costs = scan.get("usage") or {}, scan.get("costs") or {}
    rows = []
    for h in hits:
        last = (usage.get(h["id"]) or {}).get("last_used")
        always_on = (costs.get(h["id"]) or {}).get("always_on")
        rows.append({**h, "usage_known": bool(scan.get("usage_window")), "last_used": last[:10] if last else None, "always_on": always_on})
    return rows


def idle_days(hit: dict[str, Any], today: date) -> int | None:
    return (today - date.fromisoformat(hit["last_used"])).days if hit.get("last_used") else None


def is_forgotten(hit: dict[str, Any], today: date) -> bool:
    """Seen in no transcript, or not for FORGOTTEN_DAYS; unknown usage is never called forgotten."""
    idle = idle_days(hit, today)
    return bool(hit.get("usage_known")) and (idle is None or idle >= FORGOTTEN_DAYS)


def refine(
    hits: Sequence[dict[str, Any]], today: date, *, forgotten: bool = False, origin_filter: str | None = None
) -> list[dict[str, Any]]:
    """Keep hits by --forgotten and --origin (plugin = from any plugin, yours = your own)."""
    return [
        h
        for h in hits
        if (not forgotten or is_forgotten(h, today))
        and (origin_filter is None or (origin(h["invoke"]) == "yours") == (origin_filter == "yours"))
    ]


def last_seen(hit: dict[str, Any], today: date) -> str:
    idle = idle_days(hit, today)
    if not hit.get("usage_known"):
        return "usage not read"
    if idle is None:
        return "never seen used"
    if idle < 1:
        return "last used today"
    for unit, size in (("month", 30), ("week", 7), ("day", 1)):
        if idle >= size or unit == "day":
            n = idle // size
            return f"last used {n} {unit}{'' if n == 1 else 's'} ago"
    return ""  # pragma: no cover


def cost_text(hit: dict[str, Any]) -> str:
    n = hit.get("always_on")
    return "cost unknown" if n is None else f"{n:,} tokens every session"


def split_warnings(warnings: Sequence[str]) -> tuple[list[str], list[str]]:
    """(loose-frontmatter warnings, every other warning)."""
    loose = [w for w in warnings if LOOSE in w]
    return loose, [w for w in warnings if LOOSE not in w]


def as_json(hits: Sequence[dict[str, Any]], query: str, other_warnings: Sequence[str], today: date | None = None) -> dict[str, Any]:
    keys = ("name", "kind", "description", "invoke", "why")
    rows = [
        {
            **{k: clean(str(h[k])) for k in keys},
            "origin": origin(h["invoke"]),
            "rank": n,
            "last_used": h.get("last_used"),
            "always_on": h.get("always_on"),
            "last_seen": last_seen(h, today or date.today()),
        }
        for n, h in enumerate(hits, 1)
    ]
    return {"query": query, "hits": rows, "warnings": [clean(w) for w in other_warnings]}


def render(
    hits: Sequence[dict[str, Any]],
    query: str,
    warnings_count: int,
    style: "Style",
    width: int,
    *,
    limit: int | None = LIMIT,
    closest: Sequence[str] = (),
    today: date | None = None,
) -> list[str]:
    shown = hits[:limit]  # limit None shows every hit
    if not hits:
        lines = [style.title(fit(f'No match for "{query}". Try fewer or different words.', width))]
        if closest:
            lines += ["", fit("Closest names: " + ", ".join(closest), width)]
    else:
        words = ("skill", "skills") if all(h["kind"] == "skill" for h in hits) else ("match", "matches")
        noun = words[len(hits) != 1]
        lines = [style.title(fit(f'Found {len(hits)} {noun} for "{query}"', width)), ""]
        for n, hit in enumerate(shown, 1):
            prefix = f"{n}.".ljust(len(str(len(shown))) + 1) + " "
            meta = f"{hit['kind']} · {origin(hit['invoke'])}"
            name = fit(clean(hit["name"]), max(8, width - len(prefix) - len(meta) - 2))
            lines.append(prefix + style.title(name) + "  " + style.paint(meta, "dim"))
            pad = " " * len(prefix)
            room = width - len(prefix)
            lines.append(pad + fit(trim(clean(hit["description"]), DESCRIPTION_CHARS), room))
            lines.append(pad + style.paint(fit("matched: " + clean(hit["why"]), room), "dim"))
            if "usage_known" in hit:
                lines.append(pad + style.paint(fit(f"{last_seen(hit, today or date.today())} · {cost_text(hit)}", room), "dim"))
            lines += [pad + fit(clean(hit["invoke"]), room), ""]
        if len(shown) < len(hits):
            more = f"Showing {len(shown)} of {len(hits)} (--all shows every match, --limit N sets it)."
            lines.append(style.paint(fit(more, width), "dim"))
        else:
            lines.pop()
    if warnings_count:
        files = "1 file had" if warnings_count == 1 else f"{warnings_count} files had"
        text = f"{files} loose frontmatter and {'was' if warnings_count == 1 else 'were'} read leniently (--verbose lists them)"
        lines += ["", style.paint(fit(text, width), "dim")]
    return lines
