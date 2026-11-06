import os
import re
from pathlib import Path
from typing import Any

from .answer import clean_name
from .redact import redact
from .report import CAVEAT, _known_costs, _saving
from .suggestions import Kind, Suggestion, _make, _moves
from .verdict_types import Assessment, Evidence

HEADER = "Constellation never edits your config. Every change below is yours to make by hand.\n\n# Constellation cleanup checklist\n\n"


def checklist_ids(text: str) -> list[str]:
    ids = []
    for line in text.splitlines():
        match = re.fullmatch(r"- \[[ xX]\] .+ \(id ([0-9a-f]{12})\)", line)
        if match:
            ids.append(match[1])
    return list(dict.fromkeys(ids))


def append_line(path: Path, s: Suggestion) -> bool:
    """Append a server-selected Suggestion; the caller serialises concurrent updates."""
    try:
        text = path.read_text()
    except FileNotFoundError:
        text = ""
    if s.id in checklist_ids(text):
        if path.exists():
            path.chmod(0o600)  # a loose file is tightened even when nothing is added
        return False
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    reason = " ".join(s.reason.splitlines())
    line = f"- [ ] {reason} {_saving(s)} (id {s.id})\n"
    if not text:
        line = f"{HEADER}{line}"
    elif not text.endswith("\n"):
        line = f"\n{line}"
    # O_APPEND, never truncate: a user's edit made since the read above survives, and one write keeps the line whole.
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    fd = os.open(path, flags, 0o600)  # pragma: no mutate
    os.chmod(path, 0o600)  # the mode above applies only to a new file
    with os.fdopen(fd, "a") as f:
        f.write(line)
    return True


BUDGET_DAYS = 30  # "used in the last 30 active days" for the whole-setup budget line (§7f)
_KIND: dict[str, Kind] = {
    "remove": "remove_unused",
    "remove_twin": "remove_duplicate",
    "use_underlying": "use_underlying",
    "move_to_project": "move_to_project",
    "disable_plugin": "disable_plugin",
    "fix_description": "fix_description",
}
_REMOVING = {"remove", "remove_twin", "use_underlying", "disable_plugin"}  # actions that take the assessed Item away


def _row_ids(a: Assessment, data: dict[str, Any]) -> tuple[str, ...]:
    """Item ids as the old generators made them, so a checklist line still matches when the kind is unchanged."""
    for o in data.get("overlaps") or []:
        if a.action == "remove_twin" and o["verdict"] == "duplicate" and a.id in (o["a_id"], o["b_id"]):
            return tuple(sorted((o["a_id"], o["b_id"])))
        if a.action == "use_underlying" and o["verdict"] == "wrapper" and o["a_id"] == a.id:
            return (o["a_id"], o["b_id"])
    return (a.id,)


def _wait_summary(rows: list[dict[str, Any]], by_id: dict[str, Assessment]) -> list[dict[str, Any]]:
    codes: dict[str, list[int | None]] = {}
    for row in rows:
        a = by_id[row["item_ids"][0]]
        codes.setdefault(a.reasons[0].code, []).append(a.recheck_after)
    ahead = {c: [d for d in days if d is not None] for c, days in codes.items()}
    out = [{"code": c, "count": len(days), "recheck_after": max(ahead[c], default=None)} for c, days in codes.items()]
    return sorted(out, key=lambda w: (-w["count"], w["code"]))


def _budget(data: dict[str, Any], evidence: Evidence, known: dict[str, int]) -> dict[str, Any] | None:
    """§7f: what skills cost every session, and how much of that is for skills used lately."""
    skills = [i["id"] for i in data["items"] if i["kind"] == "skill" and not i.get("disabled") and i["id"] in known]
    tokens = sum(known[i] for i in skills)
    if not tokens:
        return None

    def lately(id_: str) -> bool:
        e = evidence.items.get(id_)
        return e is not None and e.count > 0 and (e.idle_active_days is None or e.idle_active_days < BUDGET_DAYS)

    used = sum(known[i] for i in skills if lately(i))
    return {"kind": "skill", "tokens": tokens, "used_tokens": used, "used_share": round(used / tokens, 2), "days": BUDGET_DAYS}


def build_brief(data: dict[str, Any], assessments: dict[str, Assessment], evidence: Evidence) -> dict[str, Any]:
    """Group, rank and total the assessed Items (§5). Pure and local; the server adds `checklist`.

    Rank key is (-saves / risk, -saves, name, id); an unknown saving sorts last and is never 0.
    """
    items = {i["id"]: i for i in data["items"]}
    names = {k: f"{clean_name(i['name'])} ({i['kind']})" for k, i in items.items()}
    moves = {s.item_ids[0]: s for s in _moves(data)}
    labels = data.get("projects") or {}
    groups: dict[str, list[tuple[dict[str, Any], Assessment]]] = {"safe": [], "look": [], "wait": []}
    for a in assessments.values():
        if a.group is None or a.id not in items:
            continue
        kind: Kind = _KIND.get(a.action, "wait")
        s = _make(kind, _row_ids(a, data), redact(f"{names[a.id]}: {a.reasons[0].text}"), None)
        row: dict[str, Any] = {
            "id": s.id,
            "kind": s.kind,
            "item_ids": list(s.item_ids),
            "removes": a.id if a.action in _REMOVING else None,
            "reason": s.reason,
            "saves": a.saves,
            "tier": a.tier,
            "confidence": a.confidence,
            "reasons": [{"code": r.code, "text": redact(r.text)} for r in a.reasons],
        }
        if (m := moves.get(a.id)) and a.action == "move_to_project":
            row.update(project=m.project, project_label=labels.get(m.project))
        groups[a.group].append((row, a))

    def rank(pair: tuple[dict[str, Any], Assessment]) -> tuple[bool, float, int, str, str]:
        row, a = pair
        saves = a.saves or 0
        return (a.saves is None, -saves / a.risk, -saves, items[a.id]["name"], a.id)

    for g in groups.values():
        g.sort(key=rank)
    parents = {a.id for _, a in groups["safe"] + groups["look"] if a.action == "disable_plugin"}
    inside = {r["target"] for r in data.get("relations") or [] if r["kind"] == "contains" and r["source"] in parents}

    def total(g: list[tuple[dict[str, Any], Assessment]]) -> tuple[int, int]:
        counted = [a for _, a in g if a.id not in inside]  # a plugin's parts are counted once, through the plugin
        return sum(a.saves or 0 for a in counted), sum(a.saves is None for a in counted)

    (safe, safe_unknown), (look, look_unknown) = total(groups["safe"]), total(groups["look"])
    low, high = safe, safe + look
    pace = evidence.sessions_per_day
    per_day = (int(round(low * pace, -2)), int(round(high * pace, -2)))
    wait = [row for row, _ in groups["wait"]]
    by_id = {a.id: a for _, a in groups["wait"]}
    return {
        "evidence": {
            "sessions": evidence.sessions,
            "active_days": evidence.active_days,
            "span_days": evidence.span_days,
            "sessions_per_day": pace,
        },
        "safe": {"rows": [r for r, _ in groups["safe"]], "saves": safe, "unknown": safe_unknown},
        "look": {"rows": [r for r, _ in groups["look"]], "saves": look, "unknown": look_unknown},
        "wait": {"summary": _wait_summary(wait, by_id), "rows": wait},
        # per_day is (0, 0) when the pace is unknown
        "range": {"low": low, "high": high, "per_day": per_day, "unknown": safe_unknown + look_unknown},
        "scope": {"caveat": CAVEAT},
        "budget": _budget(data, evidence, _known_costs(data)),
    }
