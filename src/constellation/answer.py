"""Plain-language answer blocks for local chat: wording, cards, verdicts and the plain-text rendering. Local signals only; no provider."""

import re
import unicodedata
from datetime import date
from typing import Any

HEADLINE, WHAT, WHY, NEXT, NOTE, CHIP, TEXT = 140, 120, 90, 100, 160, 40, 1200
KINDS = {"mcp_server": "MCP server"}
LATELY_DAYS = 30  # the span "lately" means in a question; a window for listing, never a verdict threshold (verdict.py decides those)
TONE = {  # an Assessment tier as Ask's tone; the tier names and labels come from verdict.py
    "keep": "keep", "keep_rare": "keep", "review": "review", "too_early": "review",
    "redundant": "remove", "could_go": "remove", "off": "unknown", "untracked": "unknown",
}  # fmt: skip
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


def idle_days(data: dict[str, Any], id_: str) -> tuple[int, bool] | None:
    """(days idle, exact) to the newest saved session. Never seen = the whole window, a lower bound (exact False). None = unknown."""
    window, usage = data.get("usage_window"), (data.get("usage") or {}).get(id_)
    if not window or usage is None:  # the callers have already checked that transcripts exist
        return None
    if not usage["count"]:
        span = _span(window)
        return (span, False) if span else None
    if not usage.get("last_used") or not window.get("last"):
        return None
    return max(0, (date.fromisoformat(window["last"]) - date.fromisoformat(usage["last_used"][:10])).days), True


def _overlap(data: dict[str, Any], id_: str) -> dict[str, Any] | None:
    found = [o for o in data.get("overlaps") or [] if id_ in (o["a_id"], o["b_id"]) and o["verdict"] != "distinct"]
    order = ("duplicate", "wrapper", "overlap")
    return min(found, key=lambda o: (order.index(o["verdict"]), o["a_id"], o["b_id"]), default=None)


def verdict(data: dict[str, Any], id_: str) -> dict[str, str]:
    """The Item's Assessment (verdict.assess, shared with the Inspector and the Brief) in Ask's label / tone / why shape."""
    found = (data.get("assessments") or {}).get(id_)
    if found is None:
        return {"label": "Not enough data", "tone": "unknown", "why": "No verdict is available for this Item"}
    return {"label": found["label"], "tone": TONE[found["tier"]], "why": cut(found["reasons"][0]["text"], WHY)}


def kind_label(kind: str) -> str:
    return KINDS.get(kind, kind.replace("_", " "))


_DO = {  # what Claude Code is asked to do for an Item worth acting on, per kind; {n} is the quoted name
    "skill": "Remove the skill {n}: find its folder (under ~/.claude/skills) and delete only that folder.",
    "agent": "Remove the agent {n}: find its file (under ~/.claude/agents) and delete only that file.",
    "command": "Remove the command {n}: find its file (under ~/.claude/commands) and delete only that file.",
    "mcp_server": "Remove the MCP server {n} from my Claude Code config, in the scope where it is defined.",
    "plugin": "Disable the plugin {n} in my user settings.json enabledPlugins; do not delete files.",
    "hook": "Remove the hook {n} from the hooks section of my settings.json.",
    "connector": "Disconnect the connector {n}. It is managed in claude.ai, so tell me where to click.",
}
_CONFIRM = " Show me exactly what will change and wait for my OK."
INSTRUCTION = 400


def handoff(data: dict[str, Any], item: dict[str, Any], overlap: dict[str, Any] | None) -> dict[str, Any]:
    """A copyable instruction for Claude Code and the checklist row that can be added for this Item. The Assessment's action decides
    (like frontend/src/lib/instruction.ts); the Overlap only names the other Item."""
    id_, name, label = item["id"], quote(item["name"]), kind_label(item["kind"])
    action = ((data.get("assessments") or {}).get(id_) or {}).get("action", "none")
    other = None  # pragma: no mutate (equivalent: only read when there is an overlap)
    names = {i["id"]: i["name"] for i in data["items"]}
    twin = ((data.get("assessments") or {}).get(id_) or {}).get("twin_id")
    if twin in names:  # the Item the engine compared, not whichever Overlap is shown
        other = quote(names[twin])
    elif overlap:
        other = quote(names[overlap["b_id"] if overlap["a_id"] == id_ else overlap["a_id"]])

    def remove() -> str:
        text = _DO.get(item["kind"], "Review the " + label + " {n} and tell me how to remove it.").format(n=name)
        origin = item.get("origin")
        if origin and item["kind"] in ("skill", "agent", "mcp_server"):
            text += f" It came from {quote(origin)}: if that is a plugin or pack, change it there, not inside its folder."
        return text

    if action == "use_underlying" and other:
        text = f"The {label} {name} only calls {other}. Show me how to use {other} directly, then remove {name}."
    elif action == "remove_twin" and other:
        text = f"{remove()} It does the same job as {other}, which stays."
    elif action == "move_to_project":
        text = f"Move the {label} {name} out of my global setup into the one project that uses it. Leave every other project as it is."
    elif action == "fix_description":
        text = (
            f"Rewrite the description of the {label} {name} so Claude knows when to pick it: "
            "say what it does and when to use it. Keep the rest unchanged."
        )
    elif action in ("remove", "disable_plugin", "remove_twin"):
        text = remove()
    else:
        text = f"Review the {label} {name}: tell me what it does and whether I still need it. Change nothing."
    if not text.endswith("Change nothing."):
        text += _CONFIRM
    return {"instruction": cut(text, INSTRUCTION), "checklist_id": (data.get("checklist") or {}).get(id_)}


def card(data: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    id_ = item["id"]
    cost = (data.get("costs") or {}).get(id_) or {}
    overlap = _overlap(data, id_)
    decided, shown = verdict(data, id_), None
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
        "verdict": decided,
        "handoff": handoff(data, item, overlap),
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
    handoff: dict[str, Any] | None = None,
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
        "handoff": handoff,
    }


REFUSALS = {
    "edit": "Constellation never changes your files. Claude Code can, and it asks you first.",
    "body": "Constellation does not read or show file contents. Claude Code can open the file for you.",
    "debug": "Constellation sees how your setup is shaped, not how it ran. Claude Code can look at the failure.",
    "general": "That is outside what this scan holds, so I would only guess. Claude Code is the better place to ask.",
}
_ASK = {  # what Claude Code is asked to do, per refusal; {q} is the user's own words, {of} the Item or nothing
    "edit": "{q}{of}. Show me every change before you make it and wait for my OK.",
    "body": "Open the file{of} and tell me what it says, in full. Do not change anything.",
    "debug": "Help me debug this: {q}{of}. Read the logs and my config, and change nothing until I agree.",
    "general": "{q}",
}


def refusal(category: str, question: str, item: dict[str, Any] | None) -> tuple[str, dict[str, Any]]:
    """The honest one-line refusal and a copyable instruction for Claude Code. Text only: nothing is run or written."""
    q = cut(" ".join(question.split()).rstrip("?.!"), 200)
    of = (
        f" (the {kind_label(item['kind'])} {quote(item['name'])})"
        if item and (category == "body" or item["name"].lower() not in q.lower())
        else ""
    )
    return REFUSALS[category], {"instruction": _ASK[category].format(q=q, of=of), "checklist_id": None}


NAME_MAX = 80


def clean_name(name: str) -> str:
    """A third-party name made safe to paste into an instruction or a checklist line: one line, no control characters, at most
    NAME_MAX characters. Mirrors cleanName() in frontend/src/lib/instruction.ts."""
    text = " ".join("".join(" " if ch.isspace() or unicodedata.category(ch)[0] == "C" else ch for ch in name).split())
    return text if len(text) <= NAME_MAX else text[: NAME_MAX - 1] + "…"


def quote(name: str) -> str:
    """The cleaned name in a code span (backticks inside become apostrophes), so it reads as a name and not as an instruction."""
    return "`" + clean_name(name).replace("`", "'") + "`"


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
    if b["handoff"]:
        lines.append(f"Ask Claude Code: {b['handoff']['instruction']}")
    return cut("\n".join(lines), TEXT)
