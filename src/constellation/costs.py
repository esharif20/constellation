"""Context cost: what each Item adds to the model's context, counted exactly and cached by content hash."""

import hashlib
import json
import os
from collections.abc import Iterable
from pathlib import Path

from .models import Cost, Item, TokenCounter
from .redact import ProviderError, redact

DEFAULT_CACHE = Path.home() / ".cache" / "constellation" / "token-counts.json"


def _key(text: str, known: Iterable[str]) -> str:
    return hashlib.sha256(redact(text, known).encode()).hexdigest()  # keyed on what a provider would see, so no secret reaches the file


def _load(path: Path) -> dict[str, int]:
    try:
        cache: dict[str, int] = json.loads(path.read_text())
        return cache
    except (OSError, ValueError):  # missing or corrupt: start over, the counts are re-fetchable
        return {}


def _save(path: Path, cache: dict[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as file:
        file.write(json.dumps(cache))


def _texts(item: Item, body: str | None) -> tuple[str | None, str | None]:
    """(always-on text, on-use text). A hook's output exists only at runtime, so it is never guessed."""
    if item.kind == "hook":
        return None, None
    return f"{item.name}: {item.description}", body


def measure(
    items: Iterable[Item], bodies: dict[str, str], counter: TokenCounter, known: Iterable[str], cache_path: Path | None = None
) -> tuple[dict[str, Cost], list[str]]:
    """`counter` must be the guarded one: it redacts what it is given, and turns a provider failure into a ProviderError."""
    # shortcut: the cache key ignores the model, so switching counting models needs the cache file deleted.
    path = cache_path or DEFAULT_CACHE
    known = tuple(known)
    pairs = {i.id: _texts(i, bodies.get(i.id)) for i in items}
    cache = _load(path)
    missing = {_key(t, known): t for pair in pairs.values() for t in pair if t is not None and _key(t, known) not in cache}
    warnings: list[str] = []
    if missing:
        try:
            cache |= dict(zip(missing, counter(list(missing.values())), strict=True))
            _save(path, cache)
        except ProviderError as error:
            warnings.append(f"could not count context cost: {error}")
    counted = {id_: [None if t is None else cache.get(_key(t, known)) for t in pair] for id_, pair in pairs.items()}
    return {id_: Cost(always_on, on_use) for id_, (always_on, on_use) in counted.items()}, warnings
