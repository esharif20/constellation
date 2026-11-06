"""Help text, the --dry-run rule and the exit-code summary for the CLI, kept apart from cli.py's parser wiring.

`decorate()` runs once after the parser is built: it gives each known verb a description and an examples epilog, marks the
verbs that write (`writes=True` default) and gives each an `--dry-run` flag.
"""

import argparse
from pathlib import Path

# name -> (group, one-sentence description, example lines). A verb missing here keeps its own text and lands in "Manage".
_VERBS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "doctor": ("Look", "One-screen health check of your setup.", ("constellation doctor", "constellation doctor --json")),
    "cost": ("Look", "What loads at session start, biggest first, by plugin.", ("constellation cost", "constellation cost --json")),
    "unused": ("Look", "Items not used lately, with confidence.", ("constellation unused", "constellation unused --json")),
    "twins": ("Look", "Overlapping pairs and which one you use.", ("constellation twins", "constellation twins my-scan.json")),
    "why": ("Look", "Why one Item has its verdict, and what removing it frees.", ("constellation why my-skill",)),
    "hooks": ("Look", "Every hook, ranked by what it does to each prompt.", ("constellation hooks", "constellation hooks --json")),
    "clashes": ("Look", "Hook, MCP name and trigger-phrase collisions.", ("constellation clashes", "constellation clashes --json")),
    "triggers": ("Look", "Skills that never fire or fire too greedily.", ("constellation triggers", "constellation triggers --json")),
    "explain": ("Look", "Plain-English summary of the whole setup.", ("constellation explain",)),
    "ask": ("Look", "Ask a question in plain English (local rules, no model).", ('constellation ask "what costs the most?"',)),
    "report": (
        "Look",
        "Print a plain-text report of a saved scan (reads the file only; no network, no cost).",
        ("constellation report", "constellation report --top 5 --cleanup cleanup.md --dry-run"),
    ),
    "assess": ("Look", "Print every Item's verdict from a saved scan as JSON.", ("constellation assess > verdicts.json",)),
    "weekly": (
        "Look",
        "What changed since the last scan, and what went quiet.",
        ("constellation weekly", "constellation weekly --since 2026-11-01"),
    ),
    "diff": ("Look", "List Items added, removed or changed between two saved scans.", ("constellation diff old.json new.json",)),
    "delta": ("Look", "What changed between two saved scans, in tokens and Overlaps.", ("constellation delta old.json new.json",)),
    "preview": (
        "Look",
        "Show what installing a downloaded plugin or skill folder would add. Nothing is run or sent.",
        ("constellation preview ./downloaded-plugin", "constellation preview ./downloaded-plugin --out preview.json --dry-run"),
    ),
    "expand": ("Look", "List the tools of one configured local MCP server.", ("constellation expand my-server --config-dir ~/.claude",)),
    "clean": (
        "Act",
        "Build a private cleanup checklist from the last scan. Nothing in your setup is changed.",
        ("constellation clean --dry-run        # print the checklist, write nothing", "constellation clean --out ~/cleanup.md"),
    ),
    "share": (
        "Act",
        "Write the public Snapshot (same as export --public). Free text is not anonymised.",
        ("constellation share --dry-run", "constellation share --out constellation-share"),
    ),
    "export": (
        "Act",
        "Write a read-only public Snapshot to a new directory; free text is NOT anonymised.",
        ("constellation export --public --out snapshot --dry-run", "constellation export --public --out snapshot"),
    ),
    "review": (
        "Act",
        "Go through Suggestions one at a time and write the approved ones to a checklist (no network, no cost).",
        ("constellation review", "constellation review --dry-run"),
    ),
    "scan": (
        "Map",
        "Read a Claude Code config directory and write a constellation JSON file.",
        ("constellation scan ~/.claude --dry-run   # show what would be sent and written", "constellation scan ~/.claude --offline"),
    ),
    "open": (
        "Map",
        "Serve a constellation JSON file as a graph in the browser (`open demo` shows the packaged demo).",
        ("constellation open", "constellation open demo --no-browser"),
    ),
    "completion": (
        "Manage",
        "Print a shell completion script (bash, zsh or fish) to stdout.",
        ("constellation completion zsh > ~/.zfunc/_constellation", "constellation completion bash >> ~/.bashrc"),
    ),
}
WRITERS = frozenset({"scan", "clean", "share", "export", "review", "report", "preview"})
EXIT_CODES = "Exit codes: 0 ok, 1 runtime error, 2 usage error or missing input, 130 interrupted."
_GROUP_ORDER = ("Look", "Act", "Map", "Manage")


def decorate(parser: argparse.ArgumentParser, commands: dict[str, argparse.ArgumentParser]) -> None:
    """Describe every verb, mark and flag the writers, and group the top-level help."""
    for name, sub in commands.items():
        if name in _VERBS:
            sub.description = _VERBS[name][1]
            sub.epilog = "examples:\n" + "\n".join(f"  {e}" for e in _VERBS[name][2])
        elif sub.epilog is None:  # a verb added elsewhere still gets the examples heading to fill in
            sub.epilog = "examples:\n  constellation " + name
        sub.formatter_class = argparse.RawDescriptionHelpFormatter
        if name in WRITERS:
            sub.set_defaults(writes=True)
            if not any("--dry-run" in a.option_strings for a in sub._actions):
                sub.add_argument("--dry-run", action="store_true", help="show what would be written; write nothing")
    parser.epilog = (
        help_groups(commands) + "\n\n" + EXIT_CODES + "\nNo telemetry. The network is used only by scan (with a key), ask and update."
    )


def help_groups(commands: dict[str, argparse.ArgumentParser]) -> str:
    rows: dict[str, list[tuple[str, str]]] = {g: [] for g in _GROUP_ORDER}
    for name, sub in commands.items():
        group = _VERBS[name][0] if name in _VERBS else "Manage"
        rows[group].append((name, (sub.description or "").split(". ")[0].rstrip(".")))
    return "\n\n".join(f"{g}:\n" + "\n".join(f"  {n:<12}{h}" for n, h in r) for g, r in rows.items() if r)


def scan_writes(out: Path, history: Path | None, habits: Path | None, weekly: Path | None) -> list[str]:
    """The files a real `scan` would write, in order, skipping those switched off (None)."""
    return [str(p) for p in (out, history, habits, weekly) if p is not None]
