from datetime import date
from typing import Any

from .report import _known_costs, _never_used, _ranked
from .snapshot import snapshot
from .suggestions import suggest

PUBLIC_FOOTER = "Shared from Constellation (public summary: no dates, paths or ids)."


def explain(data: dict[str, Any], public: bool = False) -> dict[str, Any]:
    """Short summary of a scan. Public mode reads only the Snapshot allowlist: no usage, dates, ids or paths."""
    if public:
        data = snapshot(data)
    known = _known_costs(data)
    items = data["items"]
    clusters = sorted(data.get("clusters") or [], key=lambda c: (-len(c["item_ids"]), c["name"]))[:3]
    window = data.get("usage_window")  # a Snapshot has none, so public mode is always null
    unused = None
    if window:
        unused = [{"name": i["name"], "kind": i["kind"], "always_on": known.get(i["id"])} for i in _never_used(data)[:5]]
    days = 0
    if window and window.get("first"):
        days = (date.fromisoformat(window["last"]) - date.fromisoformat(window["first"])).days + 1
    return {
        "public": public,
        "items": len(items),
        "known": sum(known.values()) if known else None,  # None = nothing measured, never 0
        "unknown": sum(i["id"] not in known for i in items),
        "clusters": [
            {
                "name": c["name"],
                "items": len(c["item_ids"]),
                "always_on": sum(known[i] for i in c["item_ids"] if i in known) if any(i in known for i in c["item_ids"]) else None,
            }
            for c in clusters
        ],
        "costs": [{"name": i["name"], "kind": i["kind"], "always_on": known[i["id"]]} for i in _ranked(data, known)[:5]],
        "unused": unused,
        "window": {"files": window["files"], "days": days} if window else None,
        "actions": [{"reason": s.reason, "tokens_saved": s.tokens_saved} for s in suggest(data)[:3]],
    }


def _tokens(value: int | None) -> str:
    return "cost unknown" if value is None else f"{value:,} tokens"


def render_explain(summary: dict[str, Any]) -> str:
    lines = ["# My Claude Code setup", ""]
    cost = "cost not measured" if summary["known"] is None else f"{summary['known']:,} always-on tokens known"
    lines += [f"{summary['items']} items, {cost}, {summary['unknown']} with unknown cost.", "", "## Largest clusters", ""]
    lines += [f"- {c['name']}: {c['items']} items, {_tokens(c['always_on'])}" for c in summary["clusters"]] or ["- None."]
    lines += ["", "## Costliest always-on", ""]
    lines += [f"- {c['name']} ({c['kind']}): {_tokens(c['always_on'])}" for c in summary["costs"]] or ["- None measured."]
    lines += ["", "## Not used lately", ""]
    if summary["public"]:
        lines.append("Not included in public summaries.")
    elif summary["unused"] is None:
        lines.append("Usage was not read in this scan.")
    else:
        w = summary["window"]
        lines += [f"Checked {w['files']} transcripts over {w['days']} days.", ""]
        lines += [f"- {u['name']} ({u['kind']}): {_tokens(u['always_on'])}" for u in summary["unused"]] or ["- None."]
    lines += ["", "## Three suggested actions", ""]
    lines += [f"- {a['reason']} (saves {_tokens(a['tokens_saved'])})" for a in summary["actions"]] or ["- None."]
    if summary["public"]:
        lines += ["", PUBLIC_FOOTER]
    return "\n".join(lines) + "\n"
