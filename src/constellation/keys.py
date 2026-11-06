"""Keys read from the terminal, and the Action a key press can end a page with."""

import re
from collections.abc import Callable, Iterator
from typing import NamedTuple


class Action(NamedTuple):
    kind: str  # "run", "more", "version", "update", "back", "quit", "interrupt", or an Analyze action
    choice: int = 0


RESIZE = b"\x1b[8;0;0t"  # what the terminal reader says when the window changed size (no real key sends it)

_NAMED = {
    b"": "q",  # EOF
    b"\x1b[A": "up",
    b"\x1b[B": "down",
    b"\x1b[C": "right",
    b"\x1b[D": "left",
    b"\x7f": "backspace",
    b"\x08": "backspace",
    b"\x1b": "esc",
    b"\r": "enter",
    b"\n": "enter",
    b"\x03": "ctrl-c",
    b"\x04": "q",
    RESIZE: "resize",
}


class Cancel(Exception):
    """The user pressed Esc (or Ctrl-C) at a prompt: do nothing and go back."""


def parse_key(data: bytes, fold: bool = True) -> str:
    """The key name for one key's bytes. `fold` lowercases letters (menus); typed text keeps case and reports end of input as "eof"."""
    if not fold and data in (b"", b"\x04"):
        return "eof"
    if data in _NAMED:
        return _NAMED[data]
    if len(data) == 1 and data[0] < 128:
        return chr(data[0]).lower() if fold else chr(data[0])
    return ""


def edit(text: str, key: str) -> tuple[str, str | None]:
    """One key at a text prompt: the new text and "done" (Enter) or "cancel" (Esc, Ctrl-C, end of input) when the prompt ends."""
    if key == "enter":
        return text, "done"
    if key in ("esc", "ctrl-c", "eof"):
        return text, "cancel"
    if key == "backspace":
        return text[:-1], None
    if len(key) == 1 and key.isprintable():
        return text + key, None
    return text, None


_PARTS = re.compile(rb"\x1b\[[0-9;]*[A-Za-z~]|\x1b|[\x00-\x7f]|[\x80-\xff]+")


def split_keys(data: bytes) -> list[bytes]:
    """One terminal read can hold several key presses (fast repeat, paste); cut it into single keys."""
    return _PARTS.findall(data)


def key_stream(read: Callable[[], bytes], fold: bool = True) -> Iterator[str]:
    """Keys from successive reads; an empty read is end of input and ends the stream with a quit ("eof" when not folding)."""
    while True:
        data = read()
        if not data:
            yield "q" if fold else "eof"
            return
        for part in split_keys(data):
            yield parse_key(part, fold)
