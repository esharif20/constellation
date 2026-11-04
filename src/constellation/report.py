from __future__ import annotations

import os
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .redact import redact

if TYPE_CHECKING:
    from .suggestions import Suggestion

VERDICTS = ("duplicate", "wrapper", "overlap")  # display order; "distinct" is hidden unless show_all
_STYLE = {"bold": "1", "dim": "2", "duplicate": "31", "wrapper": "33", "overlap": "36", "distinct": "32"}
_BAR = 10
NOTE = "Descriptions and reasons are redacted by pattern rules only; the scan file does not record your secrets."


def _paint(text: str, style: str, color: bool) -> str:
    return f"\033[{_STYLE[style]}m{text}\033[0m" if color else text


def _fit(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def _names(data: dict[str, Any]) -> dict[str, str]:
    return {i["id"]: f"{i['name']} ({i['kind']})" for i in data["items"]}


def _known_costs(data: dict[str, Any]) -> dict[str, int]:
    """Item id -> always-on tokens, for Items where it is known. Unknown is left out, never counted as 0."""
    return {k: c["always_on"] for k, c in (data.get("costs") or {}).items() if c and c.get("always_on") is not None}


def _ranked(data: dict[str, Any], known: dict[str, int]) -> list[dict[str, Any]]:
    return sorted((i for i in data["items"] if i["id"] in known), key=lambda i: (-known[i["id"]], i["name"], i["id"]))


def _heading(title: str, width: int, color: bool) -> str:
    rule = ("─" if color else "-") * (width - len(title) - 1)
    return "\n" + _paint(title, "bold", color) + " " + _paint(rule, "dim", color)


def _wrap(text: str, width: int, indent: str, first: str | None = None) -> str:
    return textwrap.fill(text, width, initial_indent=indent if first is None else first, subsequent_indent=indent)


def _session_start(data: dict[str, Any], names: dict[str, str], width: int, color: bool) -> list[str]:
    """What prompt-time hooks inject before you type, read from files without running anything; empty when the scan had none."""
    weights = data.get("hook_weights") or {}
    if not weights:
        return []
    out = [_heading("Session-start weight (hooks, nothing run)", width, color)]
    for id_ in sorted(weights, key=lambda i: names.get(i, i)):
        w = weights[id_]
        size = "unknown" if w["bytes"] is None else f"{w['bytes']:,} B" + (f", {w['tokens']:,} tokens" if w["tokens"] is not None else "")
        out.append(_wrap(f"{names.get(id_, id_)}: {size}", width, "      ", "  - "))
    known = [w for w in weights.values() if w["bytes"] is not None]
    tokens = [w["tokens"] for w in known if w["tokens"] is not None]
    size = sum(w["bytes"] for w in known)
    total = f"At least {size:,} bytes across {len(known)} of {len(weights)} hooks (lower bound; the rest are unknown)."
    total += f" At least {sum(tokens):,} tokens." if tokens else " Tokens not counted (use --count-bodies)."
    return [*out, "\n" + _wrap(total, width, "  ")]


def _pairs(data: dict[str, Any], verdict: str) -> list[tuple[str, str, str]]:
    names = _names(data)
    found = [
        (names.get(o["a_id"], o["a_id"]), names.get(o["b_id"], o["b_id"]), redact(o["reason"]))
        for o in data.get("overlaps") or []
        if o["verdict"] == verdict
    ]
    return sorted(found)


def render_report(data: dict[str, Any], *, top: int, color: bool, width: int, show_all: bool) -> str:
    items, names = data["items"], _names(data)
    known = _known_costs(data)
    kinds: dict[str, int] = {}
    for item in items:
        kinds[item["kind"]] = kinds.get(item["kind"], 0) + 1
    out = [_paint("Constellation report", "bold", color)]
    out.append(_wrap(f"Items: {len(items)} ({', '.join(f'{k} {n}' for k, n in sorted(kinds.items()))})", width, "  "))
    out.append(f"  Relations: {len(data.get('relations') or [])}   Clusters: {len(data.get('clusters') or [])}")

    out.append(_heading("Most expensive Items (always-on tokens)", width, color))
    ranked = _ranked(data, known)
    if not ranked:
        out.append("  Token costs were not measured in this scan.")
    cluster_of = {i: c["name"] for c in data.get("clusters") or [] for i in c["item_ids"]}
    labels = data.get("labels") or {}
    for rank, item in enumerate(ranked[:top], 1):
        tokens = known[item["id"]]
        bar = ("█" if color else "#") * (max(1, round(tokens / known[ranked[0]["id"]] * _BAR)) if tokens else 0)
        head = f"{rank:>2}  {tokens:>7,}  {bar:<{_BAR}}  "
        out.append(head + _fit(names[item["id"]], width - len(head)))
        notes = [f"{k} {v}" for k, v in (("cluster", cluster_of.get(item["id"])), ("purpose", labels.get(item["id"]))) if v]
        if notes:
            out.append(_paint(_fit("      " + " · ".join(notes), width), "dim", color))
        if item["description"]:
            out.append(_paint(_fit("      " + redact(item["description"]), width), "dim", color))
    unknown = len(items) - len(known)
    total = (
        f"Total always-on: {sum(known.values()):,} tokens across {len(known)} Items; {unknown} Items have unknown cost (not counted as 0)."
    )
    out.append("\n" + _wrap(total, width, "  "))

    out += _session_start(data, names, width, color)

    out.append(_heading("Overlaps", width, color))
    shown = VERDICTS + (("distinct",) if show_all else ())
    overlaps = data.get("overlaps") or []
    for verdict in shown:
        pairs = _pairs(data, verdict)
        if pairs:
            out.append(_paint(f"  {verdict} ({len(pairs)})", verdict, color))
        for a, b, reason in pairs:
            out.append(_wrap(f"{a} {'wraps' if verdict == 'wrapper' else 'and'} {b}", width, "    "))
            out.append(_paint(_wrap(reason, width, "      "), "dim", color))
    if not any(o["verdict"] in shown for o in overlaps):
        out.append("  None found.")
    hidden = 0 if show_all else sum(o["verdict"] == "distinct" for o in overlaps)
    if hidden:
        out.append(f"  ({hidden} distinct hidden; use --all to show them)")

    out.append(_heading("Warnings", width, color))
    out += [_wrap(redact(w), width, "    ", "  - ") for w in sorted(data.get("warnings") or [])] or ["  None."]
    out.append("\n" + _paint(_wrap(NOTE, width, ""), "dim", color))
    return "\n".join(out) + "\n"


def write_private(path: Path, text: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # pragma: no mutate (equivalent: the chmod below fixes the final mode)
    os.chmod(path, 0o600)  # the mode above applies only to a new file
    with os.fdopen(fd, "w") as f:
        f.write(text)


def _saving(s: Suggestion) -> str:
    return f"Saves about {s.tokens_saved:,} always-on tokens." if s.tokens_saved is not None else "Saving not measured."


def _approved(approved: list[Suggestion]) -> list[str]:
    return [f"- [ ] {s.reason} {_saving(s)} (id {s.id})" for s in approved] or ["None approved."]


def render_cleanup(data: dict[str, Any], *, top: int, approved: list[Suggestion] | None = None) -> str:
    """A markdown checklist the user acts on by hand. Same redaction as the report."""
    names, known = _names(data), _known_costs(data)
    lines = [
        "Constellation never edits your config. Every change below is yours to make by hand.",
        "",
        "# Constellation cleanup checklist",
        "",
    ]
    if approved is not None:
        lines += ["## Approved Suggestions", ""] + _approved(approved)
    else:
        lines += ["## Duplicates", ""]
        lines += [f"- [ ] Review and remove one of these two: {a} and {b}. {r}" for a, b, r in _pairs(data, "duplicate")] or ["None found."]
    lines += ["", "## Highest always-on cost", ""]
    lines += [f"- [ ] {names[i['id']]}: {known[i['id']]:,} tokens every session. Is it worth it?" for i in _ranked(data, known)[:top]] or [
        "Token costs were not measured."
    ]
    return "\n".join(lines) + "\n"
