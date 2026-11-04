"""Context cost: what each Item adds to the model's context, counted exactly and cached by content hash."""

import hashlib
import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .models import Cost, Item, TokenCounter
from .redact import ProviderError, redact

DEFAULT_CACHE = Path.home() / ".cache" / "constellation" / "token-counts.json"


def cache_key(text: str, known: Iterable[str], salt: str = "") -> str:
    """Keyed on what a provider would see, so no secret reaches the file. `salt` (a model id) keeps answers from another model apart;
    empty leaves the plain hash, so existing cache files stay valid."""
    return hashlib.sha256((f"{salt}\0" if salt else "").encode() + redact(text, known).encode()).hexdigest()


def load_cache(path: Path) -> dict[str, Any]:
    """A JSON cache file keyed by content hash; shared with the Overlap verdict cache."""
    try:
        cache = json.loads(path.read_text())
    except (OSError, ValueError):  # missing or corrupt: start over, the entries are re-fetchable
        return {}
    return cache if isinstance(cache, dict) else {}


def save_cache(path: Path, cache: dict[str, Any]) -> None:
    """Written with mode 0600 (it is derived from the user's setup), creating the directory if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as file:
        file.write(json.dumps(cache))


def _texts(item: Item, body: str | None) -> tuple[str | None, str | None]:
    """(always-on text, on-use text). A hook's output exists only at runtime, so it is never guessed."""
    if item.kind == "hook":
        return None, None
    return f"{item.name}: {item.description}", body


def _fill(cache: dict[str, Any], texts: Iterable[str], counter: TokenCounter | None, known: tuple[str, ...], path: Path) -> list[str]:
    """Counts the texts the cache lacks (one batch) into `cache` and saves it. `counter` must be the guarded one."""
    missing = {cache_key(t, known): t for t in texts if cache_key(t, known) not in cache}
    warnings: list[str] = []
    if missing and counter:
        try:
            cache |= dict(zip(missing, counter(list(missing.values())), strict=True))
        except ProviderError as error:
            warnings.append(f"could not count context cost: {error}")
        else:
            try:
                save_cache(path, cache)
            except OSError as error:  # the counts are paid for and kept in memory; only the next scan loses them
                warnings.append(f"could not save the token-count cache: {error}")
    return warnings


def count_texts(
    texts: dict[str, str], counter: TokenCounter | None, known: Iterable[str], cache_path: Path | None = None
) -> tuple[dict[str, int | None], list[str]]:
    """Tokens per key, from the same cache and guarded counter as `measure`; None where uncounted (no counter, or the count failed)."""
    known = tuple(known)
    cache = load_cache(cache_path or DEFAULT_CACHE)
    warnings = _fill(cache, texts.values(), counter, known, cache_path or DEFAULT_CACHE)
    return {k: cache.get(cache_key(t, known)) for k, t in texts.items()}, warnings


def measure(
    items: Iterable[Item], bodies: dict[str, str], counter: TokenCounter | None, known: Iterable[str], cache_path: Path | None = None
) -> tuple[dict[str, Cost], list[str]]:
    """`counter` must be the guarded one: it redacts what it is given, and turns a provider failure into a ProviderError.
    With no counter (offline) only what is already cached is reported; the rest is unknown."""
    # shortcut: the cache key ignores the model, so switching counting models needs the cache file deleted.
    path = cache_path or DEFAULT_CACHE
    known = tuple(known)
    pairs = {i.id: _texts(i, bodies.get(i.id)) for i in items}
    cache = load_cache(path)
    warnings = _fill(cache, (t for pair in pairs.values() for t in pair if t is not None), counter, known, path)
    counted = {id_: [None if t is None else cache.get(cache_key(t, known)) for t in pair] for id_, pair in pairs.items()}
    return {id_: Cost(always_on, on_use) for id_, (always_on, on_use) in counted.items()}, warnings
