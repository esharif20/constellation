"""Free local compare/explain for chat: parse the question, then build plain-text cards from the saved scan only (no provider, no model)."""

import re
from datetime import date
from typing import Any

_PRONOUN = {"it", "i t", "its", "that", "this", "one"}
_WHAT = r"(?:wh?a?t(?:\s+(?:is|are)|'?s)|explain|describe|tell me about)"
_COMPARE = r"compar\w*"
_JOIN = r"(?:to|with|and|against|vs\.?|versus)"
_PATTERNS = [  # group a: an early subject that "it" refers to; b and c: the two names
    rf"^(?P<a>.*?)\s*(?:\b(?:and|an|also|then)\s+)?how\s+(?:does|do|is|are)\s+(?P<b>.+?)\s+{_COMPARE}\s+(?:to|with|against)\s+(?P<c>.+)$",
    r"difference\w*\s+(?:between|of)\s+(?P<b>.+?)\s+and\s+(?P<c>.+)$",
    rf"\b{_COMPARE}\s+(?P<b>.+?)\s+{_JOIN}\s+(?P<c>.+)$",
    r"^(?P<b>.+?)\s+(?:vs\.?|versus)\s+(?P<c>.+)$",
]
_ENDS = re.compile(r"\b(?:an|and|also|then|please|to|with)$")


def clean_name(text: str) -> str:
    text = re.sub(rf"^\s*(?:{_WHAT}\s+)?(?:(?:the|a|an)\s+)?", "", text.lower().replace("’", "'"))
    text = re.sub(r"[^\w\s'-]", " ", text)
    text = " ".join(text.split())
    while (stripped := _ENDS.sub("", text).strip()) != text:
        text = stripped
    return text


def parse_compare(question: str) -> tuple[str, str] | None:
    """The two cleaned names, or None. The first is "" when the question only says "it" (the caller supplies the selected Item)."""
    q = question.lower().replace("’", "'")
    for pattern in _PATTERNS:
        if match := re.search(pattern, q):
            groups = match.groupdict()
            first, second, third = clean_name(groups.get("a", "")), clean_name(groups["b"]), clean_name(groups["c"])
            # "wht is pony tail an how does I t compare to shovel": the early subject is the first Item and "it" refers to it
            first = first if first and second in _PRONOUN else second
            return ("" if first in _PRONOUN else first), third
    return None


def parse_what(question: str) -> str | None:
    match = re.match(rf"^\s*{_WHAT}\s+(.+)$", question.lower().replace("’", "'"))
    return clean_name(match[1]) if match else None


def first_sentence(text: str, limit: int = 110) -> str:
    text = " ".join(re.sub(r"[`*_#>]+", "", text).split())
    sentence = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0] if text else "no description"
    return sentence[:limit].rstrip() + "…" if len(sentence) > limit else sentence


def _tokens(value: int | None) -> str:
    return "unknown" if value is None else f"{value:,} tokens"


def _usage(data: dict[str, Any], id_: str) -> str:
    window, usage = data.get("usage_window"), (data.get("usage") or {}).get(id_)
    if not window or not window["files"] or usage is None:
        return "unknown (not read for this Item)"
    if usage["count"]:
        last = f", last {usage['last_used'][:10]}" if usage.get("last_used") else ""
        return f"{usage['count']} {'use' if usage['count'] == 1 else 'uses'}{last}"
    if window["first"]:
        return f"never seen in {(date.fromisoformat(window['last']) - date.fromisoformat(window['first'])).days + 1} days"
    return "never seen in the scanned transcripts"


def _cluster(data: dict[str, Any], id_: str) -> str | None:
    return next((c["name"] for c in data.get("clusters") or [] if id_ in c["item_ids"]), None)


def _card(data: dict[str, Any], item: dict[str, Any]) -> list[str]:
    cost = (data.get("costs") or {}).get(item["id"]) or {}
    lines = [
        f"{item['name']}",
        f"- Kind: {item['kind']}",
        f"- Does: {first_sentence(item['description'])}",
        f"- Always-on: {_tokens(cost.get('always_on'))}",
        f"- On-use: {_tokens(cost.get('on_use'))}",
        f"- Usage: {_usage(data, item['id'])}",
    ]
    if cluster := _cluster(data, item["id"]):
        lines.append(f"- Cluster: {cluster}")
    return lines


def _overlap(data: dict[str, Any], a: str, b: str) -> dict[str, Any] | None:
    return next((o for o in data.get("overlaps") or [] if {o["a_id"], o["b_id"]} == {a, b}), None)


def _recommendation(overlap: dict[str, Any] | None, names: dict[str, str]) -> str:
    verdict = overlap["verdict"] if overlap else "distinct"
    if verdict == "duplicate":
        return "duplicate: keep one"
    if verdict == "wrapper" and overlap:
        return f"wrapper: keep the wrapped one ({names[overlap['b_id']]}); {names[overlap['a_id']]} only calls it"
    if verdict == "overlap":
        return "partial overlap: keep both only if you need the difference"
    return "different jobs"


def explain_card(data: dict[str, Any], item: dict[str, Any]) -> str:
    lines = _card(data, item)
    related = [o for o in data.get("overlaps") or [] if item["id"] in (o["a_id"], o["b_id"]) and o["verdict"] != "distinct"]
    names = {i["id"]: i["name"] for i in data["items"]}
    for o in related[:3]:
        other = o["b_id"] if o["a_id"] == item["id"] else o["a_id"]
        lines.append(f"- {o['verdict'].capitalize()} with {names[other]}")
    return "\n".join(lines)


def compare_card(data: dict[str, Any], a: dict[str, Any], b: dict[str, Any]) -> str:
    overlap = _overlap(data, a["id"], b["id"])
    cluster_a, cluster_b = _cluster(data, a["id"]), _cluster(data, b["id"])
    same = (
        "same cluster" if cluster_a and cluster_a == cluster_b else "different clusters" if cluster_a and cluster_b else "cluster unknown"
    )
    names = {a["id"]: a["name"], b["id"]: b["name"]}
    verdict = f"{overlap['verdict']}: {overlap['reason']}" if overlap else "none recorded in this scan"
    return "\n".join(
        [
            f"{a['name']} vs {b['name']}",
            "",
            *_card(data, a),
            "",
            *_card(data, b),
            "",
            f"Overlap: {verdict}",
            f"Clusters: {same}",
            f"Suggestion: {_recommendation(overlap, names)}",
        ]
    )
