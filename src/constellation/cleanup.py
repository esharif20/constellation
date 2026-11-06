"""The Clean dry run: every Item the verdicts would propose, grouped, with what it frees (a Scan in, lines out). Nothing is deleted."""

import os
from pathlib import Path
from typing import NamedTuple

from .cli_reports import Scan, Style
from .keys import Action
from .redact import redact
from .verdict import totals

TIERS = ("redundant", "could_go", "review")
RED, AMBER, BLUE, MAGENTA, DIM = "38;5;167", "38;5;179", "38;5;110", "38;5;139", "2"
_SHADE = {"redundant": RED, "could_go": AMBER}
_ACTIONS = {
    "enter": "why",
    "right": "why",
    " ": "toggle",
    "p": "pin",
    "a": "write",
    "esc": "back",
    "left": "back",
    "b": "back",
    "q": "back",
}
FOOTER = "↑↓ | Enter Why | Space Toggle | P Pin | A Write checklist | Esc/Q Back"
PROTECTED = "Protected (pinned)"
HEADER = "Constellation never edits your config. Every change below is yours to make by hand."


class Prop(NamedTuple):
    id: str
    name: str
    group: str  # the plugin that holds it, else its kind
    tier: str
    label: str
    confidence: str
    saves: int | None
    reasons: tuple[str, ...]


def _groups(props: list[Prop]) -> list[tuple[str, list[Prop], int]]:
    """(group, its Items by saving, subtotal) with the biggest subtotal first."""
    by: dict[str, list[Prop]] = {}
    for p in props:
        by.setdefault(p.group, []).append(p)
    out = [(g, sorted(ps, key=lambda p: (-(p.saves or 0), p.name)), sum(p.saves or 0 for p in ps)) for g, ps in by.items()]
    return sorted(out, key=lambda g: (-g[2], g[0]))


def proposals(s: Scan) -> tuple[list[Prop], list[Prop]]:
    """(proposed, protected): what the verdicts would let go, and the pinned Items, which are never proposed. Both in display order."""
    owner = {r["target"]: s.label(r["source"]) for r in s.data.get("relations") or [] if r["kind"] == "contains"}
    kind = {i["id"]: i["kind"] for i in s.data["items"]}
    evidence = s.found.evidence.items
    proposed: list[Prop] = []
    protected: list[Prop] = []
    for id_, a in s.found.assessments.items():
        pinned = id_ in evidence and evidence[id_].pinned
        if pinned or a.tier in TIERS:
            conf = a.confidence or ""
            p = Prop(id_, s.names[id_], owner.get(id_, kind[id_]), a.tier, a.label, conf, a.saves, tuple(r.text for r in a.reasons))
            (protected if pinned else proposed).append(p)
    return [p for _, ps, _ in _groups(proposed) for p in ps], [p for _, ps, _ in _groups(protected) for p in ps]


def reclaimable(s: Scan) -> tuple[int, int, int]:
    """(low, high, Items of unknown size): the same range the doctor and the Brief print."""
    t = totals(s.found.assessments)
    return t["low"], t["high"], t["unknown"]


def step(index: int, key: str, count: int) -> int | Action:
    if key == "up":
        return max(0, index - 1)
    if key == "down":
        return min(count - 1, index + 1)
    if key == "ctrl-c":
        return Action("back")
    if key in _ACTIONS and (count or _ACTIONS[key] == "back"):
        return Action(_ACTIONS[key], index)
    return index


def _c(st: Style, code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if st.color else text


def _fit(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def _saves(n: int | None) -> str:
    return "unknown" if n is None else f"{n:,}"


def headline(props: list[Prop], checked: frozenset[str], rng: tuple[int, int, int]) -> str:
    n = sum(p.saves or 0 for p in props if p.id in checked)
    low, high, unknown = rng
    extra = f"; {unknown} unmeasured" if unknown else ""
    return f"Could free ~{n:,} tokens per session ({low:,} to {high:,}{extra})"


def _row(p: Prop, on: bool, mark: str, tail: str, shade: str, st: Style) -> str:
    row = _fit(f"  {'▶' if on else ' '} {mark} {p.name}  {tail}", st.width)
    return _c(st, shade, row) if on else row.replace(tail, _c(st, shade, tail))


def body(props: list[Prop], n_proposed: int, checked: frozenset[str], index: int, st: Style) -> tuple[list[str], int]:
    """Every line of the grouped list and the line the selected Item is on."""
    sections = [(g, ps, f", ~{sub:,} tokens", False) for g, ps, sub in _groups(props[:n_proposed])]
    sections += [(PROTECTED, props[n_proposed:], "", True)] if props[n_proposed:] else []
    lines: list[str] = []
    at = pos = 0
    for group, ps, extra, protected in sections:
        lines.append(_c(st, "1", f"  {group}") + _c(st, DIM, f"  {len(ps)} Item{'' if len(ps) == 1 else 's'}{extra}"))
        for p in ps:
            if pos == index:
                at = len(lines)
            mark = "[-]" if protected else "[x]" if p.id in checked else "[ ]"
            tail = "pinned: kept" if protected else f"{p.label} · {p.confidence} · {_saves(p.saves)} · {p.reasons[0]}"
            lines.append(_row(p, pos == index, mark, tail, DIM if protected else _SHADE.get(p.tier, BLUE), st))
            pos += 1
    return lines, at


def render(
    props: list[Prop], n_proposed: int, checked: frozenset[str], index: int, st: Style, rng: tuple[int, int, int], size: int = 14
) -> list[str]:
    lines, at = body(props, n_proposed, checked, index, st)
    start = max(0, min(at - size // 2, len(lines) - size))
    head = _c(st, "1;" + MAGENTA, "Clean") + _c(st, DIM, "  (dry run: nothing is deleted)")
    return [
        head,
        _c(st, DIM, _fit(headline(props[:n_proposed], checked, rng), st.width)),
        "",
        *lines[start : start + size],
        "",
        _c(st, DIM, _fit(FOOTER, st.width)),
    ]


def why_text(proposed: list[Prop], protected: list[Prop], rng: tuple[int, int, int], st: Style) -> str:
    """The non-interactive dry run with every reason (clean --dry-run --why)."""
    lines = [st.title("Clean: dry run (nothing is deleted)"), "", "  " + headline(proposed, frozenset(p.id for p in proposed), rng)]
    for group, ps, subtotal in _groups(proposed):
        lines += ["", st.title(f"{group}  ({len(ps)} Item{'' if len(ps) == 1 else 's'}, ~{subtotal:,} tokens)")]
        for p in ps:
            lines.append(f"  {p.name}: {p.label}, {p.confidence} confidence, saves {_saves(p.saves)}")
            lines += [f"      - {r}" for r in p.reasons]
    if protected:
        lines += ["", st.title(f"{PROTECTED}  ({len(protected)})")] + [f"  {p.name}: kept because you pinned it" for p in protected]
    if not proposed:
        lines += ["", "  Nothing to propose."]
    return "\n".join(lines) + "\n"


def checklist(chosen: list[Prop]) -> str:
    """The markdown checklist for the chosen Items; the user makes each change by hand."""
    rows = [f"- [ ] {redact(p.name)} ({p.group}): {redact(p.reasons[0])} Saves {_saves(p.saves)} always-on tokens." for p in chosen]
    return (
        "\n".join([HEADER, "", "# Constellation cleanup checklist", "", "## Chosen in the Clean view", "", *(rows or ["None chosen."])])
        + "\n"
    )


def write_new(path: Path, text: str) -> None:
    """Write a private (0600) file that must not exist yet. Raises FileExistsError or OSError."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)


class View:
    """The Clean page's state: the proposals, which of them are in the checklist, and the verdict range."""

    def __init__(self, scan: Scan, keep: frozenset[str] | None = None):
        proposed, protected = proposals(scan)
        self.props = proposed + protected
        self.n = len(proposed)
        self.rng = reclaimable(scan)
        ids = frozenset(p.id for p in proposed)
        self.checked = ids if keep is None else ids & keep

    def lines(self, index: int, st: Style) -> list[str]:
        return render(self.props, self.n, self.checked, index, st, self.rng)

    def key(self, index: int, key: str) -> int | Action:
        """Like `step`, but Space flips the Item in or out of the checklist here (pinned Items cannot be checked)."""
        result = step(index, key, len(self.props))
        if not isinstance(result, Action):
            return result
        if result.kind == "toggle":
            if index < self.n:
                self.checked = self.checked ^ {self.props[index].id}
            return index
        return result

    def chosen(self) -> list[Prop]:
        return [p for p in self.props[: self.n] if p.id in self.checked]
