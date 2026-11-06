"""Keys read from the terminal, and the Action a key press can end a page with."""

import re
from collections.abc import Callable, Iterator
from typing import NamedTuple


class Action(NamedTuple):
    kind: str  # "run", "more", "version", "update", "back", "quit", "interrupt", or an Analyze action
    choice: int = 0


_NAMED = {
    b"": "q",  # EOF
    b"\x1b[A": "up",
    b"\x1b[B": "down",
    b"\x1b[C": "right",
    b"\x1b": "esc",
    b"\r": "enter",
    b"\n": "enter",
    b"\x03": "ctrl-c",
    b"\x04": "q",
}


def parse_key(data: bytes) -> str:
    if data in _NAMED:
        return _NAMED[data]
    return chr(data[0]).lower() if len(data) == 1 and data[0] < 128 else ""


_PARTS = re.compile(rb"\x1b\[[0-9;]*[A-Za-z~]|\x1b|[\x00-\x7f]|[\x80-\xff]+")


def split_keys(data: bytes) -> list[bytes]:
    """One terminal read can hold several key presses (fast repeat, paste); cut it into single keys."""
    return _PARTS.findall(data)


def key_stream(read: Callable[[], bytes]) -> Iterator[str]:
    """Keys from successive reads; an empty read is end of input and ends the stream with a quit."""
    while True:
        data = read()
        if not data:
            yield "q"
            return
        for part in split_keys(data):
            yield parse_key(part)
