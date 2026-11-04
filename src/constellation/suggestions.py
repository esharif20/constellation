import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from .redact import redact
from .report import _known_costs, _names, _never_used


@dataclass(frozen=True)
class Suggestion:
    id: str  # content-derived, so a decision still applies after a re-scan
    kind: Literal["remove_duplicate", "use_underlying", "remove_unused"]
    item_ids: tuple[str, ...]
    reason: str  # plain English, redacted
    tokens_saved: int | None  # None = unknown, never 0


def _make(
    kind: Literal["remove_duplicate", "use_underlying", "remove_unused"], item_ids: tuple[str, ...], reason: str, saved: int | None
) -> Suggestion:
    digest = hashlib.sha256((kind + "\0" + "\0".join(item_ids)).encode()).hexdigest()[:12]
    return Suggestion(digest, kind, item_ids, redact(reason), saved)


def _duplicates(data: dict[str, Any]) -> list[Suggestion]:
    names, known = _names(data), _known_costs(data)
    found = []
    for o in data.get("overlaps") or []:
        if o["verdict"] != "duplicate":
            continue
        ids = tuple(sorted((o["a_id"], o["b_id"])))
        a, b = (names.get(i, i) for i in ids)
        saved = min(known[i] for i in ids) if all(i in known for i in ids) else None
        found.append(_make("remove_duplicate", ids, f"Remove one of these two: {a} and {b}. {o['reason']}", saved))
    return found


def _wrappers(data: dict[str, Any]) -> list[Suggestion]:
    names, known = _names(data), _known_costs(data)
    found = []
    for o in data.get("overlaps") or []:
        if o["verdict"] != "wrapper":  # a_id is the wrapper, b_id what it calls
            continue
        wrapper, wrapped = names.get(o["a_id"], o["a_id"]), names.get(o["b_id"], o["b_id"])
        reason = f"{wrapper} only calls {wrapped}; consider using {wrapped} directly. {o['reason']}"
        found.append(_make("use_underlying", (o["a_id"], o["b_id"]), reason, known.get(o["a_id"])))
    return found


def _unused(data: dict[str, Any]) -> list[Suggestion]:
    names, known = _names(data), _known_costs(data)
    found = []
    for item in _never_used(data):
        id_ = item["id"]
        window = data["usage_window"]
        reason = f"{names[id_]} was never seen in {window['files']} transcripts ({window['first']} to {window['last']})."
        if id_ in known:
            reason += f" It costs {known[id_]} always-on tokens every session."
        found.append(_make("remove_unused", (id_,), reason, known.get(id_)))
    return found


GENERATORS: list[Callable[[dict[str, Any]], list[Suggestion]]] = [_duplicates, _wrappers, _unused]


def suggest(data: dict[str, Any]) -> list[Suggestion]:
    """Known savings first (largest first), then unknown; ties by Item ids, so the same scan always gives the same order."""
    every = [s for generate in GENERATORS for s in generate(data)]
    return sorted(every, key=lambda s: (s.tokens_saved is None, -(s.tokens_saved or 0), s.item_ids))
