"""Scan progress: a pure event type and renderer, plus a small stderr reporter. Never writes to stdout."""

import math
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Self, TextIO

LABELS = {
    "skills": "reading config and skills",
    "mcp": "reading hooks/MCP",
    "usage": "reading transcripts",
    "analyze": "counting tokens, grouping clusters",
    "write": "writing",
}
ETA_AFTER = 2.0  # seconds of data before an estimate is worth showing
REDRAW = 0.1
HIDE, SHOW, CLEAR_LINE = "\x1b[?25l", "\x1b[?25h", "\x1b[K"


@dataclass(frozen=True)
class ProgressEvent:
    phase: str
    done: int
    total: int
    size: int = 0  # bytes read so far (transcripts only)


Progress = Callable[[ProgressEvent], None]


def _bytes(n: int) -> str:
    return f"{n / 1_000_000:.1f} MB" if n >= 1_000_000 else f"{n / 1000:.0f} KB" if n >= 1000 else f"{n} B"


def _eta(seconds: float) -> str:
    s = math.ceil(seconds)
    return f"~{s}s left" if s < 60 else f"~{s // 60}m{s % 60:02d}s left"


def render_bar(event: ProgressEvent, width: int, started: float, now: float, color: bool) -> str:
    """`[██████░░░░░░░░░░] 41%  reading transcripts 87/212 files 4.1 MB  ~12s left` (no ETA before 2 s of data)."""
    total = max(event.total, 0)
    done = min(max(event.done, 0), total) if total else max(event.done, 0)
    filled = width * done // total if total else 0
    full, empty = "█" * filled, "░" * (width - filled)
    bar = f"\x1b[32m{full}\x1b[2m{empty}\x1b[0m" if color else full + empty
    text = f"{LABELS.get(event.phase, event.phase)}"
    if total:
        text += f" {done}/{total}" + (" files" if event.phase == "usage" else "")
    if event.size:
        text += f" {_bytes(event.size)}"
    elapsed = now - started
    if total and 0 < done < total and elapsed >= ETA_AFTER:
        text += f"  {_eta(elapsed / done * (total - done))}"
    return f"[{bar}] {100 * done // total if total else 0}%  {text}"


class Reporter:
    """A TTY gets one redrawn line; anything else gets a plain line each time a phase ends."""

    def __init__(
        self,
        title: str,
        tty: bool,
        color: bool,
        columns: int = 80,
        out: TextIO | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.title, self.tty, self.color, self.out, self.clock = title, tty, color, out or sys.stderr, clock
        self.width = 16 if columns >= 90 else 8
        self.last: ProgressEvent | None = None
        self.started = self.drawn = 0.0

    def __enter__(self) -> Self:
        if self.tty:
            self.out.write(HIDE)
            self.out.flush()
        return self

    def __exit__(self, kind: type[BaseException] | None, error: BaseException | None, trace: TracebackType | None) -> None:
        if self.tty:
            self.out.write("\r" + CLEAR_LINE + SHOW)
        elif self.last:
            self._milestone(self.last)
        self.out.flush()

    def _milestone(self, event: ProgressEvent) -> None:
        self.out.write(f"{LABELS.get(event.phase, event.phase)}… {event.done}\n")

    def __call__(self, event: ProgressEvent) -> None:
        now = self.clock()
        new = self.last is None or self.last.phase != event.phase
        if new:
            if self.last and not self.tty:
                self._milestone(self.last)
            self.started, self.drawn = now, 0.0
        self.last = event
        if self.tty and (new or now - self.drawn >= REDRAW or event.done >= event.total):
            self.drawn = now
            self.out.write("\r" + self.title + "  " + render_bar(event, self.width, self.started, now, self.color) + CLEAR_LINE)
            self.out.flush()
