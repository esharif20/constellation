"""Free local answers over saved metadata; no provider or persisted conversation."""

import hashlib
import json
import re
import sqlite3
import threading
from collections import OrderedDict
from contextlib import closing
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context

from .brief import brief
from .redact import redact
from .report import _never_used, _usage_note

_STOP = set("what can help me to do a an the with for please find search show highlight focus filter on items item".split())


class ChatState(TypedDict):
    question: str
    selected: list[str]
    data: dict[str, Any]
    matches: list[str]
    response: dict[str, Any]
    intent: str
    scope: list[str]


def _retrieve(state: ChatState) -> dict[str, Any]:
    question, items = state["question"].lower().strip(), state["data"]["items"]
    question = re.sub(r"^(?:show(?: me)? )?everything that touches\s+", "", question)
    tokens = [t for t in re.findall(r"[^\W_]+", question) if t not in _STOP and t != "redacted"]
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.execute(
            "CREATE VIRTUAL TABLE metadata USING fts5(id UNINDEXED, name, description, kind)"  # pragma: no mutate (SQL case)
        )
        connection.executemany(
            "INSERT INTO metadata VALUES (?, ?, ?, ?)",  # pragma: no mutate (SQL case)
            [(i["id"], i["name"], i["description"], i["kind"]) for i in items],
        )
        rows = (
            connection.execute(
                "SELECT id FROM metadata WHERE metadata MATCH ? ORDER BY bm25(metadata), id LIMIT 8",  # pragma: no mutate (SQL case)
                (" OR ".join('"' + t + '"' for t in tokens),),
            ).fetchall()
            if tokens
            else []
        )
    exact = [i["id"] for i in items if i["name"] and re.search(r"(?<!\w)" + re.escape(i["name"].lower()) + r"(?!\w)", question)]
    context = state["selected"] if re.search(r"\b(this|these|selected)\b", question) or state["intent"] == "explain" else []
    scoped = list(dict.fromkeys([*context, *sorted(exact)]))
    if scoped and state["intent"] in ("explain", "cost"):
        return {"matches": scoped, "intent": "explain"}
    return {"matches": list(dict.fromkeys([*scoped, *(row[0] for row in rows)])), "scope": scoped}


def _short(text: str, limit: int) -> str:
    return text[:limit] + "…" if len(text) > limit else text


def _intent(question: str) -> str:
    q = question.lower()
    if re.search(r"\b(how many items|item count|count items)\b", q):
        intent = "count"
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
    data = state["data"]
    data = {
        **data,
        "items": [
            {
                "id": i["id"],
                **{key: _short(i[key], {"name": 96, "kind": 40, "description": 160}[key]) for key in ("name", "kind", "description")},
            }
            for i in data["items"]
        ],
    }
    return {"data": data}


def _response(answer: str, ids: list[str] | None = None, kind: str = "highlight") -> dict[str, Any]:
    return {"response": {"answer": redact(answer), "actions": [{"kind": kind, "item_ids": ids}] if ids else [], "mode": "local"}}


def _count(state: ChatState) -> dict[str, Any]:
    return _response(f"The current scan contains {len(state['data']['items'])} Items.")


def _cost(state: ChatState) -> dict[str, Any]:
    data = state["data"]
    items = {i["id"]: i for i in data["items"]}
    if re.search(r"\b(total|on[ -]use)\b", state["question"].lower()):
        return _response(
            "Local chat ranks always-on Context costs. Ask for top costs, or name/select an Item to see its always-on and on-use costs."
        )
    summary = brief(data)["cost"]
    rows = summary["rows"]
    ids = [r["item_ids"][0] for r in rows]
    lines = [f"- {items[r['item_ids'][0]]['name']}: {r['tokens_saved']:,} tokens" for r in rows]
    answer = "Highest always-on Context costs:\n" + "\n".join(lines) if lines else "Token costs were not measured in this scan."
    answer += f"\n{summary['unknown']} Items have unknown cost; unknown is never counted as 0."
    return _response(answer, ids)


def _pairs(state: ChatState) -> dict[str, Any]:
    data = state["data"]
    pair_data = {
        **data,
        "overlaps": [o for o in data["overlaps"] if not state["scope"] or {o["a_id"], o["b_id"]} & set(state["scope"])],
    }
    rows = brief(pair_data)["pairs"]["rows"]
    ids = list(dict.fromkeys(id_ for r in rows for id_ in r["item_ids"]))
    answer = (
        "Known duplicate/wrapper Overlaps:\n" + "\n".join(f"- {r['reason']}" for r in rows)
        if rows
        else "No known duplicate/wrapper Overlaps for the requested Items."
        if state["scope"]
        else "No known duplicate/wrapper Overlaps in this scan."
    )
    return _response(answer, ids)


def _usage(state: ChatState) -> dict[str, Any]:
    data, intent = state["data"], state["intent"]
    items = {i["id"]: i for i in data["items"]}
    window = data.get("usage_window")
    ids = []  # pragma: no mutate (equivalent: None and [] both suppress graph actions)
    answer = _usage_note(data)
    if window and window["files"]:
        found = _never_used(data) if intent == "unused" else sorted(items.values(), key=lambda i: (i["name"], i["id"]))
        found = [i for i in found if not state["scope"] or i["id"] in state["scope"]]
        ids = [i["id"] for i in found[:5]]
        lines = [f"- {items[id_]['name']}" for id_ in ids]
        if intent == "usage":
            usage = data.get("usage") or {}
            lines = [f"- {items[id_]['name']}: {str(usage[id_]['count']) + ' uses' if id_ in usage else 'usage unknown'}" for id_ in ids]
        heading = "Never seen in the scanned transcripts:" if intent == "unused" else "Recorded usage:"
        empty = "None of the requested Items are recorded as never seen." if state["scope"] else "No Items were never seen in this scan."
        answer = (heading + "\n" + "\n".join(lines) if lines else empty) + "\n" + answer
    return _response(answer, ids)


def _items_answer(state: ChatState, *, explain: bool = False, kind: str = "highlight") -> dict[str, Any]:
    data = state["data"]
    items = {i["id"]: i for i in data["items"]}
    ids = state["matches"][:5]
    lines = [f"- {items[id_]['name']} ({items[id_]['kind']}): {items[id_]['description']}" for id_ in ids]
    if explain:
        for n, id_ in enumerate(ids):
            cost = (data.get("costs") or {}).get(id_) or {}
            values = [f"{cost[k]:,} tokens" if cost.get(k) is not None else "unknown" for k in ("always_on", "on_use")]
            lines[n] += f"\n  Always-on: {values[0]}; on-use: {values[1]}."
    heading = "Item details:" if explain else "Matching Items:"
    answer = heading + "\n" + "\n".join(lines) if lines else "No matching Items found. Try an Item name or a word from its description."
    if len(state["matches"]) > 5:
        answer += "\nMore matches omitted; narrow your question."
    return _response(answer, ids, kind)


def _search(state: ChatState) -> dict[str, Any]:
    return _items_answer(state)


def _explain(state: ChatState) -> dict[str, Any]:
    return _items_answer(state, explain=True)


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
        "count": _count,
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
            "count": "count",
        },
    )
    return graph.compile()


class LocalChat:
    def __init__(self) -> None:
        self._cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self._workflow = _graph()

    def answer(self, data: dict[str, Any], question: str, selected: list[str]) -> dict[str, Any]:
        clean: dict[str, Any] = {
            "items": [
                {
                    "id": i["id"],
                    **{key: redact(i[key]) for key in ("name", "kind", "description")},
                }
                for i in data["items"]
            ]
        }
        ids = {i["id"] for i in clean["items"]}
        clean["costs"] = {k: v for k, v in (data.get("costs") or {}).items() if k in ids}
        clean["overlaps"] = [
            {key: _short(redact(o[key]), 240) if key == "reason" else o[key] for key in ("a_id", "b_id", "verdict", "reason")}
            for o in data.get("overlaps") or []
            if o["a_id"] in ids and o["b_id"] in ids
        ]
        question = redact(question)
        if _intent(question) in ("usage", "unused"):
            clean["usage"] = data.get("usage")
            clean["usage_window"] = data.get("usage_window")
        key = hashlib.sha256(json.dumps([question, selected, clean], sort_keys=True).encode()).hexdigest()
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return {**self._cache[key], "cached": True}
            # LangGraph otherwise honours ambient LangSmith tracing, which could upload the local state.
            with tracing_context(enabled=False):
                response: dict[str, Any] = self._workflow.invoke({"question": question, "selected": selected, "data": clean})["response"]
            self._cache[key] = response
            if len(self._cache) > 128:
                del self._cache[next(iter(self._cache))]
            return {**response, "cached": False}
