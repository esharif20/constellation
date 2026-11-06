"""No-args menu, in the style of Mole: a pure key -> state machine (`step`), pure frames (`render`) and a thin terminal layer.

Every entry just runs an existing subcommand through `cli.main`; nothing here reads your setup except through those commands.
"""

import contextlib
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from . import banner
from .cli_reports import Style
from .frontdoor import main_entries, more_entries
from .keys import Action

ENTRIES = main_entries(False)
MORE = more_entries()
FOOTERS = ("↑↓ | Enter | M More | V Version | U Update | Q Quit", "↑↓ | Enter | M More | Q Quit", "Enter | M | Q Quit")
MORE_FOOTERS = ("↑↓ | Enter | Esc Back | Q Quit", "Enter | Esc Back | Q Quit")
FOOTER, MORE_FOOTER = FOOTERS[0], MORE_FOOTERS[0]
URL = "github.com/esharif20/constellation"
DAY = 86400
PORT = 8765
CLEAR = "\033[2J\033[H"
HIDE = "\033[?25l"
SHOW = "\033[?25h"
OLIVE, STEEL, TEAL, DIM = "38;5;143", "38;5;110", "38;5;109", "2"
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
        return Action("interrupt" if top else "back")
    if key in ("esc", "left", "b") and not top:
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


def _footer(variants: tuple[str, ...], width: int) -> str:
    """The longest key hint that fits, so a narrow terminal never cuts off `Q Quit`."""
    return next((v for v in variants if len(v) <= width), variants[-1])


def render(
    index: int,
    st: Style,
    version: str,
    entries: tuple[tuple[str, str], ...] = ENTRIES,
    top: bool = True,
    note: str = "",
    height: int | None = None,
) -> list[str]:
    """The menu frame. With a `height`, a long list shows a window around the selection, so the frame never scrolls the screen."""
    name_w = max(len(name) for name, _ in entries) + 1
    num_w = len(str(len(entries)))
    rows = []
    for i, (name, hint) in enumerate(entries):
        row = _fit(f"{'➤' if i == index else ' '} {f'{i + 1}.'.ljust(num_w + 1)} {name:<{name_w}} {hint}", st.width - 2)
        rows.append("  " + (_c(st, TEAL, row) if i == index else row))
    head = ["", *banner.render(st, version), "", *(["  " + _c(st, DIM, _fit(note, st.width - 2)), ""] if note else [])]
    foot = ["", "  " + _c(st, DIM, _fit(_footer(FOOTERS if top else MORE_FOOTERS, st.width - 2), st.width - 2))]
    room = None if height is None else height - 1 - len(head) - len(foot)  # the last screen row stays free: the frame ends in a newline
    if room is not None and room < len(rows):
        room = max(room, 3)
        start = max(0, min(index - room // 2, len(rows) - room))
        rows = rows[start : start + room]
    return [*head, *rows, *foot]


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
        if key == "resize":  # the old frame has been re-wrapped by the terminal, so draw a new one from the top
            first = lines_for(index)
            write(CLEAR + "\r\n".join(first) + "\r\n")
            continue
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
