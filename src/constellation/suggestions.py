import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from .redact import redact
from .report import _known_costs, _names, _never_used, _span

Kind = Literal[
    "remove_duplicate", "use_underlying", "remove_unused", "review_cost", "move_to_project", "disable_plugin", "fix_description", "wait"
]


@dataclass(frozen=True)
class Suggestion:
    id: str  # content-derived, so a decision still applies after a re-scan
    kind: Kind
    item_ids: tuple[str, ...]
    reason: str  # plain English, redacted
    tokens_saved: int | None  # None = unknown, never 0
    project: str | None = None  # opaque project key, never a label
    confidence: str | None = None  # "high" / "medium"


def _make(
    kind: Kind,
    item_ids: tuple[str, ...],
    reason: str,
    saved: int | None,
    project: str | None = None,
    confidence: str | None = None,
) -> Suggestion:
    digest = hashlib.sha256((kind + "\0" + "\0".join(item_ids)).encode()).hexdigest()[:12]
    return Suggestion(digest, kind, item_ids, redact(reason), saved, project, confidence)


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
        reason = f"{names[id_]} was never seen in {window['files']} transcripts{_span(window, ' ({0} to {1}, {2} days)')}."
        if id_ in known:
            reason += f" It costs {known[id_]} always-on tokens every session."
        reason += (
            f" Claude Code deletes old transcripts and {window['skipped']} skipped files were not read, so this is not proof it is unused."
        )
        found.append(_make("remove_unused", (id_,), reason, known.get(id_)))
    return found


MOVE_MIN_USES, MOVE_MIN_SHARE = 3, 0.8
HIGH_DAYS, HIGH_USES = 14, 5


def _moves(data: dict[str, Any]) -> list[Suggestion]:
    """Items used almost only in one project. The reason never names the project; `project` is the opaque key."""
    by_project, known = data.get("usage_by_project") or {}, _known_costs(data)
    if not by_project:
        return []
    items = data["items"]
    contents: dict[str, list[str]] = {}
    inside = set()
    for r in data.get("relations") or []:
        if r["kind"] == "contains":
            contents.setdefault(r["source"], []).append(r["target"])
            inside.add(r["target"])
    window = data.get("usage_window")
    days = int(span) if window and (span := _span(window, "{2}")) else None  # "" when the window is missing or malformed
    copies = {(i["kind"], i["name"], i.get("project")) for i in items if i.get("scope") == "project"}
    found = []
    for item in items:
        id_ = item["id"]
        if item.get("scope", "global") != "global" or item.get("disabled") or id_ in inside:
            continue
        if item["kind"] not in {"skill", "agent", "mcp_server", "plugin"}:
            continue
        counts: dict[str, int] = {}
        for member in [id_, *contents.get(id_, [])]:
            for key, u in (by_project.get(member) or {}).items():
                counts[key] = counts.get(key, 0) + u["count"]
        total = sum(counts.values())
        if not total:
            continue
        top = max(counts.values())
        winners = [k for k, n in counts.items() if n == top]
        if len(winners) != 1 or len([n for n in counts.values() if n]) >= 3:
            continue
        if total < MOVE_MIN_USES or top / total < MOVE_MIN_SHARE or (item["kind"], item["name"], winners[0]) in copies:
            continue
        high = days is not None and days >= HIGH_DAYS and total >= HIGH_USES
        over = f" over {days} days" if days is not None else ""
        where = "Enable it only in that project's settings." if item["kind"] == "plugin" else "Move it into that project's .claude/ folder."
        reason = f"{item['name']} ({item['kind']}) was used {total} times{over}, {top} of them in one project. {where}"
        found.append(_make("move_to_project", (id_,), reason, known.get(id_), winners[0], "high" if high else "medium"))
    return found


GENERATORS: list[Callable[[dict[str, Any]], list[Suggestion]]] = [_duplicates, _wrappers, _unused, _moves]


def suggest(data: dict[str, Any]) -> list[Suggestion]:
    """Known savings first (largest first), then unknown; ties by Item ids, so the same scan always gives the same order."""
    every = [s for generate in GENERATORS for s in generate(data)]
    return sorted(every, key=lambda s: (s.tokens_saved is None, -(s.tokens_saved or 0), s.item_ids))
