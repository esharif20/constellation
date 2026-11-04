"""Label every Item with the LLM, one parallel LangGraph branch per Item, skipping Items whose label is cached."""

import operator
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from .costs import cache_key, load_cache, save_cache
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


DEFAULT_CACHE = Path.home() / ".cache" / "constellation" / "labels.json"
MAX_LABEL = 60
FAILED_PREFIX = "could not label"  # the CLI looks for this prefix to report the first failure
# shortcut: a fixed cap of 4 simultaneous model calls keeps a 77-Item scan under typical rate limits; raise it when throughput matters.
MAX_CONCURRENCY = 4


def _clean(reply: str) -> str:
    """One short line: the model's reply is untrusted text (a skill description can try to steer it) and is stored and shown later."""
    lines = [line.strip() for line in reply.splitlines() if line.strip()]
    return lines[0][:MAX_LABEL] if lines else ""


def classify(
    items: list[Item], llm: LLM, known: Iterable[str] = (), cache_path: Path | None = None, salt: str = ""
) -> tuple[dict[str, str], list[str]]:
    """`llm` must be the guarded one. Labels are cached by the hash of the redacted prompt, so a changed Item or prompt is
    labelled again; `known` are the secrets and `salt` the model id (see cache_key)."""
    known = tuple(known)
    path = cache_path or DEFAULT_CACHE
    cache = load_cache(path)
    keys = {i.id: cache_key(_prompt(i), known, salt) for i in items}
    labels = {i.id: text for i in items if (text := _clean(str(cache.get(keys[i.id], ""))))}  # cleaned again: the file is editable
    todo = [i for i in items if i.id not in labels]
    if not todo:
        return labels, []

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
    result = graph.compile().invoke({"items": todo}, config={"max_concurrency": MAX_CONCURRENCY})
    fresh: dict[str, str] = result["labels"]
    warnings: list[str] = result["warnings"]
    if fresh:  # only successful labels are cached
        try:
            save_cache(path, cache | {keys[id_]: text for id_, text in fresh.items()})
        except OSError as error:  # the labels are paid for and returned; only the next scan loses them
            warnings.append(f"could not save the label cache: {error}")
    return labels | fresh, warnings
