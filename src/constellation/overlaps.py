"""Overlap detection in layers, cheapest first; each later layer only sees pairs the earlier ones left undecided.

Privacy: bodies are read here, on the user's machine, but only names, descriptions and short local signals ever reach a model."""

import hashlib
import re
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
