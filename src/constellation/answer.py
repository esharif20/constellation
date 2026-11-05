"""Plain-language answer blocks for local chat: wording, cards, verdicts and the plain-text rendering. Local signals only; no provider."""

import re
from datetime import date
from typing import Any

HEADLINE, WHAT, WHY, NEXT, NOTE, CHIP, TEXT = 140, 120, 90, 100, 160, 40, 1200
KINDS = {"mcp_server": "MCP server"}
_SKIP = re.compile(r"^(use when|use this|use for|trigger|invoke)", re.I)
_EXAMPLE = re.compile(r'"[^"]{2,}"|“[^”]{2,}”|(?:^|\s)/[a-z][\w:-]*(?=\s|$)')
_ABBREVIATION = re.compile(r"(?:^|\s)(?:(?i:e\.g|i\.e|etc|vs)|[A-Z])$")  # a word abbreviation in any case, or one capital letter


def cut(text: str, limit: int) -> str:
    """At most `limit` characters, ending in an ellipsis and never inside a word (a single long word is cut at limit - 1)."""
    if len(text) <= limit:
        return text
    space = text.rfind(" ", 0, limit)  # pragma: no mutate (equivalent: a leading space and no start both fall back to limit - 1)
    return text[: space if space > 0 else limit - 1].rstrip() + "…"


def _sentences(text: str) -> list[str]:
    out, start = [], 0
    for m in re.finditer(r"[.!?](?=\s|$)", text):
        before = text[start : m.start()]
        if _ABBREVIATION.search(before):
            continue
        out.append(text[start : m.end()].strip())
        start = m.end()
    if text[start:].strip():
        out.append(text[start:].strip())
    return out


def first_sentence(text: str, limit: int = WHAT) -> str:
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = " ".join(re.sub(r"[#*`]", "", text).split())
    sentences = _sentences(text)
    if not sentences:
        return "No description."
    keep = [s for s in sentences if not _SKIP.match(s) and not _EXAMPLE.search(s)]
    return cut((keep or sentences)[0], limit)


def plural(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def tokens(value: int | None, suffix: str = "") -> str:
    return "unknown" if value is None else f"{value:,} tokens{suffix}"


def _span(window: dict[str, Any] | None) -> int | None:
    if not window or not window.get("first"):
        return None
    return (date.fromisoformat(window["last"]) - date.fromisoformat(window["first"])).days + 1


def past(window: dict[str, Any] | None) -> str:
    span = _span(window)
    return f"{plural(span, 'day')} of past sessions" if span else "the saved past sessions"


def _usage(data: dict[str, Any], id_: str) -> tuple[str, int | None]:
    """The usage line and the count (None when usage was not read for this Item)."""
    window, usage = data.get("usage_window"), (data.get("usage") or {}).get(id_)
    if not window or not window["files"] or usage is None:
        return "Usage unknown", None
    span = _span(window)
    within = f" in {plural(span, 'day')}" if span else ""
    if not usage["count"]:
        return (f"Not seen in {plural(span, 'day')}" if span else "Not seen in past sessions"), 0
    last = f", last used {(d := date.fromisoformat(usage['last_used'][:10])).day} {d:%b}" if usage.get("last_used") else ""
    return f"Used {plural(usage['count'], 'time')}{within}{last}", usage["count"]


def _overlap(data: dict[str, Any], id_: str) -> dict[str, Any] | None:
    found = [o for o in data.get("overlaps") or [] if id_ in (o["a_id"], o["b_id"]) and o["verdict"] != "distinct"]
    order = ("duplicate", "wrapper", "overlap")
    return min(found, key=lambda o: (order.index(o["verdict"]), o["a_id"], o["b_id"]), default=None)


def verdict(data: dict[str, Any], id_: str) -> dict[str, str]:
    """A suggestion from local signals only; first match wins."""
    overlap = _overlap(data, id_)
    if overlap:
        names = {i["id"]: i["name"] for i in data["items"]}
        other = names[overlap["b_id"] if overlap["a_id"] == id_ else overlap["a_id"]]
        if overlap["verdict"] == "duplicate":
            return {"label": "Keep one", "tone": "remove", "why": cut(f"Does the same job as {other}", WHY)}
        if overlap["verdict"] == "wrapper":
            why = f"Wraps {other}" if overlap["a_id"] == id_ else f"Is called by {other}"
            return {"label": "Keep the wrapped one", "tone": "review", "why": cut(why, WHY)}
    line, count = _usage(data, id_)
    cost = ((data.get("costs") or {}).get(id_) or {}).get("always_on")
    if count is None:
        window = data.get("usage_window")
        where = "in this scan" if not window or not window["files"] else "for this Item"
        return {"label": "Not enough data", "tone": "unknown", "why": f"Usage was not read {where}"}
    if count:
        return {"label": "Keep", "tone": "keep", "why": cut(line.split(", last")[0], WHY)}
    if cost:
        return {
            "label": "Could go",
            "tone": "remove",
            "why": cut(f"Not seen in {past(data['usage_window'])} and costs {cost:,} tokens every session", WHY),
        }
    return {"label": "Review", "tone": "review", "why": cut(f"Not seen in {past(data['usage_window'])}", WHY)}


def kind_label(kind: str) -> str:
    return KINDS.get(kind, kind.replace("_", " "))


def card(data: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    id_ = item["id"]
    cost = (data.get("costs") or {}).get(id_) or {}
    overlap = _overlap(data, id_)
    shown = None
    if overlap:
        names = {i["id"]: i["name"] for i in data["items"]}
        with_id = overlap["b_id"] if overlap["a_id"] == id_ else overlap["a_id"]
        shown = {"with_id": with_id, "with_name": names[with_id], "verdict": overlap["verdict"], "reason": cut(overlap["reason"], WHAT)}
    return {
        "id": id_,
        "name": item["name"],
        "kind": item["kind"],
        "kind_label": kind_label(item["kind"]),
        "what": first_sentence(item["description"]),
        "always_on": tokens(cost.get("always_on")),
        "on_use": tokens(cost.get("on_use")),
        "usage": _usage(data, id_)[0],
        "overlap": shown,
        "verdict": verdict(data, id_),
    }


def row(item: dict[str, Any], value: str) -> dict[str, str]:
    return {
        "id": item["id"],
        "name": item["name"],
        "kind": item["kind"],
        "what": first_sentence(item["description"]),
        "value": value,
    }


def cost_value(data: dict[str, Any], id_: str) -> str:
    always_on = ((data.get("costs") or {}).get(id_) or {}).get("always_on")
    return "Cost unknown" if always_on is None else f"{always_on:,} tokens every session"


def comparison(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    ca, cb = card(data, a), card(data, b)
    clusters = data.get("clusters") or []
    return {
        "rows": [
            {"label": label, "a": ca[key], "b": cb[key]}
            for label, key in (
                ("Kind", "kind_label"),
                ("What it does", "what"),
                ("Every session", "always_on"),
                ("When used", "on_use"),
                ("Usage", "usage"),
            )
        ],
        "same_cluster": any(a["id"] in c["item_ids"] and b["id"] in c["item_ids"] for c in clusters),
    }


def blocks(
    headline: str,
    *,
    cards: list[dict[str, Any]] | None = None,
    compare: dict[str, Any] | None = None,
    rows: list[dict[str, str]] | None = None,
    more: int = 0,
    note: str | None = None,
    next_: str | None = None,
    follow_ups: list[str] | None = None,
    did_you_mean: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    chips = list(dict.fromkeys(c for c in follow_ups or [] if len(c) <= CHIP))  # callers keep to 2 cards, 5 rows, 3 chips, 3 candidates
    return {
        "headline": cut(headline, HEADLINE),
        "cards": cards or [],
        "compare": compare,
        "rows": rows or [],
        "more": more,
        "note": cut(note, NOTE) if note else None,
        "next": cut(next_, NEXT) if next_ else None,
        "follow_ups": chips,
        "did_you_mean": did_you_mean or [],
    }


def what_line(c: dict[str, Any]) -> str:
    return f"{c['name']} ({c['kind_label']}): {c['what']}"


def _card_text(c: dict[str, Any]) -> list[str]:
    lines = [what_line(c), f"Every session: {c['always_on']}. When used: {c['on_use']}. {c['usage']}."]
    if c["overlap"]:
        lines.append(f"{c['overlap']['verdict'].capitalize()} with {c['overlap']['with_name']}.")
    return [*lines, f"{c['verdict']['label']}: {c['verdict']['why']}."]


def to_text(b: dict[str, Any]) -> str:
    """The plain-text twin of the blocks, for the copy button, screen readers and old clients."""
    lines = [b["headline"]]
    if b["compare"]:
        lines += [f"{r['label']}: {r['a']} | {r['b']}" for r in b["compare"]["rows"]]
        lines.append(f"Same cluster: {'yes' if b['compare']['same_cluster'] else 'no'}")
    else:
        lines += [line for c in b["cards"] for line in _card_text(c) if line not in lines]  # the headline may already say it
    lines += [f"- {r['name']}: {r['value']}" for r in b["rows"]]
    if b["more"]:
        lines.append(f"{b['more']:,} more. Ask a narrower question.")
    if b["note"]:
        lines.append(b["note"])
    if b["next"]:
        lines.append(f"Next: {b['next']}")
    return cut("\n".join(lines), TEXT)
