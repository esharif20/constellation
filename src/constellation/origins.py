"""Where an Item came from (pack, plugin, claude.ai). Local display data only: never sent to a provider, dropped by snapshot()."""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .redact import redact

DEFAULT_LOCKFILE = Path.home() / ".agents" / ".skill-lock.json"  # the skills CLI's lockfile; the scan reads its `source` fields only
CAP = 60
# owner/repo, up to three ASCII segments, none starting with a dot; "@" only as an npm-style scope prefix, so "user@host" and paths fail.
_SAFE = re.compile(r"@?[\w-][\w.-]*(?:/[\w-][\w.-]*){0,2}", re.ASCII)
LOCK_WARNING = "could not read skill lock: unreadable or not valid JSON"


def clean(value: object, secrets: set[str]) -> str | None:
    """A short pack-like name, or None. The whole value is checked first and dropped if too long, redacted or odd: never truncated."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if len(value) > CAP or redact(value, secrets) != value or not _SAFE.fullmatch(value):
        return None
    return value


def read_lock(path: Path, secrets: set[str]) -> tuple[dict[str, str], list[str]]:
    """skill folder name -> source, from `skills[name]["source"]` only. The rest of the file is parsed in memory and forgotten."""
    try:
        if not path.is_file():
            return {}, []
        data: Any = json.loads(path.read_text())
    except (OSError, ValueError, RecursionError):
        return {}, [LOCK_WARNING]
    skills = data.get("skills") if isinstance(data, dict) else None
    found = {
        name: source
        for name, entry in (skills.items() if isinstance(skills, dict) else [])
        if isinstance(entry, dict) and (source := clean(entry.get("source"), secrets))
    }
    return found, []


@dataclass(frozen=True)
class Found:
    """What an origin source may look at: no file is read here; the lockfile, the frontmatter and the path are already in hand."""

    folder: Path  # the skill's folder (or the agents folder)
    config_dir: Path
    kind: str
    meta: dict[str, Any]
    lock: dict[str, str]
    secrets: set[str]


def _linked(f: Found) -> Path | None:
    """Where a user skill folder points when it is a symlink to somewhere outside the config dir (how an installer links it in)."""
    if f.kind != "skill" or not f.folder.is_symlink():
        return None
    target = f.folder.resolve()
    return None if target.is_relative_to(f.config_dir.resolve()) else target


def from_lockfile(f: Found) -> str | None:
    """Only a linked skill is looked up, so a plain folder that shares a name with a lock entry gets nothing."""
    target = _linked(f)
    return (f.lock.get(target.name) or f.lock.get(f.folder.name)) if target else None


def from_symlink(f: Found) -> str | None:
    """A skill linked in from `~/.<installer>/skills/<name>`: the installer folder name without its dot. Other folders (which may
    be private names) and home itself give nothing."""
    target = _linked(f)
    if not target or target.parent.name != "skills":
        return None
    installer = target.parent.parent
    if installer.parent != Path.home().resolve() or not installer.name.startswith("."):
        return None
    return clean(installer.name.lstrip("."), f.secrets)


def from_frontmatter(f: Found) -> str | None:
    value = next((f.meta[k] for k in ("repository", "repo") if isinstance(f.meta.get(k), str)), None)
    if value and "://" in value:  # a repo URL reduces to owner/repo; the host and any userinfo are dropped
        value = urlsplit(value).path.strip("/").removesuffix(".git")
    return clean(value, f.secrets)


SOURCES: tuple[Callable[[Found], str | None], ...] = (from_lockfile, from_symlink, from_frontmatter)  # add an installer here


def find(f: Found) -> str | None:
    return next((o for source in SOURCES if (o := source(f))), None)
