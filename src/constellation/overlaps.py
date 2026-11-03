"""Overlap detection in layers, cheapest first; each later layer only sees pairs the earlier ones left undecided.

Privacy: bodies are read here, on the user's machine, but only names, descriptions and short local signals ever reach a model."""

import hashlib
import re
from collections import defaultdict
from itertools import combinations

from .cluster import dot
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


WRAPPER_MAX_WORDS = 80  # shortcut: a guess; tune on a real setup


def _mentions(body: str, name: str) -> bool:
    """`/name`, `` `name` `` or `name skill|agent`, as a whole token: a bare English word never counts."""
    n = re.escape(name)
    return re.search(rf"(?<![\w-])/{n}(?![\w-])|`{n}`|(?<![\w-]){n} (?:skill|agent)\b", body) is not None


def wrappers(items: list[Item], bodies: dict[str, str]) -> list[Overlap]:
    """Layer 2: a short body that names exactly one other skill or agent and is shorter than it only hands off to it."""
    named = [i for i in items if i.id in bodies]
    overlaps = []
    for wrapper in named:
        body = _normalise(bodies[wrapper.id])
        words = len(body.split())
        if words > WRAPPER_MAX_WORDS:
            continue
        called = {i.name for i in named if i.name != wrapper.name and _mentions(body, i.name)}
        targets = [i for i in named if i.name in called]
        if len(called) == 1 and len(targets) == 1 and len(_normalise(bodies[targets[0].id]).split()) > words:  # one name, one Item
            reason = f"'{wrapper.name}' is {words} words and only hands off to '{targets[0].name}'"
            overlaps.append(Overlap(wrapper.id, targets[0].id, "wrapper", reason))
    return overlaps


TOP_K = 3
CANDIDATE_THRESHOLD = 0.5  # on centred cosines, which spread from -1 to 1
MAX_PAIRS = 150  # keeps one scan's verifier bill bounded


def candidates(items: list[Item], vectors: dict[str, list[float]], decided: set[frozenset[str]]) -> tuple[list[tuple[str, str]], list[str]]:
    """Layer 3: embeddings only propose pairs; the verifier decides. Each skill or agent proposes its nearest neighbours, and
    same-name copies are always proposed, which finds cross-plugin copies whose bodies drifted."""
    eligible = sorted((i for i in items if i.kind in ("skill", "agent")), key=lambda i: i.id)
    scores: dict[tuple[str, str], float] = {}
    for item in eligible:
        if item.id not in vectors:
            continue
        near = sorted(
            ((dot(vectors[item.id], vectors[o.id]), o.id) for o in eligible if o is not item and o.id in vectors), key=lambda t: (-t[0], t[1])
        )
        for similarity, other in near[:TOP_K]:
            if similarity >= CANDIDATE_THRESHOLD:
                scores[min(item.id, other), max(item.id, other)] = similarity
    for a, b in combinations(eligible, 2):
        if a.name == b.name:
            scores[a.id, b.id] = 1.0  # shortcut: ranks with the closest vectors; they are rare
    ranked = sorted((k for k in scores if frozenset(k) not in decided), key=lambda k: (-scores[k], k))
    warnings = [f"checked the {MAX_PAIRS} most similar pairs; {len(ranked) - MAX_PAIRS} more were not checked"] if len(ranked) > MAX_PAIRS else []
    return ranked[:MAX_PAIRS], warnings
