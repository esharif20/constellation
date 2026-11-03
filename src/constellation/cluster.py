"""Group Items by meaning: embed each Item's label and text, then join vectors that point the same way."""

import math
from dataclasses import dataclass, field
from operator import add

from .models import Cluster, Embedder, Item

# shortcut: 0.68 cosine was tuned on six sample sentences with bge-small; re-tune on real data. Result depends on item order.
DEFAULT_THRESHOLD = 0.68


def _unit(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector] if norm else vector  # a zero vector stays zero and matches nothing


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))  # strict: embeddings of mixed dimensions are an error, not a silent truncation


@dataclass
class _Group:
    total: list[float]  # sum of the members' unit vectors; its direction is the cluster centre
    members: list[int] = field(default_factory=list)


def cluster(items: list[Item], labels: dict[str, str], embed: Embedder, threshold: float = DEFAULT_THRESHOLD) -> list[Cluster]:
    """Greedy leader clustering: each Item joins the closest cluster centre at or above `threshold`, else starts a new cluster."""
    vectors = [_unit(v) for v in embed([f"{labels[i.id]}. {i.name}: {i.description}" for i in items])]
    groups: list[_Group] = []
    for index, vector in enumerate(vectors):
        best = max(groups, key=lambda g: _dot(_unit(g.total), vector), default=None)
        if best is not None and _dot(_unit(best.total), vector) >= threshold:
            best.total = list(map(add, best.total, vector))
            best.members.append(index)
        else:
            groups.append(_Group(vector, [index]))
    clusters = []
    for group in groups:
        centre = _unit(group.total)
        nearest = max(group.members, key=lambda i: _dot(centre, vectors[i]))  # the member closest to the centre names the cluster
        clusters.append(Cluster(labels[items[nearest].id], tuple(items[i].id for i in group.members)))
    return clusters
