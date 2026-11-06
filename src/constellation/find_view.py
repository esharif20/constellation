"""`constellation find` output: small cards, one dim warnings line. Pure: callers print the returned lines."""

import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .cli_reports import Style

LIMIT = 8
FETCH = 200  # pragma: no mutate  # search at most this many so the header can count every match
DESCRIPTION_CHARS = 100
LOOSE = "frontmatter is not valid YAML"
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


def split_warnings(warnings: Sequence[str]) -> tuple[list[str], list[str]]:
    """(loose-frontmatter warnings, every other warning)."""
    loose = [w for w in warnings if LOOSE in w]
    return loose, [w for w in warnings if LOOSE not in w]


def as_json(hits: Sequence[dict[str, Any]], query: str, other_warnings: Sequence[str]) -> dict[str, Any]:
    keys = ("name", "kind", "description", "invoke", "why")
    rows = [{**{k: clean(str(h[k])) for k in keys}, "origin": origin(h["invoke"]), "rank": n} for n, h in enumerate(hits, 1)]
    return {"query": query, "hits": rows, "warnings": [clean(w) for w in other_warnings]}


def render(
    hits: Sequence[dict[str, Any]],
    query: str,
    warnings_count: int,
    style: Style,
    width: int,
    *,
    limit: int | None = LIMIT,
    closest: Sequence[str] = (),
) -> list[str]:
    shown = hits[:limit]  # limit None shows every hit
    if not hits:
        lines = [style.title(fit(f'No match for "{query}". Try fewer or different words.', width))]
        if closest:
            lines += ["", fit("Closest names: " + ", ".join(closest), width)]
    else:
        noun = "skill" if len(hits) == 1 else "skills"
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
