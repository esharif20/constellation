"""The one dim line printed after a command in a terminal: what to run next, picked from what the command just found."""

import shlex
from collections.abc import Mapping
from typing import Any

from .cli_reports import Style

_FIXED = {"cost": "clean", "scan": "status", "clean": "open", "status": "unused", "doctor": "cost"}


def next_step(command: str, result: Mapping[str, Any] | None) -> str | None:
    """A suggested follow-up command for `command`, or None. `result` is the command's built data (rows for unused, hits for find)."""
    if command in _FIXED:
        return f"constellation {_FIXED[command]}"
    rows = (result or {}).get({"unused": "rows", "find": "hits"}.get(command, ""))
    if rows and rows[0].get("name"):
        return f"constellation why {shlex.quote(str(rows[0]['name']))}"
    return None


def hint_line(st: Style, command: str, result: Mapping[str, Any] | None) -> str | None:
    step = next_step(command, result)
    if step is None:
        return None
    text = f"Next: {step}"
    return f"\033[2m{text}\033[0m" if st.color else text
