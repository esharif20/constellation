"""Label helpers for the scan graph: the free cache plan, one model call per Item, and the cache flush."""

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .costs import cache_key, load_cache, save_cache
from .models import LLM, Item
from .redact import ProviderError


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


def label_plan(items: list[Item], known: Iterable[str], cache_path: Path | None, salt: str) -> tuple[dict[str, str], list[Item]]:
    """Free, local: (labels already in the cache, Items still to label)."""
    known = tuple(known)
    cache = load_cache(cache_path or DEFAULT_CACHE)
    labels = {
        i.id: text for i in items if (text := _clean(str(cache.get(cache_key(_prompt(i), known, salt), ""))))
    }  # cleaned again: the file is editable
    return labels, [i for i in items if i.id not in labels]


def label_one(item: Item, llm: LLM) -> dict[str, Any]:
    """One model call: a state update with either `labels` or `warnings`."""
    try:
        text = _clean(llm(_prompt(item)))
    except ProviderError as error:
        return {"warnings": [f"{FAILED_PREFIX} '{item.name}': {error}"]}
    if not text:
        return {"warnings": [f"{FAILED_PREFIX} '{item.name}': empty reply"]}
    return {"labels": {item.id: text}}


def label_flush(cache_path: Path | None, fresh: dict[str, str]) -> list[str]:
    """Cache the successful labels (`fresh`: cache key -> label); an unwritable cache is a warning."""
    if not fresh:
        return []
    path = cache_path or DEFAULT_CACHE
    try:
        save_cache(path, load_cache(path) | fresh)
    except OSError as error:  # the labels are paid for and returned; only the next scan loses them
        return [f"could not save the label cache: {error}"]
    return []
