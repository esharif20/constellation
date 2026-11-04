"""Group Items by meaning: embed each Item's label and text, then join vectors that point the same way."""

import math
from dataclasses import dataclass, field
from operator import add

from .models import Cluster, Embedder, Item

# Raw embedding cosines are squeezed together (eval F1 0.33 at best), so with enough Items the mean vector is subtracted first
# (eval F1 0.67). Centred cosines spread from -1 to 1, so they need a different threshold. See docs/ideas/clustering-quality.md.
# shortcut: both defaults come from the 30-item synthetic eval and one real scan (255 Items); retune on more setups.
MIN_ITEMS_TO_CENTRE = 10  # the mean of two or three vectors is mostly noise
RAW_THRESHOLD = 0.75
CENTRED_THRESHOLD = 0.2


def _unit(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector] if norm else vector  # a zero vector stays zero and matches nothing


def _centre(vectors: list[list[float]]) -> list[list[float]]:
    mean = [sum(column) / len(vectors) for column in zip(*vectors, strict=True)]
    return [_unit([x - mean[k] for k, x in enumerate(v)]) for v in vectors]


def dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))  # strict: embeddings of mixed dimensions are an error, not a silent truncation


@dataclass
class _Group:
    total: list[float]  # sum of the members' unit vectors; its direction is the cluster centre
    members: list[int] = field(default_factory=list)


def item_vectors(items: list[Item], embed: Embedder) -> tuple[dict[str, list[float]], bool]:
    """Unit vectors by Item id, mean-centred when there are enough Items, and whether they were centred. Embeds name and
    description only; scan() embeds once and shares the result with the clusters and the Overlap candidates."""
    items = sorted(items, key=lambda i: i.id)  # greedy clustering depends on order, so fix the order
    # a hook's description is a shell command, which clusters by shape rather than meaning, so hooks are embedded by name (event:matcher)
    vectors = [_unit(v) for v in embed([i.name if i.kind == "hook" else f"{i.name}: {i.description}" for i in items])]
    centred = len(vectors) >= MIN_ITEMS_TO_CENTRE
    if centred:
        vectors = _centre(vectors)
    return {i.id: v for i, v in zip(items, vectors, strict=True)}, centred


def cluster(
    items: list[Item], labels: dict[str, str], by_id: dict[str, list[float]], centred: bool, threshold: float | None = None
) -> list[Cluster]:
    """Greedy leader clustering on name and description only (labels just name the clusters): each Item joins the closest
    cluster centre at or above `threshold`, else starts a new cluster. The default threshold depends on whether the vectors were centred."""
    items = sorted(items, key=lambda i: i.id)
    vectors = [by_id[i.id] for i in items]
    if threshold is None:
        threshold = CENTRED_THRESHOLD if centred else RAW_THRESHOLD
    groups: list[_Group] = []
    for index, vector in enumerate(vectors):
        best = max(groups, key=lambda g: dot(_unit(g.total), vector), default=None)
        if best is not None and dot(_unit(best.total), vector) >= threshold:
            best.total = list(map(add, best.total, vector))
            best.members.append(index)
        else:
            groups.append(_Group(vector, [index]))
    clusters = []
    for group in groups:
        centre = _unit(group.total)
        by_closeness = sorted(group.members, key=lambda i: -dot(centre, vectors[i]))  # sorted is stable, so ties keep item order
        labelled = next((i for i in by_closeness if items[i].id in labels), None)
        name = labels[items[labelled].id] if labelled is not None else items[by_closeness[0]].name
        clusters.append(Cluster(name, tuple(items[i].id for i in group.members)))
    return clusters
