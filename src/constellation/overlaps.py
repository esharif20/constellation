"""Overlap detection in layers, cheapest first; each later layer only sees pairs the earlier ones left undecided.

Privacy: bodies are read here, on the user's machine, but only names, descriptions and short local signals ever reach a model."""

import hashlib
from collections import defaultdict

from .models import Item, Overlap


def _normalise(body: str) -> str:
    return "\n".join(line.rstrip() for line in body.strip().splitlines())


def exact_duplicates(items: list[Item], bodies: dict[str, str]) -> list[Overlap]:
    """Layer 1: identical instructions. Name and description are not hashed: a renamed copy is still a copy."""
    groups: dict[str, list[str]] = defaultdict(list)
    for item in items:
        body = _normalise(bodies.get(item.id, ""))
        if body:  # empty bodies would all match each other
            groups[hashlib.sha256(body.encode()).hexdigest()].append(item.id)
    overlaps = []
    for ids in groups.values():
        anchor, *others = sorted(ids)  # n copies make n-1 pairs; all n*n/2 pairs would be noise
        overlaps += [Overlap(anchor, other, "duplicate", "identical instructions") for other in others]
    return overlaps
