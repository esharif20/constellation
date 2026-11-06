"""Glue between a saved scan and the verdict engine (smarter-verdict §4.4). Local and free: no provider call, no transcript read.

`compute` is the one place that turns the scan JSON, the habit ledger and the pins into Assessments, so the Inspector, the Brief
and Ask can never disagree. The engine keys Items by name; this module adapts the scan's id-keyed overlaps and conflicts.
"""

import re
import statistics
from dataclasses import asdict, dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any

from . import habits as habit_ledger
from . import history
from . import pins as pin_file
from .redact import redact
from .usage import TRACKED, mac
from .verdict import assess, evidence
from .verdict_types import Assessment, Evidence, Habits, ItemEvidence, ItemHabits

SCOPE_RANK = {"local": 0, "project": 1, "user": 2}  # an MCP server name resolves to the narrowest scope


@dataclass(frozen=True)
class Assessed:
    assessments: dict[str, Assessment]  # Item id -> verdict
    evidence: Evidence  # keyed by Item id
    ledger: bool  # True when the habit ledger (not just the saved transcripts) backs the verdicts


def _scope(item: dict[str, Any]) -> str:
    match = re.search(r":mcp_server:(user|local)/", item["id"])
    return match[1] if match else "project"


def _keys(items: list[dict[str, Any]]) -> dict[str, str]:
    """Item id -> the unique name the engine keys by. Shared names get a qualifier so they cannot collide."""
    count: dict[str, int] = {}
    for i in items:
        count[i["name"]] = count.get(i["name"], 0) + 1
    keys: dict[str, str] = {}
    for i in sorted(items, key=lambda i: i["id"]):
        qualifier = _scope(i) if i["kind"] == "mcp_server" else i["kind"]
        keys[i["id"]] = i["name"] if count[i["name"]] == 1 else f"{i['name']} ({qualifier})"
    if len(set(keys.values())) != len(keys):  # still shared (same kind and scope): the id is unique
        keys = {i: k if list(keys.values()).count(k) == 1 else f"{k} [{i}]" for i, k in keys.items()}
    return keys


def adapt(data: dict[str, Any], keys: dict[str, str]) -> dict[str, Any]:
    """The engine's input (verdict.py docstring) from a real scan; Items are renamed to their unique key."""
    costs = data.get("costs") or {}
    parents: dict[str, str] = {}
    for r in data.get("relations") or []:
        if r["kind"] == "contains":
            parents.setdefault(r["target"], r["source"])
    callers: dict[str, list[str]] = {}
    for r in data.get("relations") or []:
        if r["kind"] == "triggers" and r["source"] in keys:
            callers.setdefault(r["target"], []).append(keys[r["source"]])
    kinds = {i["id"]: i["kind"] for i in data["items"]}
    items = []
    for i in data["items"]:
        parent = parents.get(i["id"])
        item: dict[str, Any] = {
            "id": i["id"], "kind": i["kind"], "name": keys[i["id"]], "description": i["description"], "origin": i.get("origin"),
            "always_on": (costs.get(i["id"]) or {}).get("always_on"), "scope": i.get("scope", "global"),
            "match": i["name"], "callers": sorted(callers.get(i["id"], [])),
        }  # fmt: skip
        if i.get("disabled"):
            item["disabled"] = True
        if parent in keys and kinds.get(parent) == "plugin":
            item["plugin"] = keys[parent]
        items.append(item)
    by_id = {i["id"]: i for i in data["items"]}
    shadowed = []
    conflicts = []
    for c in data.get("conflicts") or []:
        ids = [i for i in c["item_ids"] if i in by_id]
        if c["kind"] == "mcp_name" and ids:
            ranked = sorted(ids, key=lambda i: (SCOPE_RANK[_scope(by_id[i])], i))
            for lost in ranked[1:]:  # only the copy that never loads is passed on
                detail = f"{_scope(by_id[lost])} copy shadowed by {_scope(by_id[ranked[0]])} scope"
                shadowed.append({"kind": "mcp_name", "ids": [keys[lost]], "detail": detail})
        elif c["kind"] == "trigger":
            conflicts.append({"kind": "trigger", "ids": [keys[i] for i in ids], "detail": c["reason"]})
    children: dict[str, int] = {}
    for item in items:
        if "plugin" in item:
            children[item["plugin"]] = children.get(item["plugin"], 0) + 1
    weights = data.get("hook_weights") or {}
    hook_bytes = {keys[k]: w["bytes"] for k, w in weights.items() if k in keys and isinstance(w, dict) and w.get("bytes") is not None}
    return {
        "items": items,
        "overlaps": [
            {"a": keys[o["a_id"]], "b": keys[o["b_id"]], "verdict": o["verdict"]}
            for o in data.get("overlaps") or []
            if o["a_id"] in keys and o["b_id"] in keys and o["verdict"] != "distinct"
        ],
        "conflicts": shadowed + conflicts,
        "plugin_children": children,
        "hook_bytes": hook_bytes,
    }


def _days(first: str, last: str) -> int:
    """Whole days from `first` to `last`; 0 for a date that does not parse (a malformed window means an unknown span)."""
    try:
        return max(0, (date.fromisoformat(last) - date.fromisoformat(first)).days)
    except ValueError:
        return 0


def _skipped(data: dict[str, Any]) -> float:
    window = data.get("usage_window") or {}
    total = (window.get("files") or 0) + (window.get("skipped") or 0)
    return (window.get("skipped") or 0) / total if total else 0.0


def _from_ledger(data: dict[str, Any], ledger: dict[str, Any], today: str, keys: dict[str, str]) -> tuple[Habits, Evidence]:
    items = data["items"]
    tracked = {i["id"]: i["kind"] for i in items if i["kind"] in TRACKED}
    parents = {r["target"]: r["source"] for r in data.get("relations") or [] if r["kind"] == "contains"}
    profile = habit_ledger.profile(ledger, today, tracked, {k: v for k, v in parents.items() if k in tracked})
    days = {d: r for d, r in ledger["days"].items() if d <= today}
    active = sorted(days)
    start = active[0] if active else today
    per_item: dict[str, ItemEvidence] = {}
    for i in items:
        if i["id"] not in tracked:
            continue
        record = ledger["items"].get(mac(ledger["salt"], i["id"], 12)) or {"first_seen": today, "days": {}}
        used = {d: c for d, c in record["days"].items() if d <= today and c["n"] > 0}
        h = profile.items[i["id"]]
        per_item[keys[i["id"]]] = ItemEvidence(
            sessions_used=sum(c["s"] for c in used.values()),
            days_used=len(used),
            last_used=max(used, default=None),
            idle_active_days=h.idle_active_days,
            mean_gap=h.typical_gap,
            first_seen=record["first_seen"] if record["first_seen"] > start else None,  # the day we began watching proves nothing
            changed_on=i.get("changed_on"),
        )
    sessions = sum(r["sessions"] for r in days.values())
    projects = {
        p: (max(d for d, r in days.items() if p in r["projects"]), sum(r["projects"].get(p, 0) for r in days.values()))
        for p in {p for r in days.values() for p in r["projects"]}
    }
    base = Evidence(
        sessions=sessions,
        active_days=len(active),
        span_days=(date.fromisoformat(active[-1]) - date.fromisoformat(active[0])).days + 1 if active else 0,
        sessions_per_day=statistics.median(r["sessions"] for r in days.values()) if days else 0.0,
        projects=projects,
        skipped_share=_skipped(data),
        items=per_item,
    )  # fmt: skip
    return Habits(profile.active_days, profile.projects_active, {keys[i]: h for i, h in profile.items.items()}), base


def _from_scan(data: dict[str, Any], keys: dict[str, str]) -> tuple[Habits, Evidence]:
    """No ledger yet (or usage read without one): the saved transcripts' own counts, a short window that says so honestly."""
    window = data.get("usage_window") or {}
    usage: dict[str, Any] = dict(data.get("usage") or {})
    for id_, by in (data.get("usage_by_project") or {}).items():  # a scan with only the per-project counts still shows its uses
        if id_ not in usage and by:
            usage[id_] = {
                "count": sum(u["count"] for u in by.values()),
                "last_used": max(u.get("last_used") or "" for u in by.values()) or None,
            }
    files = window.get("files") or 0
    span = _days(window["first"], window["last"]) + 1 if window.get("first") and window.get("last") else 0
    sessions = window.get("sessions") or files
    active = min(span, sessions)
    tracked = [i for i in data["items"] if i["kind"] in TRACKED and i["id"] in usage]
    counts = {i["id"]: usage[i["id"]]["count"] for i in tracked}
    per_item: dict[str, ItemEvidence] = {}
    hab: dict[str, ItemHabits] = {}
    for i in tracked:
        u, same = usage[i["id"]], [counts[j["id"]] for j in tracked if j["kind"] == i["kind"]]
        last = (u.get("last_used") or "")[:10] or None
        newest = window.get("last")
        idle = _days(last, newest) if last and newest else None
        name, n = keys[i["id"]], u["count"]
        per_item[name] = ItemEvidence(
            sessions_used=min(n, sessions), days_used=min(n, active), last_used=last, idle_active_days=idle, changed_on=i.get("changed_on")
        )
        rank = 100 * sum(c < n for c in same) // len(same)
        per_project = [p["count"] for p in (data.get("usage_by_project") or {}).get(i["id"], {}).values() if p["count"] > 0]
        share = max(per_project) / sum(per_project) if per_project else 0.0
        hab[name] = ItemHabits(
            decayed_use=float(n),
            all_time=n,
            percentile=rank,
            idle_active_days=idle,
            projects_used=len(per_project),
            top_project_share=share,
        )
    base = Evidence(sessions, active, span, sessions / active if active else 0.0, {}, _skipped(data), per_item)
    return Habits(active, len(data.get("projects") or {}), hab), base


def compute(data: dict[str, Any], ledger_path: Path | None = None, pins_path: Path | None = None, today: str | None = None) -> Assessed:
    """Every Item's Assessment for this saved scan. The ledger is used when it holds this setup (data['setup']), else the scan's usage."""
    today = today or history._today()
    keys = _keys(data["items"])
    records, _ = habit_ledger.load(ledger_path or habit_ledger.DEFAULT_CACHE)
    ledger = records.get(data.get("setup") or "")
    habits, base = _from_ledger(data, ledger, today, keys) if ledger else _from_scan(data, keys)
    ids = frozenset(i for i in pin_file.load(pins_path or pin_file.DEFAULT_CACHE) if i in keys)
    view = adapt(data, keys)
    ev = evidence(view, habits, base, ids)
    result = assess(view, ev, habits, ids, date.fromisoformat(today))
    by_id = {i: ev.items[k] for i, k in keys.items() if k in ev.items}
    return Assessed(result, replace(ev, items=by_id), ledger is not None)


def public(a: Assessment) -> dict[str, Any]:
    """The Assessment as JSON for the local app, with reason texts redacted."""
    row = asdict(a)
    row["reasons"] = [{"code": r.code, "text": redact(r.text)} for r in a.reasons]
    return row
