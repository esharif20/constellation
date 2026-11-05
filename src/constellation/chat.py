"""Free local answers over saved metadata; no provider or persisted conversation."""

import hashlib
import json
import re
import threading
from collections import OrderedDict
from collections.abc import Callable
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context

from .answer import blocks, card, comparison, cost_value, past, plural, row, to_text, what_line
from .brief import frees, removes
from .compare import parse_compare, parse_keep, parse_what
from .redact import redact
from .report import _known_costs, _never_used, _ranked
from .retrieve import Index
from .suggestions import suggest

_STOP = set("what can help me to do a an the with for please find search show highlight focus filter on items item".split())
ASK_NEXT = ["What costs the most every session?", "What have I never used?"]
_NOT_WHAT = (
    r"(?<![\w-])(this|these|selected|costs?|tokens?|usage|used|unused|never|duplicates?|wrappers?|overlaps?)(?![\w-])"  # not inside a name
)


class ChatState(TypedDict):
    question: str
    selected: list[str]
    data: dict[str, Any]
    matches: list[str]
    response: dict[str, Any]
    intent: str
    scope: list[str]
    index: Any


def _strip(question: str) -> str:
    return re.sub(r"^(?:show(?: me)? everything that touches|what do i have for)\s+", "", question.lower().strip())


def _retrieve(state: ChatState) -> dict[str, Any]:
    question, items = state["question"], state["data"]["items"]
    question = _strip(question)  # lower-cased and trimmed
    tokens = [t for t in re.findall(r"[^\W_]+", question) if t not in _STOP and t != "redacted"]
    index = Index(items)
    try:
        rows = index.fts(tokens)
    finally:
        index.close()
    exact = [i["id"] for i in items if i["name"] and re.search(r"(?<!\w)" + re.escape(i["name"].lower()) + r"(?!\w)", question)]
    context = state["selected"] if re.search(r"\b(this|these|selected)\b", question) or state["intent"] == "explain" else []
    scoped = list(dict.fromkeys([*context, *sorted(exact)]))
    if scoped and state["intent"] in ("explain", "cost"):
        return {"matches": scoped, "intent": "explain"}
    return {"matches": list(dict.fromkeys([*scoped, *rows])), "scope": scoped}


def _short(text: str, limit: int) -> str:
    return text[:limit] + "…" if len(text) > limit else text


def _intent(question: str) -> str:
    q = question.lower()
    if parse_compare(q):
        intent = "compare"
    elif re.search(r"\b(how many items|item count|count items)\b", q):
        intent = "count"
    elif parse_what(q) and not re.search(_NOT_WHAT, q):
        intent = "whatis"
    elif parse_keep(q) is not None:
        intent = "whatis"
    elif re.search(r"\b(remove|delete|get rid|clean ?up|prune|trim|declutter)\b|\bsave (me )?tokens?\b", q):
        intent = "remove"
    elif re.search(r"\b(explain|describe)\b", q):
        intent = "explain"
    elif re.search(r"\b(usage|used|unused|never)\b", q):
        intent = "unused" if re.search(r"\b(never|unused)\b", q) else "usage"
    elif re.search(r"\b(costs?|expensive|tokens?)\b", q):
        intent = "cost"
    elif re.search(r"\b(duplicates?|wrappers?|overlaps?)\b", q):
        intent = "pairs"
    elif re.search(r"\bfocus\b", q):
        intent = "focus"
    elif re.search(r"\b(this|these)\b", q):
        intent = "explain"
    else:
        intent = "search"
    return intent


def _route(state: ChatState) -> dict[str, Any]:
    prepared: ChatState = {**state, "intent": _intent(state["question"])}
    return {**prepared, **_retrieve(prepared), **_display(prepared)}


def _display(state: ChatState) -> dict[str, Any]:
    items = [{**i, **{key: _short(i[key], {"name": 96, "kind": 40}[key]) for key in ("name", "kind")}} for i in state["data"]["items"]]
    return {"data": {**state["data"], "items": items}}  # descriptions stay whole: answer.first_sentence cuts them at a sentence


def _response(headline: str, ids: list[str] | None = None, kind: str = "highlight", **parts: Any) -> dict[str, Any]:
    made = blocks(headline, **parts)  # every input was redacted on the way in (LocalChat.answer)
    actions = [{"kind": kind, "item_ids": ids}] if ids else []
    return {"response": {"answer": to_text(made), "blocks": made, "actions": actions, "mode": "local"}}


def _by_id(state: ChatState) -> dict[str, dict[str, Any]]:
    return {i["id"]: i for i in state["data"]["items"]}


def _count(state: ChatState) -> dict[str, Any]:
    return _response(f"The current scan contains {plural(len(state['data']['items']), 'Item')}.", follow_ups=ASK_NEXT)


def _cost(state: ChatState) -> dict[str, Any]:
    data = state["data"]
    if re.search(r"\b(total|on[ -]use)\b", state["question"].lower()):
        return _response("I rank what each Item costs every session.", next_="Ask for the top costs, or name an Item to see what it costs.")
    known = _known_costs(data)
    ranked = _ranked(data, known)
    unknown = len(data["items"]) - len(known)
    note = f"Plus {plural(unknown, 'Item')} with unknown cost, not counted as 0." if unknown else None
    if not ranked:
        return _response("Token costs were not measured in this scan.", note=note, follow_ups=ASK_NEXT)
    top = ranked[0]
    return _response(
        f"{top['name']} costs the most: {known[top['id']]:,} tokens every session.",
        [i["id"] for i in ranked[:5]],
        rows=[row(i, cost_value(data, i["id"])) for i in ranked[:5]],
        more=max(0, len(ranked) - 5),
        note=note,
        next_=f"Check whether you still use {top['name']}.",
        follow_ups=[f"Should I keep {top['name']}?", *ASK_NEXT],
    )


def _removal_value(s: Any, id_: str | None, known: dict[str, int], names: dict[str, str]) -> str:
    other = next((n for i, n in names.items() if i in s.item_ids and i != id_), "")
    why = {"remove_duplicate": f"Same job as {other}", "use_underlying": f"Only calls {other}", "remove_unused": "Not seen"}[s.kind]
    return f"{why}; {'saves ' + format(known[id_], ',') + ' tokens' if id_ in known else 'saving unknown'}"


def _remove(state: ChatState) -> dict[str, Any]:
    """Removable Items from suggest(), with one deduplicated saving. Moves are scope advice and name projects, so they are left out."""
    data = state["data"]
    known, items = _known_costs(data), _by_id(state)
    off = {i["id"] for i in data["items"] if i.get("disabled")}  # a switched-off plugin costs nothing now
    found: dict[Any, tuple[Any, str | None]] = {}
    for s in suggest(data):
        if s.kind in ("remove_duplicate", "use_underlying", "remove_unused") and not off & set(s.item_ids):
            found.setdefault(removes(s, known) or s.item_ids, (s, removes(s, known)))
    if not found:
        return _response("Nothing in this scan looks safe to remove.", follow_ups=ASK_NEXT)
    chosen = list(found.values())
    saved = [{"removes": id_, "tokens_saved": s.tokens_saved} for s, id_ in chosen]
    total, unknown = frees(saved, known), sum(id_ is None or id_ not in known for _, id_ in chosen)
    headline = (
        f"You could remove {len(chosen)}, saving about {total:,} tokens every session."
        if total
        else f"You could remove {plural(len(chosen), 'Item')}, but the saving is unknown."
    )
    caveat = "Unused rests on saved transcripts, which Claude Code deletes over time."
    shown = chosen[:5]
    names = {i: items[i]["name"] for s, _ in shown for i in s.item_ids}
    return _response(
        headline,
        [id_ or s.item_ids[0] for s, id_ in shown],
        rows=[row(items[id_ or s.item_ids[0]], _removal_value(s, id_, known, names)) for s, id_ in shown],
        more=len(chosen) - len(shown),
        note=f"Plus {plural(unknown, 'Item')} with an unknown saving, not counted as 0. {caveat}" if unknown else caveat,
        next_="Open one on the map before you decide.",
        follow_ups=[f"Should I keep {items[chosen[0][1] or chosen[0][0].item_ids[0]]['name']}?", *ASK_NEXT],
    )


def _pairs(state: ChatState) -> dict[str, Any]:
    data, scope = state["data"], set(state["scope"])
    found = [o for o in data["overlaps"] if o["verdict"] in ("duplicate", "wrapper") and (not scope or {o["a_id"], o["b_id"]} & scope)]
    if not found:
        return _response(
            "No known duplicates or wrappers for those Items." if scope else "No known duplicates or wrappers in this scan.",
            follow_ups=ASK_NEXT,
        )
    items = _by_id(state)
    shown = found[:5]
    ids = list(dict.fromkeys(id_ for o in shown for id_ in (o["a_id"], o["b_id"])))
    rows = [
        row(
            items[o["a_id"]],
            f"Wraps {items[o['b_id']]['name']}" if o["verdict"] == "wrapper" else f"Does the same job as {items[o['b_id']]['name']}",
        )
        for o in shown
    ]
    first = items[shown[0]["a_id"]]["name"]
    return _response(
        f"Found {plural(len(found), 'duplicate or wrapper pair')}, starting with {first}.",
        ids,
        rows=rows,
        more=len(found) - len(shown),
        next_="Open a pair on the map and choose which one to keep.",
        follow_ups=[f"Should I keep {first}?", *ASK_NEXT],
    )


def _usage(state: ChatState) -> dict[str, Any]:
    data, intent = state["data"], state["intent"]
    window = data.get("usage_window")
    if not window:
        return _response("Usage was not read in this scan.")
    if not window["files"]:
        return _response("No transcripts found.")
    items = _by_id(state)
    found = _never_used(data) if intent == "unused" else sorted(items.values(), key=lambda i: (i["name"], i["id"]))
    found = [i for i in found if not state["scope"] or i["id"] in state["scope"]]
    skipped = f" ({plural(window['skipped'], 'file')} skipped)" if window["skipped"] else ""
    note = f"Based on {plural(window['files'], 'saved transcript')}{skipped}. Old ones are deleted, so this is not proof an Item is unused."
    if not found:
        return _response(
            "None of those Items is recorded as never seen." if state["scope"] else f"Nothing here has been unused in {past(window)}.",
            note=note,
            follow_ups=ASK_NEXT,
        )
    usage = data.get("usage") or {}
    if intent == "unused":
        headline = f"{plural(len(found), 'Item')} not seen in {past(window)}, starting with {found[0]['name']}."
    else:
        headline = f"Usage across {past(window)}."
    unused = intent == "unused"
    return _response(
        headline,
        [i["id"] for i in found[:5]],
        rows=[row(i, cost_value(data, i["id"]) if unused else _usage_value(usage, i["id"])) for i in found[:5]],
        more=max(0, len(found) - 5),
        note=note,
        next_=f"Ask whether to keep {found[0]['name']}." if intent == "unused" else None,
        follow_ups=[f"Should I keep {found[0]['name']}?", *ASK_NEXT] if intent == "unused" else ASK_NEXT,
    )


def _usage_value(usage: dict[str, Any], id_: str) -> str:
    return plural(usage[id_]["count"], "use") if id_ in usage else "Usage unknown"


def _terms(question: str) -> str:
    return " ".join(t for t in re.findall(r"[^\W_]+", _strip(question)) if t not in _STOP)[:40] or question.strip()[:40]


def _not_found(name: str, follow_ups: list[str]) -> dict[str, Any]:
    return _response(
        f'I could not find "{name}" in this scan.',
        next_="Check the spelling, or describe what it does.",
        follow_ups=follow_ups,
    )


def _items_answer(state: ChatState, *, explain: bool = False, kind: str = "highlight") -> dict[str, Any]:
    data, items = state["data"], _by_id(state)
    ids = state["matches"][:5]
    if not ids:
        return _not_found(_terms(state["question"]), ASK_NEXT)
    cards = [card(data, items[i]) for i in ids[:2]] if explain else []
    rows = [row(items[i], cost_value(data, i)) for i in ids[0 if not explain else 2 :]]
    first = items[ids[0]]["name"]
    headline = (
        what_line(cards[0]) if explain else f"{first} is the closest match." if len(state["matches"]) > 1 else f"One Item matches: {first}."
    )
    return _response(
        headline,
        ids,
        kind,
        cards=cards,
        rows=rows,
        more=max(0, len(state["matches"]) - 5),
        next_="Click a name to see it on the map.",
        follow_ups=[f"Should I keep {first}?", *ASK_NEXT],
    )


def _search(state: ChatState) -> dict[str, Any]:
    return _items_answer(state)


def _explain(state: ChatState) -> dict[str, Any]:
    return _items_answer(state, explain=True)


def _resolve(state: ChatState, name: str) -> dict[str, Any] | list[dict[str, Any]] | None:
    """The Item for a name: None when nothing matches, a list of candidates when several are equally close, else the Item (with `took`)."""
    hits = state["index"].query(name)
    if not hits:
        return None
    items = _by_id(state)
    weak = re.compile(r"name|close to").match
    if weak(hits[0]["why"]):
        return items[hits[0]["id"]]
    tier = hits[0]["why"].partition(" ")[0]
    close = [items[h["id"]] for h in hits if h["why"].partition(" ")[0] == tier]
    return close[:3] if len(close) > 1 else {**items[hits[0]["id"]], "took": True}


def _ambiguous(candidates: list[dict[str, Any]], ask: Callable[[dict[str, Any]], str]) -> dict[str, Any]:
    return _response("Which one did you mean?", did_you_mean=[{"id": c["id"], "name": c["name"], "ask": ask(c)} for c in candidates])


def _compare(state: ChatState) -> dict[str, Any]:
    first, second = parse_compare(state["question"]) or ("", "")  # pragma: no mutate (unreachable fallback: routing saw a match)
    a, b = _resolve(state, first), _resolve(state, second)
    if not first and state["selected"]:  # "how does it compare to X" means the selected Item
        a = _by_id(state)[state["selected"][0]]
    typed = [first, second]
    shown = [f["name"] if isinstance(f, dict) else typed[n] for n, f in enumerate((a, b))]
    for n, found in enumerate((a, b)):
        if isinstance(found, list):  # the other name is the resolved Item, or what was typed

            def ask(c: dict[str, Any], n: int = n) -> str:
                return f"Compare {c['name']} and {shown[1]}" if n == 0 else f"Compare {shown[0]} and {c['name']}"

            return _ambiguous(found, ask)
    if not isinstance(a, dict) or (isinstance(b, dict) and a["id"] == b["id"]):
        return _response(
            "I could not tell which two Items you mean.",
            next_="Name both Items, for example: compare ponytail to chisel.",
            follow_ups=ASK_NEXT,
        )
    data = state["data"]
    if b is None:
        return _response(
            f'I could not find "{second}" to compare with. Here is {a["name"]}.',
            [a["id"]],
            cards=[card(data, a)],
            next_="Check the spelling of the second name.",
            follow_ups=[f"Should I keep {a['name']}?"],
        )
    assert isinstance(b, dict)  # a list returned above
    took = [f'"{n}" to mean {i["name"]}' for n, i in ((first, a), (second, b)) if i.get("took")]
    overlap = _overlap_between(data, a["id"], b["id"])
    names = {a["id"]: a["name"], b["id"]: b["name"]}
    return _response(
        _compare_headline(overlap, a, b, names),
        [a["id"], b["id"]],
        cards=[card(data, a), card(data, b)],
        compare=comparison(data, a, b),
        note=f"I took {' and '.join(took)}." if took else None,
        follow_ups=[f"Should I keep {a['name']}?", f"Should I keep {b['name']}?"],
    )


def _overlap_between(data: dict[str, Any], a: str, b: str) -> dict[str, Any] | None:
    return next((o for o in data["overlaps"] if {o["a_id"], o["b_id"]} == {a, b}), None)


def _compare_headline(overlap: dict[str, Any] | None, a: dict[str, Any], b: dict[str, Any], names: dict[str, str]) -> str:
    if overlap and overlap["verdict"] == "duplicate":
        return f"{a['name']} and {b['name']} do the same job; you could keep one."
    if overlap and overlap["verdict"] == "wrapper":
        return f"{names[overlap['a_id']]} only calls {names[overlap['b_id']]}; you could keep the wrapped one."
    if overlap and overlap["verdict"] == "overlap":
        return f"{a['name']} and {b['name']} partly overlap; keep both only if you need the difference."
    return f"{a['name']} and {b['name']} do different jobs."


def _whatis(state: ChatState) -> dict[str, Any]:
    keep = parse_keep(state["question"])
    parsed = keep if keep is not None else parse_what(state["question"])
    name = parsed or ""  # pragma: no mutate (unreachable fallback: routing saw a match)
    found: dict[str, Any] | list[dict[str, Any]] | None
    if name in ("this", "it", "that"):  # the selected Item, or nothing
        found = _by_id(state)[state["selected"][0]] if state["selected"] else None
    else:
        found = _resolve(state, name)
    if found is None:
        return _not_found(name, [f"What do I have for {name}?", *ASK_NEXT])
    if isinstance(found, list):
        return _ambiguous(found, lambda c: f"{'Should I keep' if keep is not None else 'What is'} {c['name']}?")
    c = card(state["data"], found)
    lead = f'I took "{name}" to mean {found["name"]}. ' if found.get("took") else ""
    headline = f"{c['name']}: {c['verdict']['label']}. {c['verdict']['why']}." if keep is not None else what_line(c)
    return _response(
        lead + headline,
        [found["id"]],
        cards=[c],
        next_=f"Open {c['name']} on the map to see what it connects to.",
        follow_ups=[f"Should I keep {c['name']}?" if keep is None else f"What is {c['name']}?", *ASK_NEXT],
    )


def _focus(state: ChatState) -> dict[str, Any]:
    return _items_answer(state, kind="focus")


def _answer_node(state: ChatState) -> str:
    return state["intent"]


def _graph() -> Any:
    graph = StateGraph(ChatState)
    graph.add_node("route", _route)
    operations = {
        "search": _search,
        "explain": _explain,
        "focus": _focus,
        "top_costs": _cost,
        "pairs": _pairs,
        "usage": _usage,
        "remove": _remove,
        "count": _count,
        "compare": _compare,
        "whatis": _whatis,
    }
    for name, operation in operations.items():
        graph.add_node(name, operation)
        graph.add_edge(name, END)
    graph.add_edge(START, "route")
    graph.add_conditional_edges(
        "route",
        _answer_node,
        {
            "search": "search",
            "explain": "explain",
            "focus": "focus",
            "cost": "top_costs",
            "pairs": "pairs",
            "usage": "usage",
            "unused": "usage",
            "remove": "remove",
            "count": "count",
            "compare": "compare",
            "whatis": "whatis",
        },
    )
    return graph.compile()


class LocalChat:
    def __init__(self) -> None:
        self._cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self._workflow = _graph()

    def answer(
        self, data: dict[str, Any], question: str, selected: list[str], index_for: Callable[[list[dict[str, Any]]], Index]
    ) -> dict[str, Any]:
        clean: dict[str, Any] = {
            "items": [
                {
                    "id": i["id"],
                    "disabled": bool(i.get("disabled")),
                    **{key: redact(i[key]) for key in ("name", "kind", "description")},
                }
                for i in data["items"]
            ]
        }
        ids = {i["id"] for i in clean["items"]}
        clean["costs"] = {k: v for k, v in (data.get("costs") or {}).items() if k in ids}
        clean["overlaps"] = [
            {key: redact(o[key]) if key == "reason" else o[key] for key in ("a_id", "b_id", "verdict", "reason")}
            for o in data.get("overlaps") or []
            if o["a_id"] in ids and o["b_id"] in ids
        ]
        question = redact(question)
        clean["usage"], clean["usage_window"] = data.get("usage"), data.get("usage_window")
        clean["clusters"] = [{"item_ids": c["item_ids"]} for c in data.get("clusters") or []]
        index: Index | None = None  # pragma: no mutate (equivalent: unused unless set below)
        if _intent(question) in ("compare", "whatis"):
            index = index_for(data["items"])
            # meaning-based matches appear once the vectors are ready, so that moment must not reuse an older answer
            clean["vectors_ready"] = index.vectors is not None  # pragma: no mutate (equivalent: only needs to differ before and after)
        key = hashlib.sha256(json.dumps([question, selected, clean], sort_keys=True).encode()).hexdigest()
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return {**self._cache[key], "cached": True}
            # LangGraph otherwise honours ambient LangSmith tracing, which could upload the local state.
            with tracing_context(enabled=False):
                response: dict[str, Any] = self._workflow.invoke(
                    {"question": question, "selected": selected, "data": clean, "index": index}
                )["response"]
            self._cache[key] = response
            if len(self._cache) > 128:
                del self._cache[next(iter(self._cache))]
            return {**response, "cached": False}
