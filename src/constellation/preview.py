"""Install cost preview: read an untrusted local folder safely and say what installing it would add. Nothing is run, fetched or sent.

No provider is imported here. Token counts come from the existing cache or a length estimate; overlap uses the local vectors."""

import math
import os
import re
import stat
import unicodedata
from dataclasses import replace
from pathlib import Path
from typing import Any

from . import retrieve
from .claude_code import pack_secrets, read_pack
from .cluster import dot
from .costs import measure
from .models import Embedder, Item
from .redact import redact

MAX_ENTRIES = 2000
MAX_FILE_BYTES = 1_000_000
NAME_CAP = 80
DESCRIPTION_CAP = 200
_PRUNED = {".git", "node_modules"}
_TEXT_SUFFIXES = {".md", ".json"}
_ESCAPES = re.compile(r"(?:\x1b\[|\x9b)[0-?]*[ -/]*[@-~]|(?:\x1b\]|\x9d)[^\x07\x1b\x9c]*(?:\x07|\x1b\\|\x9c)?")
_COUNTED = {"skill", "agent", "command"}  # always-on text is `name: description`; hooks and MCP servers only exist after install


def _strip(text: str) -> str:
    """Printable text only: ANSI escapes and every Unicode `C*` character (control, bidi override, zero-width) dropped, whitespace
    collapsed."""
    text = _ESCAPES.sub("", "".join(" " if c.isspace() else c for c in text))
    return " ".join("".join(c for c in text if unicodedata.category(c)[0] != "C").split())


def _plain(text: str, cap: int) -> str:
    return _strip(text)[:cap].strip()


def _clean(text: object, cap: int, secrets: set[str]) -> str:
    """Strip first so a secret split by a zero-width character is whole again, then redact, then cut."""
    return _plain(redact(_strip(str(text)), secrets), cap)


def check_tree(root: Path) -> str | None:
    """Why the folder must not be read (the relative path is named), or None. Looks at names and file types only; reads nothing."""
    base = root.resolve()
    seen = 0
    stack = [base]
    while stack:
        with os.scandir(stack.pop()) as entries:
            for entry in sorted(entries, key=lambda e: e.name):
                if entry.name in _PRUNED:
                    continue
                seen += 1
                rel = _strip(str(Path(entry.path).relative_to(base)))
                if seen > MAX_ENTRIES:
                    return f"{rel}: more than {MAX_ENTRIES} entries in the folder"
                link = entry.is_symlink()
                if link and not Path(entry.path).resolve().is_relative_to(base):
                    return f"{rel}: symlink points outside the folder"
                try:
                    info = os.stat(entry.path)  # follows a symlink that was just checked to stay inside; a FIFO is only stat-ed
                except OSError:
                    return f"{rel}: cannot be read"
                if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                    return f"{rel}: not a regular file or folder"
                if stat.S_ISREG(info.st_mode) and Path(entry.name).suffix.lower() in _TEXT_SUFFIXES and info.st_size > MAX_FILE_BYTES:
                    return f"{rel}: file is larger than {MAX_FILE_BYTES} bytes"
                if stat.S_ISDIR(info.st_mode) and not link:
                    stack.append(Path(entry.path))
    return None


def _pack_items(items: list[Item], secrets: set[str]) -> list[Item]:
    return [replace(i, name=_clean(i.name, NAME_CAP, secrets), description=_clean(i.description, DESCRIPTION_CAP, secrets)) for i in items]


def _tokens(items: list[Item], cost_cache: Path | None) -> dict[str, tuple[int | None, bool]]:
    """(tokens, estimated) per Item id: the exact cached count, else ceil(bytes / 4); None for kinds only known after install."""
    exact, _ = measure([i for i in items if i.kind in _COUNTED], {}, None, set(), cost_cache)
    out: dict[str, tuple[int | None, bool]] = {}
    for i in items:
        if i.kind not in _COUNTED:
            out[i.id] = (None, False)
        elif (cached := exact[i.id].always_on) is not None:
            out[i.id] = (cached, False)
        else:
            out[i.id] = (math.ceil(len(f"{i.name}: {i.description}".encode()) / 4), True)
    return out


def _overlaps(
    items: list[Item], scan: dict[str, Any], embedder: Embedder | None, vector_cache: Path | None
) -> tuple[list[dict[str, str]], str | None]:
    existing = [{**e, "name": _plain(str(e["name"]), NAME_CAP)} for e in scan["items"]]
    by_name = {(e["kind"], e["name"].lower()): e for e in existing}
    found: list[dict[str, str]] = []
    for i in items:
        if i.kind != "plugin" and (e := by_name.get((i.kind, i.name.lower()))):
            found.append({"new_id": f"new:{i.id}", "existing_id": e["id"], "existing_name": e["name"], "why": "same name"})
    if embedder is None:
        return found, "Meaning-based overlap is off (the local embedder is unavailable); only same names were compared."
    new = [{"id": f"new:{i.id}", "kind": i.kind, "name": i.name, "description": i.description} for i in items if i.kind in _COUNTED]
    old = [e for e in existing if e["kind"] in _COUNTED]
    index = retrieve.Index([*new, *old])
    try:
        index.add_vectors(embedder, vector_cache or retrieve.DEFAULT_CACHE)
        if index.vectors is None:
            return found, index.note
        named = {o["new_id"] for o in found}
        for n in new:
            scored = sorted(
                ((dot(index.vectors[n["id"]], index.vectors[e["id"]]), e["id"], e["name"]) for e in old), key=lambda s: (-s[0], s[1])
            )
            if n["id"] not in named and scored and scored[0][0] >= retrieve.SIMILAR:
                found.append({"new_id": n["id"], "existing_id": scored[0][1], "existing_name": scored[0][2], "why": "similar meaning"})
        return found, index.note
    finally:
        index.close()


def preview(
    root: Path,
    scan: dict[str, Any] | None,
    embedder: Embedder | None = None,
    cost_cache: Path | None = None,
    vector_cache: Path | None = None,
) -> dict[str, Any]:
    """What installing the folder at `root` would add. Raises ValueError (a plain reason) when the folder must not be read."""
    root = Path(root)
    if reason := check_tree(root):
        raise ValueError(reason)
    try:
        name, layout, raw, warnings, _ = read_pack(root)
    except ValueError as error:
        raise ValueError(_strip(str(error))) from None
    secrets = pack_secrets(root.resolve())
    items = _pack_items(raw, secrets)
    tokens = _tokens(items, cost_cache)
    pack = _clean(name, NAME_CAP, secrets)
    overlaps, note = _overlaps(items, scan, embedder, vector_cache) if scan is not None else ([], None)
    return {
        "version": 1,
        "pack": {"name": pack, "layout": layout},
        "items": [
            {
                "id": f"new:{i.id}",
                "kind": i.kind,
                "name": i.name,
                "description": i.description,
                "always_on": tokens[i.id][0],
                "estimated": tokens[i.id][1],
            }
            for i in items
        ],
        "counts": {k: sum(i.kind == k for i in items) for k in sorted({i.kind for i in items})},
        "always_on": {
            "counted": sum(t or 0 for t, est in tokens.values() if not est),
            "estimated": sum(t or 0 for t, est in tokens.values() if est),  # pragma: no mutate (equivalent: an estimate is never 0 or None)
            "unknown": sum(i.kind in {"hook", "mcp_server"} for i in items),
        },
        "overlaps": overlaps,
        "already_installed": scan is not None
        and layout == "plugin"
        and any(e["kind"] == "plugin" and _plain(str(e["name"]), NAME_CAP) == pack for e in scan["items"]),
        "compared": scan is not None,
        "note": note,
        "warnings": [_clean(w, DESCRIPTION_CAP, secrets) for w in warnings],
    }
