"""Local streaming transcript reader. Only indexed Item ids, counts and digit dates escape."""

import hashlib
import json
import os
import re
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, BinaryIO

from .models import Item, ProjectUsage, Relation, Usage, UsageWindow
from .redact import redact

FILE_CAP = 256 * 1024 * 1024
LINE_CAP = 8 * 1024 * 1024
PROJECTS = "projects"
SUBAGENTS = "subagents"
TRACKED = {"skill", "agent", "mcp_server", "connector"}
LABEL_CAP = 60


def _encode(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))  # Claude Code's folder naming (assumed); a mismatch only costs a label


def _label(folder: str, number: int, project: Path | None) -> str:
    """Local-only display label; never the username (home prefix removed) and always redacted."""
    if project is not None and folder == _encode(project.resolve()):
        shown = project.resolve().name
    else:
        home = _encode(Path.home()) + "-"
        shown = (folder.removeprefix(home) if folder.startswith(home) else folder).strip("-")
    return redact(shown)[:LABEL_CAP] or f"project {number}"


def _bump(old: Usage, day: str | None) -> Usage:
    used = max(old.last_used, day) if old.last_used and day else old.last_used or day
    return Usage(old.count + 1, used)


def _projects(credited: dict[str, dict[str, Usage]], folders: set[str], project: Path | None) -> ProjectUsage:
    """Folder names turn into ordinals p1..pN here; only keys, labels (local) and Usage leave this module."""
    current = _encode(project.resolve()) if project is not None else None
    kept = sorted({f for per in credited.values() for f in per} | ({current} & folders if current else set()))
    keys = {folder: f"p{n}" for n, folder in enumerate(kept, 1)}
    labels = {keys[folder]: _label(folder, n, project) for n, folder in enumerate(kept, 1)}
    by_project = {id_: {keys[f]: u for f, u in per.items()} for id_, per in credited.items()}
    return ProjectUsage(labels, by_project, keys.get(current) if current else None)


def _day(value: Any) -> str | None:
    if not isinstance(value, str) or not re.match(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T", value):
        return None
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        return None


def _index(items: list[Item], relations: list[Relation]) -> tuple[dict[tuple[str, str], list[str]], dict[str, list[str]]]:
    names: dict[tuple[str, str], list[str]] = {}
    prefixes: dict[str, list[str]] = {}
    # A plugin's contents are the targets of its "contains" edges; an id prefix is no scope (a plugin may be named "user").
    owner = {r.target: r.source for r in relations if r.kind == "contains"}
    plugin_names = {i.id: i.name for i in items if i.kind == "plugin"}
    plugin_of = {i.id: plugin_names[owner[i.id]] if i.id in owner else "" for i in items}
    local = {(i.kind, i.name) for i in items if not plugin_of[i.id]}
    for i in items:
        plugin = plugin_of[i.id]
        if i.kind in {"skill", "agent"}:
            if plugin:
                names.setdefault((i.kind, f"{plugin}:{i.name}"), []).append(i.id)
            if not plugin or (i.kind, i.name) not in local:
                names.setdefault((i.kind, i.name), []).append(i.id)
        if i.kind == "mcp_server":  # scans no longer produce connectors; they return with transcript-seen connectors
            normalized = re.sub(r"[^A-Za-z0-9_-]", "_", i.name)
            if plugin:
                normalized = "plugin_" + re.sub(r"[^A-Za-z0-9_-]", "_", plugin) + "_" + normalized
            prefixes.setdefault(f"mcp__{normalized}__", []).append(i.id)
    return names, prefixes


def _digest(value: str) -> bytes:
    return hashlib.blake2b(value.encode(), digest_size=8).digest()  # pragma: no mutate (digest length changes are equivalent)


Index = tuple[dict[tuple[str, str], list[str]], dict[str, list[str]]]


def _block(role: str, block: Any, record: dict[str, Any], index: Index) -> tuple[list[list[str]], Any]:
    """One content block to (name lookups, dedup key); ValueError marks only this block bad."""
    names, prefixes = index
    if not isinstance(block, dict) or not isinstance(block.get("type"), str):
        raise ValueError
    groups: list[list[str]] = []  # one group per name lookup; ambiguity is decided per lookup
    key: Any = ""  # pragma: no mutate (initial key is unused until ids are matched)
    if role == "assistant" and block.get("type") == "tool_use":
        name, inputs, key = block.get("name"), block.get("input"), block.get("id")
        if not isinstance(name, str) or not isinstance(inputs, dict) or not isinstance(key, str):
            raise ValueError
        if name in {"Skill", "Agent", "Task"}:
            field = "skill" if name == "Skill" else "subagent_type"
            if field in inputs or name == "Skill":  # an Agent without subagent_type is the built-in agent: valid, no Item
                value = inputs.get(field)
                if not isinstance(value, str):
                    raise ValueError
                groups = [names.get(("skill" if name == "Skill" else "agent", value), [])]
        elif name.startswith("mcp__"):
            for prefix in sorted(prefixes, reverse=True):
                if name.startswith(prefix):
                    groups = [prefixes[prefix]]
                    break
    elif role == "user" and block.get("type") == "text":
        text, key = block.get("text"), record.get("uuid")
        if not isinstance(text, str) or not isinstance(key, str):
            raise ValueError
        groups = [names.get(("skill", value), []) for value in re.findall(r"<command-name>/([^<]+)</command-name>", text)]
    return groups, key


def _matches(record: Any, index: Index, errors: list[int]) -> Iterator[tuple[str, bytes, tuple[str, ...]]]:
    if not isinstance(record, dict):
        raise ValueError
    if "message" not in record:  # not a user/assistant record (summaries, snapshots)
        return
    role = record.get("type")
    if not isinstance(role, str):
        raise ValueError
    if role not in {"user", "assistant"}:  # system and other records carry no invocations
        return
    message = record["message"]
    if not isinstance(message, dict):
        raise ValueError
    content = message.get("content")
    if isinstance(content, str) and role == "user":
        content = [{"type": "text", "text": content}]
    if not isinstance(content, list):
        raise ValueError
    for block in content:
        try:
            groups, key = _block(role, block, record, index)
        except ValueError:
            errors[0] = 1  # at most one per line; the other blocks are still credited
            continue
        if isinstance(key, str):
            digest = _digest(key)
            for group in groups:
                for id_ in group:
                    yield id_, digest, tuple(sorted(group)) if len(group) > 1 else ()


def _invocations(record: Any, index: Index, errors: list[int]) -> Iterator[tuple[str, bytes, tuple[str, ...]]]:
    try:
        matched = list(_matches(record, index, errors))
    except ValueError:
        errors[0] = 1
        return
    yield from matched


def _parse(line: bytes, index: Index, relevant: bool) -> tuple[list[tuple[str, bytes, tuple[str, ...]]], str | None, int]:
    # The record and all its text die with this call, including on malformed shapes.
    try:
        record = json.loads(line)
    except (ValueError, UnicodeError, RecursionError):
        return [], None, int(relevant)
    day = _day(record.get("timestamp")) if isinstance(record, dict) else None  # top-level only, never a nested one
    if not relevant:
        return [], day, 0
    errors = [0]
    return list(_invocations(record, index, errors)), day, errors[0]


def _is_dir(entry: os.DirEntry[str]) -> bool:
    return entry.is_dir(follow_symlinks=False)  # pragma: no mutate (defence in depth after explicit symlink rejection)


def _is_file(entry: os.DirEntry[str]) -> bool:
    return entry.is_file(follow_symlinks=False)  # pragma: no mutate (defence in depth after explicit symlink rejection)


@contextmanager
def _directory(name: str | Path, parent: int | None = None) -> Iterator[int]:
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    try:
        yield fd
    finally:
        os.close(fd)


def _walk(parent: int, depth: int, folder: str = "") -> Iterator[tuple[int, str, str] | str | None]:
    """Only project/main files (depth 1) and session/subagents files (depth 3)."""
    try:
        with os.scandir(parent) as stream:
            entries = sorted(stream, key=lambda e: e.name)
        for entry in entries:
            try:
                if entry.is_symlink():
                    yield "symlink"
                elif depth in {1, 3} and entry.name.endswith(".jsonl") and _is_file(entry):
                    yield parent, entry.name, folder
                elif depth < 3 and _is_dir(entry):
                    if depth == 1 and entry.name in {"memory", "tool-results"}:
                        continue
                    if depth == 2 and entry.name != SUBAGENTS:
                        continue
                    with _directory(entry.name, parent) as child:
                        yield from _walk(child, depth + 1, entry.name if depth == 0 else folder)
            except OSError:
                yield None
    except OSError:
        yield None


def _transcripts(config_dir: Path) -> Iterator[tuple[int, str, str] | str | None]:
    # Keep every ancestor pinned; subsequent opens resolve only one child component.
    with _directory(config_dir) as config:
        with _directory(PROJECTS, config) as projects:
            yield from _walk(projects, 0)


def _drain(stream: BinaryIO) -> None:
    while chunk := stream.readline(LINE_CAP + 1):
        if chunk.endswith(b"\n"):
            return


def read_usage(
    config_dir: Path, items: list[Item], relations: list[Relation], project: Path | None = None
) -> tuple[dict[str, Usage], UsageWindow, list[str], ProjectUsage]:
    usage = {i.id: Usage(0, None) for i in items if i.kind in TRACKED}
    config_dir = config_dir.resolve()  # a symlinked config dir is the user's choice; pin its real target once
    projects = config_dir / PROJECTS
    if projects.is_symlink():
        return usage, UsageWindow(0, None, None, 1), ["usage: projects folder is a symlink; not read"], ProjectUsage()
    if not projects.exists():
        return usage, UsageWindow(0, None, None, 0), [], ProjectUsage()
    index = _index(items, relations)
    seen: set[bytes] = set()
    folders: set[str] = set()
    credited: dict[str, dict[str, Usage]] = {}  # Item id -> project folder -> Usage; folders become opaque keys at the end
    ambiguous: set[tuple[str, ...]] = set()
    files = skipped = malformed = oversize = big = symlinks = 0
    first = last = None
    try:
        for path in _transcripts(config_dir):
            if path is None or isinstance(path, str):  # None is unreadable, "symlink" is skipped on purpose
                skipped += 1
                symlinks += path == "symlink"
                continue
            try:
                parent, name, folder = path
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                with os.fdopen(fd, "rb") as stream:
                    info = os.fstat(stream.fileno())
                    if not stat.S_ISREG(info.st_mode) or info.st_size > FILE_CAP:
                        skipped += 1
                        big += stat.S_ISREG(info.st_mode)  # in this branch a regular file is a too-big one
                        continue
                    files += 1
                    folders.add(folder)
                    while line := stream.readline(LINE_CAP + 1):
                        if len(line) > LINE_CAP and not line.endswith(b"\n"):
                            _drain(stream)
                            oversize += 1
                            continue
                        relevant = b'"tool_use"' in line or b"<command-name>" in line  # pragma: no mutate (prefilter only)
                        invocations, used_day, errors = _parse(line, index, relevant)
                        malformed += errors
                        if used_day:
                            first = min(first, used_day) if first else used_day
                            last = max(last, used_day) if last else used_day
                        by_key: dict[bytes, dict[str, tuple[str, ...]]] = {}
                        for id_, key, group in invocations:
                            by_key.setdefault(key, {})[id_] = group
                        for key, ids in by_key.items():
                            if key in seen:
                                continue
                            seen.add(key)
                            ambiguous.update(group for group in ids.values() if group)
                            for id_ in ids:
                                usage[id_] = _bump(usage[id_], used_day)
                                per = credited.setdefault(id_, {})
                                per[folder] = _bump(per.get(folder, Usage(0, None)), used_day)
                        del line
            except OSError:
                skipped += 1
    except OSError:
        skipped += 1
    warnings = []
    if malformed or oversize or skipped:
        warnings.append(
            f"usage: skipped {malformed} malformed lines, {oversize} oversize line, "
            f"{skipped} files ({big} too big, {symlinks} symlinks skipped on purpose, {skipped - big - symlinks} unreadable)"
        )
    if ambiguous:
        warnings.append(f"usage: {len(ambiguous)} invocation names matched more than one Item; each was credited")
    return usage, UsageWindow(files, first, last, skipped), warnings, _projects(credited, folders, project)
