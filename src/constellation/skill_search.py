"""Private local skill-content discovery. This module has no provider or export path."""

import json
import os
import re
from collections.abc import Iterable
from pathlib import Path

from .claude_code import SOURCE, _frontmatter, _manifest, _plugin_roots, read_items, read_secrets
from .redact import _ASSIGNMENT, _FLAG, redact
from .retrieve import Index

DEFAULT_CACHE = Path.home() / ".cache" / "constellation" / "skill-content.json"
FIRST_LINES = 3
MAX_HINT_CHARS = 200
MAX_CACHE_BYTES = 8 * 1024 * 1024
HINT_KINDS = {"heading", "first line", "file"}
HEADINGS = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)
UNDERLINE = re.compile(r"(?:=+|-+)")
CONTROLS = re.compile(r"[\x00-\x1f\x7f-\x9f]")
SKILL_LAYOUTS = (("skills/*/SKILL.md", ""), ("skills/synced/*/*/SKILL.md", "synced/"))


def _safe(text: str, known: Iterable[str] = ()) -> str:
    return CONTROLS.sub("", redact(text, known))


def _entries(body: str) -> list[tuple[str, str]]:
    lines = []
    fence = None
    for raw in body.splitlines():
        line = raw.strip()
        if fence is not None:
            if line.startswith(fence):
                fence = None
            continue
        if line.startswith(("```", "~~~")):
            fence = line[:3]
            continue
        if line:
            lines.append(line)
    entries = []
    for n, line in enumerate(lines):
        if match := HEADINGS.fullmatch(line):
            entries.append(("heading", match[1]))
        elif n + 1 < len(lines) and UNDERLINE.fullmatch(lines[n + 1]):
            entries.append(("heading", line))
        elif n < FIRST_LINES and not UNDERLINE.fullmatch(line):
            entries.append(("first line", line))
    return entries


def load_content(cache: Path) -> dict[str, list[tuple[str, str]]]:
    """Load private evidence for Index(..., skill_content=...), without rereading skills or calling an embedder."""
    try:
        with os.fdopen(os.open(cache, os.O_RDONLY | os.O_NOFOLLOW)) as handle:
            if os.fstat(handle.fileno()).st_size > MAX_CACHE_BYTES:
                return {}
            data = json.load(handle)
    except (OSError, ValueError, RecursionError):
        return {}
    content: dict[str, list[tuple[str, str]]] = {}
    if isinstance(data, dict):
        for id_, rows in data.items():
            if isinstance(rows, list):
                content[id_] = [
                    (row[0], _safe(row[1])[:MAX_HINT_CHARS])
                    for row in rows
                    if isinstance(row, list)
                    and len(row) == 2
                    and isinstance(row[0], str)
                    and row[0] in HINT_KINDS
                    and isinstance(row[1], str)
                ]
    return content


def _references(config_dir: Path) -> dict[str, list[str]]:
    roots = [(config_dir, "")]
    seen = set()
    for root in _plugin_roots(config_dir):
        meta = _manifest(root, [])
        if meta is not None and meta["name"] not in seen:
            seen.add(meta["name"])
            roots.append((root, f"{meta['name']}/"))
    found = {}
    for root, scope in roots:
        for pattern, extra in SKILL_LAYOUTS:
            for path in sorted(root.glob(pattern)):
                if scope and not path.resolve().is_relative_to(root.resolve()):
                    continue
                meta, _ = _frontmatter(path)
                name = meta.get("name")
                if not name:
                    continue
                id_ = f"{SOURCE}:skill:{scope}{extra}{name}"
                found[id_] = sorted({p.name for p in path.parent.rglob("*") if p != path and not p.is_symlink() and p.is_file()})
    return found


def find_skills(query: str, config_dir: Path, *, cache: Path | None = None) -> tuple[list[dict[str, str]], list[str]]:
    """Offline search with local evidence; content never becomes an Item field or embedding input."""
    items, warnings, relations, bodies = read_items(config_dir)
    known = read_secrets(config_dir)
    known |= {
        value
        for body in bodies.values()
        for pattern in (_ASSIGNMENT, _FLAG)
        for match in pattern.finditer(body)
        if (value := match["v"].strip("\"'"))
    }
    references = _references(config_dir)
    names = {i.id: i.name for i in items}
    # Only plugin containment links target skills in the source adapter's relations.
    owners = {r.target: names[r.source] for r in relations}
    metadata = [
        {
            "id": _safe(i.id, known),
            "kind": i.kind,
            "name": _safe(i.name, known),
            "description": _safe(i.description, known),
            "invoke": _safe(f"/{owners[i.id] + ':' if i.id in owners else ''}{i.name}", known),
        }
        for i in items
        if i.kind == "skill"
    ]
    content = {}
    for item in items:
        if item.kind != "skill":
            continue
        body = bodies[item.id]
        entries = _entries(body)
        entries += [("file", name) for name in references.get(item.id, [])]
        content[_safe(item.id, known)] = [(kind, _safe(text, known)[:MAX_HINT_CHARS]) for kind, text in entries]
    path = cache or DEFAULT_CACHE
    try:
        if path.resolve().is_relative_to(config_dir.resolve()):
            raise OSError
        encoded = json.dumps(content)
        if len(encoded) > MAX_CACHE_BYTES:  # json.dumps defaults to ASCII, so characters are bytes here
            raise OSError
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "w") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(encoded)
    except OSError:
        warnings.append("The private skill index could not be written; local search still works.")
    by_id = {i["id"]: i for i in metadata}
    index = Index(metadata, skill_content=content)
    try:
        results = [{**by_id[hit["id"]], **hit} for hit in index.query(query)]
    finally:
        index.close()
    return results, [_safe(w, known) for w in warnings]
