"""Label every Item with the LLM, one parallel LangGraph branch per Item."""

import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from .models import LLM, Item
from .redact import ProviderError


class _State(TypedDict, total=False):  # only `items` goes in; the reducers start `labels` and `warnings` empty
    items: list[Item]
    # Reducer: parallel branches each return one {id: label}; operator.or_ merges the dicts.
    labels: Annotated[dict[str, str], operator.or_]
    # Second reducer: branches that fail each return a one-line list, and operator.add concatenates them.
    warnings: Annotated[list[str], operator.add]


class _Branch(TypedDict):
    item: Item


def _prompt(item: Item) -> str:
    ask = "Reply with only a 2 to 4 word topic for what this item is for, like 'code review' or 'web research'."
    return f"Name: {item.name}\nDescription: {item.description}\n\n{ask}"


MAX_LABEL = 60
FAILED_PREFIX = "could not label"  # the CLI looks for this prefix to report the first failure
# shortcut: a fixed cap of 4 simultaneous model calls keeps a 77-Item scan under typical rate limits; raise it when throughput matters.
MAX_CONCURRENCY = 4


def _clean(reply: str) -> str:
    """One short line: the model's reply is untrusted text (a skill description can try to steer it) and is stored and shown later."""
    lines = [line.strip() for line in reply.splitlines() if line.strip()]
    return lines[0][:MAX_LABEL] if lines else ""


def classify(items: list[Item], llm: LLM) -> tuple[dict[str, str], list[str]]:

    def fan_out(state: _State) -> list[Send]:
        return [Send("label", {"item": item}) for item in state["items"]]

    def label(state: _Branch) -> dict[str, Any]:
        item = state["item"]
        try:
            text = _clean(llm(_prompt(item)))
        except ProviderError as error:
            return {"warnings": [f"{FAILED_PREFIX} '{item.name}': {error}"]}
        if not text:
            return {"warnings": [f"{FAILED_PREFIX} '{item.name}': empty reply"]}
        return {"labels": {item.id: text}}

    graph = StateGraph(_State)
    graph.add_node(label)  # the node is named after the function; fan_out sends to "label"
    graph.add_conditional_edges(START, fan_out)
    graph.add_edge("label", END)
    result = graph.compile().invoke({"items": items}, config={"max_concurrency": MAX_CONCURRENCY})
    labels: dict[str, str] = result["labels"]
    warnings: list[str] = result["warnings"]
    return labels, warnings
