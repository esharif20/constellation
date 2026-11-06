"""The Analyze page: Items ranked by what they cost at session start, as coloured bars (pure: rows in, lines out)."""

from typing import Any, NamedTuple

from .cli_reports import Style
from .keys import Action

RED, BLUE, GREEN, MAGENTA, DIM = "38;5;167", "38;5;110", "38;5;143", "38;5;139", "2"
FOOTER = "↑↓→ | Enter | R Refresh | O Open | P Preview | F File | Esc/Q Quit"
_ACTIONS = {"enter": "why", "right": "why", "r": "refresh", "o": "open", "p": "preview", "f": "file", "esc": "back", "q": "back"}


class Row(NamedTuple):
    id: str
    name: str
    tokens: int
    path: str


def rows_from(cost: dict[str, Any], scan: dict[str, Any]) -> list[Row]:
    """The measured Items of `cost --json`, biggest first, with the source file each came from."""
    source = {i["id"]: i.get("source") or "" for i in scan.get("items", [])}
    return [Row(r["id"], r["name"], r["tokens"], source.get(r["id"], "")) for r in cost["top"] if r["tokens"] is not None]


def step(index: int, key: str, count: int) -> int | Action:
    if key == "up":
        return max(0, index - 1)
    if key == "down":
        return min(count - 1, index + 1)
    if key == "ctrl-c":
        return Action("interrupt")
    if key in _ACTIONS and (count or _ACTIONS[key] in ("refresh", "back")):
        return Action(_ACTIONS[key], index)
    return index


def _c(st: Style, code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if st.color else text


def _shade(tokens: int, top: int) -> str:
    return RED if tokens * 10 >= top * 6 else BLUE if tokens * 5 >= top else GREEN


def _fit(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def render(rows: list[Row], index: int, st: Style, total: int | None, status: str) -> list[str]:
    top = max((r.tokens for r in rows), default=0)  # pragma: no mutate (equivalent: with no rows nothing uses it)
    count = "unknown" if total is None else f"{total:,}"
    head = _c(st, "1;" + MAGENTA, "Analyze Setup") + _c(st, DIM, _fit(f"  ({count} tokens at session start)", st.width - 13))
    lines = [head, _c(st, DIM, _fit(f"What loads at the start of every session, biggest first:  {status}", st.width)), ""]
    longest = max((len(r.name) for r in rows), default=0)  # pragma: no mutate (equivalent: with no rows nothing uses it)
    name_w = min(longest, max(10, st.width // 3))
    widest = max((len(f"{r.tokens:,}") for r in rows), default=0)  # pragma: no mutate (equivalent: with no rows nothing uses it)
    size_w = widest + 4
    bar_w = max(4, min(24, st.width - name_w - size_w - 15))
    for i, r in enumerate(rows):
        on = i == index
        cells = "█" * max(1, round(bar_w * r.tokens / top))
        share = "--" if not total else f"{round(100 * r.tokens / total)}%"
        shade = _shade(r.tokens, top)
        name = _fit(r.name, name_w).ljust(name_w)
        lines.append(
            f"{_c(st, BLUE, '▶') if on else ' '} {_c(st, BLUE, f'{i + 1:>2}.') if on else f'{i + 1:>2}.'} "
            f"{_c(st, shade, cells)}{' ' * (bar_w - len(cells))} {share:>4} | "
            f"{_c(st, BLUE, name) if on else name} {_c(st, shade, f'{r.tokens:,} tok'.rjust(size_w))}"
        )
    return [*lines, "", _c(st, DIM, _fit(FOOTER, st.width))]


class View:
    """The Analyze page's rows and the total they are part of."""

    def __init__(self, rows: list[Row], total: int | None):
        self.rows, self.total = rows, total

    def lines(self, index: int, st: Style) -> list[str]:
        return render(self.rows, index, st, self.total, f"{len(self.rows)} Items")

    def key(self, index: int, key: str) -> int | Action:
        return step(index, key, len(self.rows))
