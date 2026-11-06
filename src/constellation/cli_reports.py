"""Terminal analysis commands over a saved scan: thin glue over the engine the app uses (assessment, brief, lenses, Ask).

Each command is a builder (scan -> plain dict, also the --json output) and a renderer (dict -> text). Read-only, local, no provider call.
To add a command, append to COMMANDS and register a builder and renderer.
"""

import json
import os
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from difflib import get_close_matches
from pathlib import Path
from typing import Any

from . import retrieve
from .assessment import Assessed, compute
from .brief import build_brief
from .chat import LocalChat
from .conflicts import conflicts
from .explain import explain, render_explain
from .hook_safety import hook_safety
from .receipt import receipt
from .redact import redact
from .report import render_cleanup, write_private
from .triggers import trigger_audit

WINDOW = 200_000  # the context window session-start tokens are compared with
OK, WARN, BAD = "✓", "!", "✗"
_ANSI = {"bold": "1", OK: "32", WARN: "33", BAD: "31"}
TOP = 10


@dataclass(frozen=True)
class Command:
    name: str
    help: str
    group: str
    arg: str | None = None  # the name of a required first positional (why <name>, ask <question>)


COMMANDS = (
    Command("doctor", "one-screen health check of your setup", "Analyse"),
    Command("cost", "what loads at session start, biggest first, by plugin", "Analyse"),
    Command("unused", "Items not used lately, with confidence", "Analyse"),
    Command("twins", "overlapping pairs and which one you use", "Analyse"),
    Command("why", "why one Item has its verdict, and what removing it frees", "Analyse", "name"),
    Command("hooks", "every hook, ranked by what it does to each prompt", "Analyse"),
    Command("clashes", "hook, MCP name and trigger-phrase collisions", "Analyse"),
    Command("triggers", "skills that never fire or fire too greedily", "Analyse"),
    Command("explain", "plain-English summary of the whole setup", "Analyse"),
    Command("ask", "ask a question in plain English (local rules, no model)", "Analyse", "question"),
    Command("clean", "write the removal checklist (never edits settings)", "Act"),
    Command("share", "write the public Snapshot (same as export --public)", "Act"),
)


class ReportError(Exception):
    """A usage or input problem: the message is printed and the exit code is 2."""


@dataclass(frozen=True)
class Scan:
    data: dict[str, Any]
    found: Assessed

    @property
    def names(self) -> dict[str, str]:
        return {i["id"]: i["name"] for i in self.data["items"]}


def load(path: Path, habits: Path | None = None) -> Scan:
    """The saved scan and its verdicts (the same compute() the app serves). Raises ReportError."""
    try:
        data = json.loads(path.read_text())
        items = data["items"]
        if not all(isinstance(i, dict) and all(isinstance(i.get(k), str) for k in ("id", "name", "kind", "description")) for i in items):
            raise ValueError
        if len({i["id"] for i in items}) != len(items):
            raise ValueError
        return Scan(data, compute(data, habits))
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        raise ReportError(f"{path} is missing or not a usable constellation scan; run `constellation scan` first.") from None


# ---- formatting ----


@dataclass(frozen=True)
class Style:
    color: bool = False
    width: int = 80

    def paint(self, text: str, style: str) -> str:
        return f"\033[{_ANSI[style]}m{text}\033[0m" if self.color else text

    def head(self, title: str) -> str:
        return "\n" + self.paint(title, "bold")

    def mark(self, marker: str) -> str:
        return self.paint(marker, marker)

    def table(self, rows: list[list[str]], indent: str = "  ") -> list[str]:
        """Left-aligned columns padded to the widest cell; the first column is shortened to fit the terminal."""
        cols = len(rows[0])
        widths = [max(len(r[c]) for r in rows) for c in range(cols)]
        widths[0] = min(widths[0], max(12, self.width - sum(widths[1:]) - 2 * cols - len(indent)))
        cut = [[(r[0] if len(r[0]) <= widths[0] else r[0][: widths[0] - 1] + "…"), *r[1:]] for r in rows]
        return [indent + "  ".join(r[c].ljust(widths[c]) for c in range(cols)).rstrip() for r in cut]


def style_for_stdout() -> Style:
    return Style(sys.stdout.isatty() and "NO_COLOR" not in os.environ, max(40, min(shutil.get_terminal_size().columns, 100)))


def _n(value: int | None) -> str:
    return "unknown" if value is None else f"{value:,}"


def _plural(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"


# ---- builders ----


def _doctor(s: Scan, _: str | None) -> dict[str, Any]:
    r, d = receipt(s.data), s.data
    b = build_brief(d, s.found.assessments, s.found.evidence)
    live = [i for i in d["items"] if not i.get("disabled")]
    hooks, clashes, trig = hook_safety(d), conflicts(d), trigger_audit(d)["rows"]
    total = r["total_tokens"]
    return {
        "session_start": {"tokens": total, "window": WINDOW, "percent": None if total is None else round(100 * total / WINDOW, 1)},
        "reclaimable": {"low": b["range"]["low"], "high": b["range"]["high"], "unknown": b["range"]["unknown"]},
        "findings": [{"text": row["reason"], "saves": row["saves"]} for row in (b["safe"]["rows"] + b["look"]["rows"])[:5]],
        "hooks": {"count": len(hooks), "can_block": sum(h["can_block"] for h in hooks)},
        "clashes": len(clashes),
        "triggers": {"greedy": sum("greedy" in t["flags"] for t in trig), "never": sum("never" in t["flags"] for t in trig)},
        "mcp": {"servers": sum(i["kind"] == "mcp_server" for i in live), "connectors": sum(i["kind"] == "connector" for i in live)},
        "warnings": len(d.get("warnings") or []),
    }


def _cost(s: Scan, _: str | None) -> dict[str, Any]:
    r = receipt(s.data)
    owner = {rel["target"]: s.names.get(rel["source"], rel["source"]) for rel in s.data.get("relations") or [] if rel["kind"] == "contains"}
    by_plugin: dict[str, dict[str, Any]] = {}
    for row in r["rows"]:
        if row["tokens"] is not None:
            name = owner.get(row["id"], "(not in a plugin)")
            g = by_plugin.setdefault(name, {"name": name, "tokens": 0, "items": 0})
            g["tokens"] += row["tokens"]
            g["items"] += 1
    plugins = sorted(by_plugin.values(), key=lambda g: (-g["tokens"], g["name"]))
    return {"total": r["total_tokens"], "unknown": r["unknown"], "top": r["rows"][:TOP], "plugins": plugins}


def _unused(s: Scan, _: str | None) -> dict[str, Any]:
    ev = s.found.evidence
    rows: list[dict[str, Any]] = []
    if ev.sessions:
        for id_, a in s.found.assessments.items():
            if a.tier not in ("off", "untracked") and ev.items[id_].count == 0:
                rows.append({"name": s.names[id_], "label": a.label, "confidence": a.confidence, "saves": a.saves})
    rows.sort(key=lambda r: (r["saves"] is None, -(r["saves"] or 0), r["name"]))
    return {"sessions": ev.sessions, "active_days": ev.active_days, "span_days": ev.span_days, "count": len(rows), "rows": rows[:20]}


def _twins(s: Scan, _: str | None) -> dict[str, Any]:
    use = {k: v.count for k, v in s.found.evidence.items.items()}
    rows = []
    for o in s.data.get("overlaps") or []:
        if o["verdict"] != "distinct":
            a, b = use.get(o["a_id"], 0), use.get(o["b_id"], 0)
            you = "neither yet" if a == b == 0 else "both about equally" if a == b else s.names[o["a_id"] if a > b else o["b_id"]]
            rows.append({"a": s.names[o["a_id"]], "b": s.names[o["b_id"]], "verdict": o["verdict"], "reason": o["reason"], "you_use": you})
    return {"pairs": rows}


def find_item(s: Scan, query: str) -> dict[str, Any]:
    items = s.data["items"]
    for fold in (str, str.casefold):  # exact first, then ignoring case
        hits = [i for i in items if fold(query) in (fold(i["id"]), fold(i["name"]))]
        if len(hits) > 1:
            raise ReportError(redact(f"'{query}' matches several Items: " + ", ".join(i["id"] for i in hits) + ". Use the id."))
        if hits:
            return dict(hits[0])
    close = get_close_matches(query, sorted({i["name"] for i in items}), 3, 0.5)
    raise ReportError(redact(f"No Item named '{query}'." + (f" Did you mean: {', '.join(close)}?" if close else "")))


def _why(s: Scan, query: str | None) -> dict[str, Any]:
    item = find_item(s, query or "")
    a = s.found.assessments[item["id"]]
    rels = s.data.get("relations") or []
    refs = {s.names.get(r["source"], r["source"]) for r in rels if r["target"] == item["id"] and r["kind"] != "contains"}
    refs |= {s.names.get(i, i) for i in s.found.evidence.items[item["id"]].referenced_by}
    parts = sorted(s.names.get(r["target"], r["target"]) for r in rels if r["source"] == item["id"] and r["kind"] == "contains")
    return {
        "name": item["name"],
        "kind": item["kind"],
        "verdict": a.label,
        "confidence": a.confidence,
        "reasons": [r.text for r in a.reasons],
        "frees": a.saves,
        "referenced_by": sorted(refs),
        "contains": parts,
        "twin": s.names.get(a.twin_id) if a.twin_id else None,
        "history_days": s.found.evidence.active_days,
    }


def _hooks(s: Scan, _: str | None) -> dict[str, Any]:
    return {"hooks": hook_safety(s.data)}


def _clashes(s: Scan, _: str | None) -> dict[str, Any]:
    return {"clashes": [{**c, "names": [s.names.get(i, i) for i in c["item_ids"]]} for c in conflicts(s.data)]}


def _triggers(s: Scan, _: str | None) -> dict[str, Any]:
    return trigger_audit(s.data)


def _explain(s: Scan, _: str | None) -> dict[str, Any]:
    summary = explain(s.data)
    return {**summary, "text": render_explain(summary)}


def _ask(s: Scan, question: str | None) -> dict[str, Any]:
    opened: list[retrieve.Index] = []  # word search only: the embedder (a model download) is never loaded here

    def index_for(items: list[dict[str, Any]]) -> retrieve.Index:
        opened.append(retrieve.Index(items))
        return opened[0]

    try:
        reply = LocalChat().answer(s.data, question or "", [], index_for, s.found)
    finally:
        for index in opened:
            index.close()
    return {"question": question, "answer": reply["answer"]}


# ---- renderers ----


def _r_doctor(d: dict[str, Any], st: Style) -> str:
    ss, rec, hk, tr, mcp = d["session_start"], d["reclaimable"], d["hooks"], d["triggers"], d["mcp"]
    pct = ss["percent"]
    mark = WARN if pct is None else OK if pct < 10 else WARN if pct < 25 else BAD  # shortcut: thresholds are a judgement, not measured
    start = "not measured" if pct is None else f"{_n(ss['tokens'])} tokens, {pct}% of a {ss['window'] // 1000}k window"
    free = (
        "nothing safe to remove yet"
        if rec["high"] == 0
        else f"{rec['low']:,} to {rec['high']:,} tokens per session"
        + (f" ({_plural(rec['unknown'], 'Item')} of unknown size not counted)" if rec["unknown"] else "")
    )
    lines = [st.paint("Constellation doctor", "bold"), "", f"  {st.mark(mark)} Session start: {start}"]
    lines.append(f"  {st.mark(OK if rec['high'] == 0 else WARN)} Could be reclaimed: {free}")
    if d["findings"]:
        lines.append(st.head("Top findings"))
        lines += [f"  - {f['text']} (saves {_n(f['saves'])})" for f in d["findings"]]
    n, t = d["clashes"], tr["greedy"] + tr["never"]
    lines.append(st.head("Hooks and triggers"))
    lines.append(
        f"  {st.mark(BAD if n else OK)} {'No clashes' if n == 0 else '1 clash' if n == 1 else f'{n:,} clashes'}"
        + (" (run `constellation clashes`)" if n else "")
    )
    lines.append(f"  {st.mark(OK)} {_plural(hk['count'], 'hook')}, {hk['can_block']} able to block a prompt")
    lines.append(f"  {st.mark(WARN if t else OK)} {tr['never']} skills never fire, {tr['greedy']} fire greedily")
    lines.append(st.head("MCP and connectors"))
    lines.append(f"  {_plural(mcp['servers'], 'MCP server')}, {_plural(mcp['connectors'], 'connector')} (tool schemas are not measured)")
    if d["warnings"]:
        lines += ["", f"  {st.mark(WARN)} {_plural(d['warnings'], 'scan warning')} in the saved scan"]
    return "\n".join(lines) + "\n"


def _r_cost(d: dict[str, Any], st: Style) -> str:
    total = f"  Total: {_n(d['total'])} tokens" + (f" ({d['unknown']} Items unmeasured)" if d["unknown"] else "")
    lines = [st.paint("Session-start bill", "bold"), "", total, st.head("Biggest first")]
    lines += st.table(
        [[r["name"], r["kind"], f"{r['tokens']:,}"] for r in d["top"] if r["tokens"] is not None] or [["none measured", "", ""]]
    )
    lines.append(st.head("By plugin"))
    lines += st.table([[g["name"], _plural(g["items"], "Item"), f"{g['tokens']:,}"] for g in d["plugins"]] or [["none", "", ""]])
    return "\n".join(lines) + "\n"


def _r_unused(d: dict[str, Any], st: Style) -> str:
    if not d["sessions"]:
        return "No session history yet, so nothing can be called unused. Run `constellation scan` after some sessions.\n"
    history = f"  History: {_plural(d['sessions'], 'session')} over {_plural(d['span_days'], 'day')} ({d['active_days']} active)"
    lines = [st.paint("Not used lately", "bold"), "", history, ""]
    lines += st.table(
        [[r["name"], r["label"], f"{r['confidence']} confidence", f"saves {_n(r['saves'])}"] for r in d["rows"]] or [["none", "", "", ""]]
    )
    if d["count"] > len(d["rows"]):
        lines.append(f"  and {d['count'] - len(d['rows'])} more")
    return "\n".join(lines) + "\n"


def _r_twins(d: dict[str, Any], st: Style) -> str:
    if not d["pairs"]:
        return f"  {st.mark(OK)} No overlapping pairs found.\n"
    lines = [st.paint("Twins", "bold")]
    for p in d["pairs"]:
        lines += ["", f"  {st.mark(WARN)} {p['a']} and {p['b']} ({p['verdict']})", f"      {p['reason']}", f"      You use: {p['you_use']}"]
    return "\n".join(lines) + "\n"


def _r_why(d: dict[str, Any], st: Style) -> str:
    verdict = f"  Verdict: {d['verdict']}" + (f", {d['confidence']} confidence" if d["confidence"] else "")
    lines = [st.paint(f"{d['name']} ({d['kind']})", "bold"), "", verdict, *(f"  - {r}" for r in d["reasons"])]
    if d["twin"]:
        lines.append(f"  Compared with: {d['twin']}")
    lines.append(f"  Removing it frees: {_n(d['frees'])}" + ("" if d["frees"] is None else " tokens per session"))
    lines.append("  Referred to by: " + (", ".join(d["referenced_by"]) or "nothing"))
    if d["contains"]:
        lines.append("  Contains: " + ", ".join(d["contains"]))
    lines.append(f"  History: {_plural(d['history_days'], 'active day')}")
    return "\n".join(lines) + "\n"


def _r_hooks(d: dict[str, Any], st: Style) -> str:
    if not d["hooks"]:
        return f"  {st.mark(OK)} No hooks.\n"
    rows = [
        [h["name"], h["phase"], "can block" if h["can_block"] else "", h["runs"], "unknown" if h["bytes"] is None else f"{h['bytes']:,} B"]
        for h in d["hooks"]
    ]
    return "\n".join([st.paint("Hooks, by phase and weight", "bold"), "", *st.table(rows)]) + "\n"


def _r_clashes(d: dict[str, Any], st: Style) -> str:
    if not d["clashes"]:
        return f"  {st.mark(OK)} No clashes found.\n"
    lines = [st.paint("Clashes", "bold")]
    for c in d["clashes"]:
        lines += ["", f"  {st.mark(BAD)} {c['kind']}: {c['key']}", f"      {c['reason']}", "      Items: " + ", ".join(c["names"])]
    return "\n".join(lines) + "\n"


def _r_triggers(d: dict[str, Any], st: Style) -> str:
    if not d["files"]:
        return "Usage was not read in this scan, so trigger behaviour is unknown.\n"
    if not d["rows"]:
        return f"  {st.mark(OK)} Every skill fires at a reasonable rate.\n"
    rows = [[r["name"], " ".join(r["flags"]), f"{r['count']:,} uses"] for r in d["rows"]]
    return "\n".join([st.paint("Triggers", "bold"), "", *st.table(rows)]) + "\n"


def _r_text(d: dict[str, Any], st: Style) -> str:
    return str(d["text"]) if "text" in d else f"{d['answer']}\n"


RENDER: dict[str, Callable[[dict[str, Any], Style], str]] = {
    "doctor": _r_doctor, "cost": _r_cost, "unused": _r_unused, "twins": _r_twins, "why": _r_why, "hooks": _r_hooks,
    "clashes": _r_clashes, "triggers": _r_triggers, "explain": _r_text, "ask": _r_text,
}  # fmt: skip
BUILD: dict[str, Callable[[Scan, str | None], dict[str, Any]]] = {
    "doctor": _doctor, "cost": _cost, "unused": _unused, "twins": _twins, "why": _why, "hooks": _hooks,
    "clashes": _clashes, "triggers": _triggers, "explain": _explain, "ask": _ask,
}  # fmt: skip


def _scrub(value: Any) -> Any:
    """Redact every string in a result (JSON numbers must stay numbers, so the dumped text is not redacted)."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list | tuple):
        return [_scrub(v) for v in value]
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items()}
    return value


def run(name: str, s: Scan, arg: str | None, *, as_json: bool, st: Style) -> str:
    """The redacted text a read-only command prints."""
    built = _scrub(BUILD[name](s, arg))
    return json.dumps(built, indent=2) + "\n" if as_json else RENDER[name](built, st)


def clean(s: Scan, out: Path, force: bool) -> str:
    """Write the removal checklist (the same text `report --cleanup` writes). Never touches settings."""
    if out.exists() and not force:
        raise ReportError(f"{out} already exists; pass --force to overwrite it.")
    try:
        write_private(out, render_cleanup(s.data, top=5))
    except OSError:
        raise ReportError(f"Could not write {out}.") from None
    return f"Wrote the removal checklist to {out.resolve()}\nConstellation never edits your config; make each change by hand.\n"
