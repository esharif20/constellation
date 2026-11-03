"""Group Items by meaning: embed each Item's label and text, then join vectors that point the same way."""

import math
from dataclasses import dataclass, field
from operator import add

from .models import Cluster, Embedder, Item

# shortcut: raw bge-small cosines are squeezed (about 0.70 inside a group, 0.61 across), so no threshold clusters well: on the 30-item
# eval set 0.75 gives F1 0.33 (over-splits) and 0.68 merges everything. Subtracting the mean vector first reached F1 0.67 at threshold
# 0.0; adopt that once it is checked on real data (it needs a minimum number of items to be meaningful). See tests/eval.
DEFAULT_THRESHOLD = 0.75


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
    """Greedy leader clustering on name and description only (labels just name the clusters): each Item joins the closest
    cluster centre at or above `threshold`, else starts a new cluster."""
    items = sorted(items, key=lambda i: i.id)  # greedy clustering depends on order, so fix the order
    vectors = [_unit(v) for v in embed([f"{i.name}: {i.description}" for i in items])]
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
        by_closeness = sorted(group.members, key=lambda i: -_dot(centre, vectors[i]))  # sorted is stable, so ties keep item order
        labelled = next((i for i in by_closeness if items[i].id in labels), None)
        name = labels[items[labelled].id] if labelled is not None else items[by_closeness[0]].name
        clusters.append(Cluster(name, tuple(items[i].id for i in group.members)))
    return clusters
