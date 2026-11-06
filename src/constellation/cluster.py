"""Embed each Item's name and description as unit vectors for grouping.py (clusters) and the Overlap candidates."""

import math

from .models import Embedder, Item

# Raw embedding cosines are squeezed together, so with enough Items the mean vector is subtracted first (docs/ideas/clustering-quality.md).
MIN_ITEMS_TO_CENTRE = 10  # the mean of two or three vectors is mostly noise


def _unit(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector] if norm else vector  # a zero vector stays zero and matches nothing


def _centre(vectors: list[list[float]]) -> list[list[float]]:
    mean = [sum(column) / len(vectors) for column in zip(*vectors, strict=True)]
    return [_unit([x - mean[k] for k, x in enumerate(v)]) for v in vectors]


def dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))  # strict: embeddings of mixed dimensions are an error, not a silent truncation


def item_vectors(items: list[Item], embed: Embedder) -> tuple[dict[str, list[float]], bool]:
    """Unit vectors by Item id, mean-centred when there are enough Items, and whether they were centred. Embeds name and
    description only; scan() embeds once and shares the result with the clusters and the Overlap candidates."""
    items = sorted(items, key=lambda i: i.id)  # greedy clustering depends on order, so fix the order
    # a hook's description is a shell command, which clusters by shape rather than meaning, so hooks are embedded by name (event:matcher)
    vectors = [_unit(v) for v in embed([i.name if i.kind == "hook" else f"{i.name}: {i.description}" for i in items])]
    if len({len(v) for v in vectors}) > 1:
        raise ValueError("embeddings have different dimensions")  # an error, not a silent truncation
    centred = len(vectors) >= MIN_ITEMS_TO_CENTRE
    if centred:
        vectors = _centre(vectors)
    return {i.id: v for i, v in zip(items, vectors, strict=True)}, centred
