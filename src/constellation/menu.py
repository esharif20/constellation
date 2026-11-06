"""No-args menu, in the style of Mole: a pure key -> state machine (`step`), pure frames (`render`, `banner`) and a thin terminal layer.

Every entry just runs an existing subcommand through `cli.main`; nothing here reads your setup except through those commands.
"""

import contextlib
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from .cli_reports import Style
from .keys import Action

ENTRIES = (
    ("Open", "The graph of your setup, in the browser"),
    ("Analyze", "Rank what loads at the start of every session"),
    ("Find", "Say what a forgotten skill does"),
    ("Clean", "A cleanup checklist with verdicts"),
    ("Status", "Health, this week, what went quiet"),
)
MORE = (
    ("Twins", "Overlapping skills and which you use"),
    ("Weekly", "What changed since the last scan"),
    ("Remove preview", "What breaks if you remove an Item"),
    ("Share", "Write a public-safe snapshot"),
    ("Doctor --env", "Check Python, install and key"),
)
FOOTER = "↑↓ | Enter | M More | V Version | U Update | Q Quit"
MORE_FOOTER = "↑↓ | Enter | Esc Back | Q Quit"
URL = "github.com/esharif20/constellation"
DAY = 86400
PORT = 8765
CLEAR = "\033[2J\033[H"
HIDE = "\033[?25l"
SHOW = "\033[?25h"
OLIVE, STEEL, TEAL, DIM = "38;5;143", "38;5;110", "38;5;109", "2"
FONT = {
    "C": (" _ ", "|  ", "|_ "),
    "O": (" _ ", "| |", "|_|"),
    "N": ("   ", "|\\|", "| |"),
    "S": (" _ ", "|_ ", " _|"),
    "T": ("___", " | ", " | "),
    "E": (" _ ", "|_ ", "|_ "),
    "L": ("   ", "|  ", "|_ "),
    "A": (" _ ", "|_|", "| |"),
    "I": ("___", " | ", "___"),
}
ART = tuple(" ".join(FONT[ch][row] for ch in "CONSTELLATION") for row in range(3))
_NUMBERS = {str(n): n - 1 for n in range(1, 10)}


def step(index: int, key: str, count: int = len(ENTRIES), top: bool = True) -> int | Action:
    """One key press: the new selected index, or the Action that ends the page. `top` is the main menu (More, Version, Update)."""
    if key == "up":
        return max(0, index - 1)
    if key == "down":
        return min(count - 1, index + 1)
    if key == "enter":
        return Action("run", index)
    if key == "q":
        return Action("quit")
    if key == "ctrl-c":
        return Action("interrupt")
    if key == "esc" and not top:
        return Action("back")
    if top and key in ("m", "v", "u"):
        return Action({"m": "more", "v": "version", "u": "update"}[key])
    if key in _NUMBERS and _NUMBERS[key] < count:
        return _NUMBERS[key]
    return index


def _c(st: Style, code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if st.color else text


def _fit(text: str, width: int) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def banner(st: Style, version: str) -> list[str]:
    tagline = f"Map your Claude setup · {version}"
    if st.width < len(ART[0]) + 3:
        return [_c(st, OLIVE, _fit("  CONSTELLATION", st.width)), _c(st, DIM, _fit(f"  {tagline}", st.width))]
    art = [_c(st, OLIVE, row) for row in ART]
    if st.width >= len(ART[0]) + 2 + len(URL):
        return [art[0], f"{art[1]}  {_c(st, STEEL, URL)}", f"{art[2]}  {_c(st, OLIVE, tagline)}"]
    return [*art, _c(st, STEEL, _fit(URL, st.width)), _c(st, OLIVE, _fit(tagline, st.width))]


def render(index: int, st: Style, version: str, entries: tuple[tuple[str, str], ...] = ENTRIES, top: bool = True) -> list[str]:
    name_w = max(len(name) for name, _ in entries) + 1
    rows = []
    for i, (name, hint) in enumerate(entries):
        row = _fit(f"{'➤' if i == index else ' '} {i + 1}. {name:<{name_w}} {hint}", st.width - 2)
        rows.append("  " + (_c(st, TEAL, row) if i == index else row))
    return ["", *banner(st, version), "", *rows, "", "  " + _c(st, DIM, _fit(FOOTER if top else MORE_FOOTER, st.width - 2))]


def choose(
    keys: Iterator[str],
    write: Callable[[str], object],
    lines_for: Callable[[int], list[str]],
    stepper: Callable[[int, str], int | Action] = step,
    index: int = 0,
) -> Action:
    """Draw the frame, then redraw over it after each key until one ends the page (running out of keys quits)."""
    first = lines_for(index)
    write("\r\n".join(first) + "\r\n")
    for key in keys:
        result = stepper(index, key)
        if isinstance(result, Action):
            return result
        index = result
        write(f"\033[{len(first)}F\033[J" + "\r\n".join(lines_for(index)) + "\r\n")
    return Action("quit")


def _answers(input_fn: Callable[[str], str], prompt: str) -> Iterator[str]:
    try:
        while True:
            yield input_fn(prompt)
    except EOFError:
        return


def numbered(
    input_fn: Callable[[str], str], write: Callable[[str], object], lines_for: Callable[[int], list[str]], count: int, words: dict[str, str]
) -> Action:
    """No termios (Windows): list the entries and read a number or one of `words` (letter -> action kind)."""
    write("\n".join(lines_for(-1)) + "\n")
    prompt = f"number, {', '.join(w for w in words if w != 'q')} or q: "
    for line in _answers(input_fn, prompt):
        answer = line.strip().lower()
        if answer in _NUMBERS and _NUMBERS[answer] < count:
            return Action("run", _NUMBERS[answer])
        if answer in words:
            return Action(words[answer])
    return Action("quit")


@contextlib.contextmanager
def raw_mode(fd: int, termios: Any, tty: Any) -> Iterator[None]:
    saved = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)


def scan_age(path: Path, now: float) -> float | None:
    try:
        return max(0.0, now - path.stat().st_mtime)
    except OSError:
        return None
