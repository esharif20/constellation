"""What the menu offers: the main entries, the More page that reaches every other command, and the first-run wording.

Pure data and text; `session.py` does the asking and running. A command that needs an answer lists where it goes as `{ask}` (one
argument) or `{ask*}` (split on spaces); `{cfg}` is the Claude config directory.
"""

import re
from dataclasses import dataclass
from typing import Any

NO_SCAN = "No scan yet. Start with 1 Scan."


def main_entries(first_run: bool) -> tuple[tuple[str, str], ...]:
    return (
        ("Scan", "Start here: read ~/.claude and build your map" if first_run else "Read ~/.claude, build or refresh the scan"),
        ("Open", "The graph of your setup, in the browser"),
        ("Analyze", "Rank what loads at the start of every session"),
        ("Find", "Say what a forgotten skill does"),
        ("Clean", "A cleanup checklist with verdicts"),
        ("Status", "Health, this week, what went quiet"),
    )


@dataclass(frozen=True)
class Cmd:
    name: str
    group: str  # as in `constellation --help`
    hint: str
    argv: tuple[str, ...]
    ask: str | None = None  # the question put before running, when the command needs an answer
    scan: bool = True  # needs a saved scan


def _c(name: str, group: str, hint: str, *argv: str, ask: str | None = None, scan: bool = True) -> Cmd:
    return Cmd(name, group, hint, argv, ask, scan)


MORE = (
    _c("Doctor", "Look", "One-screen health check", "doctor"),
    _c("Cost", "Look", "What loads at session start", "cost"),
    _c("Unused", "Look", "Items not used lately", "unused"),
    _c("Twins", "Look", "Overlapping skills and which you use", "twins"),
    _c("Why", "Look", "Why one Item has its verdict", "why", "{ask}", ask="Which Item?"),
    _c("Remove preview", "Look", "What breaks if you remove an Item", "remove-preview", "{ask}", ask="Which Item?"),
    _c("Hooks", "Look", "Every hook, ranked", "hooks"),
    _c("Clashes", "Look", "Hook, MCP and trigger collisions", "clashes"),
    _c("Triggers", "Look", "Skills that never or over-fire", "triggers"),
    _c("Explain", "Look", "Plain-English summary of the setup", "explain"),
    _c("Ask", "Look", "Ask a question (local rules, no model)", "ask", "{ask}", ask="What do you want to know?"),
    _c("Report", "Look", "Plain-text report of the scan", "report"),
    _c("Assess", "Look", "Every verdict, as JSON", "assess"),
    _c("Weekly", "Look", "What changed since the last scan", "weekly"),
    _c("Diff", "Look", "Items changed between two scans", "diff", "{ask*}", ask="Old and new scan files?"),
    _c("Delta", "Look", "Tokens and Overlaps between two scans", "delta", "{ask*}", ask="Before and after scan files?"),
    _c("Preview", "Look", "What a downloaded plugin would add", "preview", "{ask}", ask="Which folder?"),
    _c("Profile", "Look", "What one project really uses", "profile", "{ask}", ask="Which project?", scan=False),
    _c("Expand", "Look", "Tools of one local MCP server", "expand", "{ask}", "--config-dir", "{cfg}", ask="Which Item id?"),
    _c("Review", "Act", "Go through Suggestions one by one", "review", "--dry-run"),
    _c("Share", "Act", "Write a public-safe snapshot", "share"),
    _c("Export", "Act", "Show the public snapshot (dry run)", "export", "--public", "--dry-run"),
    _c("Scan preview", "Map", "Show what a scan would send and write", "scan", "{cfg}", "--dry-run", scan=False),
    _c("Purge", "Manage", "Items only used by idle projects", "purge"),
    _c("Update", "Manage", "The upgrade command for this install", "update", scan=False),
    _c("Uninstall", "Manage", "How to remove it (dry run)", "uninstall", "--dry-run", scan=False),
    _c("Completion", "Manage", "A shell completion script", "completion", "{ask}", ask="bash, zsh or fish?", scan=False),
    _c("Doctor --env", "Manage", "Check Python, install and key", "doctor", "--env", scan=False),
)


def more_entries() -> tuple[tuple[str, str], ...]:
    return tuple((c.name, f"{c.group} · {c.hint}") for c in MORE)


def argv_for(cmd: Cmd, cfg: str, answer: str = "") -> list[str]:
    out: list[str] = []
    for token in cmd.argv:
        if token == "{ask*}":
            out += answer.split()
        else:
            out.append(answer if token == "{ask}" else token.replace("{cfg}", cfg))
    return out


def scan_intro(cfg: str, out: str) -> list[str]:
    return [f"  Reads {cfg} (local files only) and writes {out}.", "  Offline: nothing is sent anywhere."]


def done_line(data: Any) -> str:
    """`Done: N Items, M clusters` from a saved scan (just `Done.` when it cannot be read)."""
    try:
        n, m = len(data["items"]), len(data["clusters"])
    except (KeyError, TypeError):
        return "Done."
    return f"Done: {n} Item{'' if n == 1 else 's'}, {m} cluster{'' if m == 1 else 's'}"


def clean_answer(text: str) -> str:
    """A typed answer; Esc (alone or followed by Enter) cancels."""
    return "" if text.startswith("\x1b") else re.sub(r"\s+", " ", text).strip()
