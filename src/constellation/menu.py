"""No-args menu: a pure key -> state machine (`step`) plus a thin raw-terminal layer. Each entry just runs an existing subcommand."""

import contextlib
import importlib.metadata
import os
import sys
import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, NamedTuple

from .cli_reports import Style, style_for_stdout

ENTRIES = (
    ("Analyze", "what costs context, what is unused, what clashes"),
    ("Doctor", "one-screen health of your setup and this install"),
    ("Clean", "build a cleanup checklist (nothing is deleted)"),
    ("Weekly", "what changed since last week"),
    ("Open map", "the interactive graph in your browser"),
    ("Update", "check for a newer version"),
)
_COMMANDS = ("doctor", "clean", "weekly", "open", "update")
DAY = 86400
_WORDS = {"q": "quit", "h": "help"}
_NUMBERS = {str(n): n - 1 for n in range(1, len(ENTRIES) + 1)}


class Action(NamedTuple):
    kind: str  # "run", "help", "quit" or "interrupt"
    choice: int = 0


def step(index: int, key: str) -> int | Action:
    """One key press: the new selected index, or the Action that ends the menu."""
    last = len(ENTRIES) - 1
    if key == "up":
        return max(0, index - 1)
    if key == "down":
        return min(last, index + 1)
    if key == "enter":
        return Action("run", index)
    if key == "q":
        return Action("quit")
    if key == "h":
        return Action("help")
    if key == "ctrl-c":
        return Action("interrupt")
    if key in _NUMBERS:
        return _NUMBERS[key]
    return index


def parse_key(data: bytes) -> str:
    named = {b"": "q", b"\x1b[A": "up", b"\x1b[B": "down", b"\r": "enter", b"\n": "enter", b"\x03": "ctrl-c", b"\x04": "q"}  # b"" is EOF
    if data in named:
        return named[data]
    return chr(data[0]).lower() if len(data) == 1 and data[0] < 128 else ""


def age_text(seconds: float | None) -> str:
    if seconds is None:
        return "no scan yet"
    days = int(seconds) // DAY
    return "today" if days == 0 else f"{days} day{'s' if days > 1 else ''} ago"


def render(index: int, st: Style, version: str, age: str) -> list[str]:
    rows = [f"{'➤' if i == index else ' '} {i + 1}  {name:<13} {text}" for i, (name, text) in enumerate(ENTRIES)]
    rows = [st.title(row) if i == index else row for i, row in enumerate(rows)]
    hint = "↑↓ or 1-6 · Enter run · h help · q quit"
    return [
        st.title(f"Constellation {version}") + " · your Claude Code setup, mapped",
        "",
        *(f"  {r}" for r in rows),
        "",
        f"  {hint}   last scan: {age}",
    ]


def plan(index: int, fresh: bool, config_dir: str) -> list[list[str]]:
    """The subcommands an entry runs, in order. Analyze scans offline first when there is no fresh scan."""
    if index == 0:
        return ([] if fresh else [["scan", config_dir, "--offline"]]) + [["doctor"], ["cost"], ["unused"]]
    return [[_COMMANDS[index - 1]]]


def choose(keys: Iterable[str], write: Callable[[str], object], lines_for: Callable[[int], list[str]]) -> Action:
    """Draw the frame, then redraw over it after each key until one ends the menu (running out of keys quits)."""
    index = 0
    first = lines_for(index)
    write("\r\n".join(first) + "\r\n")
    for key in keys:
        result = step(index, key)
        if isinstance(result, Action):
            return result
        index = result
        write(f"\033[{len(first)}F\033[J" + "\r\n".join(lines_for(index)) + "\r\n")
    return Action("quit")


def _answers(input_fn: Callable[[str], str]) -> Iterator[str]:
    try:
        while True:
            yield input_fn("number, h or q: ")
    except EOFError:
        return


def numbered(input_fn: Callable[[str], str], write: Callable[[str], object], lines_for: Callable[[int], list[str]]) -> Action:
    """No termios (Windows): list the entries and read a number, h or q."""
    write("\n".join(lines_for(-1)) + "\n")
    for line in _answers(input_fn):
        answer = line.strip().lower()
        if answer in _NUMBERS:
            return Action("run", _NUMBERS[answer])
        if answer in _WORDS:
            return Action(_WORDS[answer])
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


def launch(
    run: Callable[[list[str]], int],
    scan_file: Path = Path("constellation.json"),
    config_dir: str | None = None,
    *,
    st: Style,
    confirm: Callable[[str], str] = input,
    raw: Callable[[], AbstractContextManager[None]] | None = None,
    keys: Iterable[str] | None = None,
    now: Callable[[], float] = time.time,
) -> int:
    """Show the menu, then run the chosen subcommands through `run` (cli.main). Returns the exit code."""
    age = scan_age(scan_file, now())
    version = importlib.metadata.version("constellation-cli")

    def lines_for(index: int) -> list[str]:
        return render(index, st, version, age_text(age))

    def write(text: str) -> None:
        sys.stdout.write(text)
        sys.stdout.flush()

    if keys is None:
        action = numbered(confirm, write, lines_for)
    else:
        with (raw or contextlib.nullcontext)():
            action = choose(keys, write, lines_for)
    if action.kind == "interrupt":
        return 130
    if action.kind == "help":
        return run(["--help"])
    if action.kind == "quit":
        return 0
    steps = plan(action.choice, age is not None and age < DAY, config_dir or str(Path.home() / ".claude"))
    if steps[0][0] == "scan":
        answer = confirm(f"No fresh scan. Run `constellation {' '.join(steps[0])}` (reads {steps[0][1]} locally, sends nothing)? [y/N] ")
        if answer.strip().lower() != "y":
            return 0
    for argv in steps:
        code = run(argv)
        if code:
            return code
    return 0


def terminal() -> tuple[Callable[[], AbstractContextManager[None]], Iterable[str]] | None:
    """Raw-mode context and the stream of keys for the real terminal, or None where termios is missing."""
    try:
        import termios
        import tty
    except ImportError:
        return None
    fd = sys.stdin.fileno()
    return (lambda: raw_mode(fd, termios, tty)), iter(lambda: parse_key(os.read(fd, 8)), None)


def open_menu(run: Callable[[list[str]], int]) -> int:
    """Entry point used by cli.main when stdin and stdout are both a TTY. Ctrl-C exits 130 with the terminal restored."""
    term = terminal()
    try:
        return launch(run, st=style_for_stdout(), raw=term[0] if term else None, keys=term[1] if term else None)
    except KeyboardInterrupt:
        return 130
