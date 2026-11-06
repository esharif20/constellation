"""Opening the graph in a browser reliably: wait for the server, use the platform's own opener, and print a clickable link.

Everything that touches the machine (platform, runner, clock, socket) is passed in, so tests start no browser and no server.
"""

import os
import subprocess
import sys
import time
import webbrowser
from collections.abc import Callable, Mapping
from typing import Any

_COMMANDS = {"darwin": "open", "linux": "xdg-open"}
_LINK_TERMS = {"iTerm.app", "WezTerm", "vscode", "ghostty", "Hyper"}


def wait_ready(
    can_connect: Callable[[], bool],
    alive: Callable[[], bool],
    *,
    timeout: float = 5.0,
    every: float = 0.1,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], object] = time.sleep,
) -> bool:
    """True once the server accepts connections; False when it died (port in use) or `timeout` seconds passed."""
    end = clock() + timeout
    while alive():
        if can_connect():
            return True
        if clock() >= end:
            return False
        sleep(every)
    return False


def open_url(
    url: str,
    platform: str = sys.platform,
    run: Callable[..., Any] = subprocess.run,
    startfile: Callable[[str], object] | None = None,
    fallback: Callable[[str], bool] = webbrowser.open,
) -> bool:
    """Open `url` with `open` (macOS), `xdg-open` (Linux) or os.startfile (Windows), else webbrowser. True if something took it."""
    try:
        if platform == "win32":
            (startfile or getattr(os, "startfile"))(url)  # noqa: B009 - os.startfile exists only on Windows
            return True
        if platform in _COMMANDS:
            run([_COMMANDS[platform], url], check=True, capture_output=True, timeout=10)
            return True
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        return bool(fallback(url))
    except webbrowser.Error:
        return False


def hyperlink(url: str, env: Mapping[str, str], tty: bool) -> str:
    """`url` as an OSC-8 clickable link where the terminal is known to support it, else the plain text."""
    vte = env.get("VTE_VERSION", "")
    known = env.get("TERM_PROGRAM") in _LINK_TERMS or "KITTY_WINDOW_ID" in env or (vte.isdigit() and int(vte) >= 5000)
    return f"\033]8;;{url}\033\\{url}\033]8;;\033\\" if tty and known else url
