"""Label every Item with the LLM, one parallel LangGraph branch per Item."""

import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from .models import LLM, Item


class _State(TypedDict):
    items: list[Item]
    # Reducer: parallel branches each return one {id: label}; operator.or_ merges the dicts.
    labels: Annotated[dict[str, str], operator.or_]


class _Branch(TypedDict):
    item: Item


def _prompt(item: Item) -> str:
    return f"Name: {item.name}\nDescription: {item.description}\n\nReply with a short free-text label for this item's purpose."


def classify(items: list[Item], llm: LLM) -> dict[str, str]:

    def fan_out(state: _State) -> list[Send]:
        return [Send("label", {"item": item}) for item in state["items"]]

    def label(state: _Branch) -> dict[str, dict[str, str]]:
        item = state["item"]
        return {"labels": {item.id: llm(_prompt(item)).strip()}}

    graph = StateGraph(_State)
    graph.add_node("label", label)
    graph.add_conditional_edges(START, fan_out, ["label"])
    graph.add_edge("label", END)
    labels: dict[str, str] = graph.compile().invoke({"items": items, "labels": {}})["labels"]
    return labels
