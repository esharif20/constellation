"""Claude Code Source adapter: reads a config dir, emits harness-neutral Items (ADR 0001)."""

import json
import re
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path, PurePath
from typing import Any
from urllib.parse import urlsplit

import yaml

from .models import Item, Relation
from .origins import Found, find, read_lock
from .origins import clean as clean_origin
from .progress import Progress, ProgressEvent
from .redact import redact

SOURCE = "claude-code"
LOCAL_SCOPE = True  # approved deviation from plan A item 8: read project/local-scope servers from .claude.json; False drops them
DESCRIPTION_CAP = 200  # a command's first line can be a whole paragraph
_SCHEMES = {"http", "https", "ws", "wss"}


def _changed_on(path: Path) -> str | None:
    """The day the file was last modified, from stat alone (the file is not read for this)."""
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, UTC).date().isoformat()
    except OSError:
        return None


def _shown(path: Path) -> str:
    """The path as shown in warnings: the home folder written as `~`, so the scan JSON never holds the username."""
    try:
        return f"~/{path.relative_to(Path.home())}"
    except ValueError:
        return str(path)


def _frontmatter(path: Path) -> tuple[dict[str, Any], str | None]:
    """The file's frontmatter, and a warning if it was not clean. Real files are not always valid YAML (an unquoted ': ' in a
    description), and Claude Code still loads them, so fall back to reading name and description line by line."""
    parts = path.read_text().split("---")
    if len(parts) < 3:
        return {}, f"no frontmatter in {_shown(path)}"
    try:
        meta = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        lines = {m[1]: m[2].strip() for m in re.finditer(r"^(name|description):[ \t]*(.*)$", parts[1], re.MULTILINE)}
        return lines, f"frontmatter is not valid YAML, read name and description leniently ({_shown(path)})"
    return (meta if isinstance(meta, dict) else {}), None


_TRANSPORTS = {"stdio", "http", "sse", "ws"}


def _shape(server: dict[str, Any]) -> str:
    """Only the shape of an MCP server: transport, and the command's basename or the url's scheme and host. Never env, headers,
    args, or a url's userinfo, port, path or query: those hold tokens."""
    kind = server.get("type")
    transport = kind if kind in _TRANSPORTS else None
    url, command = server.get("url"), server.get("command")
    if isinstance(url, str) and url:
        try:
            parts = urlsplit(url)
            # A scheme-less "user:pw@host" parses the userinfo as the scheme, so only a known scheme is printed.
            scheme = parts.scheme if parts.scheme in _SCHEMES else "unknown"
            return f"remote {transport or 'http'}: {scheme}://{parts.hostname or ''}"
        except ValueError:  # a malformed url (bad port or bracket) is not worth a warning, and must not echo the url
            return f"remote {transport or 'http'}: unknown host"
    if isinstance(command, str) and command.split():
        # The first word that is not a NAME=value assignment: a shell-string command may lead with env values or carry arguments.
        words = [w for w in command.split() if not re.match(r"[A-Za-z_]\w*=", w)]
        word = PurePath(words[0]).name if words else ""
        return f"stdio: {word if word and '=' not in word else 'unknown'}"
    return f"{transport or 'unknown'}: unknown shape"


def _load(path: Path, warnings: list[str], label: str) -> Any:
    """Parsed JSON, or None with a warning. The warning never carries the parser's message or any file text."""
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError, RecursionError):
        warnings.append(f"could not read {label}: unreadable or not valid JSON")
        return None


def _add_servers(
    data: Any, scope: str, items: list[Item], warnings: list[str], secrets: set[str], label: str, bundle: bool = False
) -> None:
    """Shape-only MCP server Items from a `{"mcpServers": {...}}` object or the bare mapping inside it (plugins use both)."""
    mapping = data.get("mcpServers", data) if isinstance(data, dict) else None
    if not isinstance(mapping, dict):
        warnings.append(f"skipped MCP servers in {label}: not an object")
        return
    for raw_name, server in mapping.items():
        name = redact(str(raw_name), secrets)
        id_ = f"{SOURCE}:mcp_server:{scope}{name}"
        if not isinstance(server, dict):
            warnings.append(f"skipped an MCP server in {label}: not an object")
        elif not any(i.id == id_ for i in items):
            items.append(Item(id_, "mcp_server", name, redact(_shape(server), secrets), SOURCE))


def _claude_json(config_dir: Path, warnings: list[str]) -> Path | None:
    """Where user-scope state lives: next to the config (CLAUDE_CONFIG_DIR keeps it inside the dir), else, for a dir named
    `.claude`, beside it in $HOME. Any other dir has none, so a fixture or a copy never reads the real home."""
    inside = config_dir / ".claude.json"
    if inside.exists():
        return inside
    beside = config_dir.parent / ".claude.json"
    if config_dir.name != ".claude":
        if beside.exists():  # existence only: the file is never opened, so a copy still never reads the real home
            warnings.append("user-scope MCP servers were not read: the config dir is not named .claude and has no .claude.json inside it")
        return None
    if not beside.exists():
        warnings.append("no .claude.json found beside the config dir, so user-scope MCP servers are not listed")
        return None
    return beside


def _project_dir(key: str) -> Path | None:
    """The folder of a `.claude.json` project key if it is an absolute path to an existing directory."""
    path = Path(key)
    return path.resolve() if path.is_absolute() and path.is_dir() else None


def numbered_projects(projects: dict[Any, Any]) -> list[str]:
    """The `.claude.json` project keys that get a `local/<n>/` index: those with servers of their own or an existing folder holding a
    `.mcp.json`, in sorted path order. The path stays out of ids (it holds the username); the index keeps same-named servers apart.
    Expansion numbers with this too, so both name the same server."""
    return [
        p
        for p in sorted(projects, key=str)
        if isinstance(projects[p], dict) and (projects[p].get("mcpServers") or ((d := _project_dir(p)) and (d / ".mcp.json").is_file()))
    ]


def _names(entry: dict[str, Any], key: str, secrets: set[str]) -> set[str]:
    """The (redacted) server names in a list setting; anything that is not a list of strings is ignored."""
    listed = entry.get(key)
    return {redact(n, secrets) for n in listed if isinstance(n, str)} if isinstance(listed, list) else set()


def _approved(name: str, entry: dict[str, Any], settings: dict[str, Any], secrets: set[str]) -> bool:
    """Whether Claude Code would load a project `.mcp.json` server: approved by name or by enable-all, and not on a disabled list."""
    both = (entry, settings)
    if any(name in _names(e, "disabledMcpjsonServers", secrets) for e in both):
        return False
    return any(e.get("enableAllProjectMcpServers") is True or name in _names(e, "enabledMcpjsonServers", secrets) for e in both)


def _mark_off(items: list[Item], first: int, off: Callable[[str], bool]) -> None:
    items[first:] = [replace(i, disabled=True) if off(i.name) else i for i in items[first:]]


def _read_claude_json(
    config_dir: Path, items: list[Item], warnings: list[str], secrets: set[str], settings: dict[str, Any], project: Path | None
) -> dict[Path, dict[str, Any]]:
    """User, local-scope and every listed project's `.mcp.json` servers; returns each existing project folder's entry. The file also
    holds OAuth tokens: it is parsed in memory, only server shapes and approval lists are taken, and nothing else from it is kept,
    logged or put in a warning. A project path never enters an id or a warning."""
    path = _claude_json(config_dir, warnings)
    data = _load(path, warnings, ".claude.json") if path else None
    if data is not None and not isinstance(data, dict):
        warnings.append("could not read .claude.json: its top level is not an object")
    if not isinstance(data, dict):
        return {}
    first = len(items)
    _add_servers(data.get("mcpServers", {}), "user/", items, warnings, secrets, ".claude.json")
    projects = data.get("projects")
    if not LOCAL_SCOPE or not isinstance(projects, dict):
        return {}
    entries = {p: projects[p] for p in numbered_projects(projects)}
    # A user server is off only when every listed project turns it off: one project's switch does not remove it elsewhere.
    every = [_names(e, "disabledMcpServers", secrets) for e in projects.values() if isinstance(e, dict)]
    off_everywhere = set.intersection(*every) if every else set()
    _mark_off(items, first, off_everywhere.__contains__)
    folders = {p: d for p in entries if (d := _project_dir(p))}
    has_file = {p for p, d in folders.items() if (d / ".mcp.json").is_file()}
    mine = project.resolve() if project is not None else None
    for number, key in enumerate(entries, 1):
        entry, scope, first = entries[key], f"local/{number}/", len(items)
        _add_servers(entry.get("mcpServers") or {}, scope, items, warnings, secrets, ".claude.json")
        _mark_off(items, first, _names(entry, "disabledMcpServers", secrets).__contains__)
        items[first:] = [replace(i, scope="project") for i in items[first:]]
        if key in has_file and folders[key] != mine and _contained(folders[key] / ".mcp.json", folders[key], "project/", warnings):
            parsed = _load(folders[key] / ".mcp.json", warnings, f"{scope}.mcp.json")
            if parsed is not None:
                _add_project_servers(parsed, scope, entry, settings, items, warnings, secrets)
    return {d: entries[p] for p, d in folders.items()}


def _add_project_servers(
    data: Any, scope: str, entry: dict[str, Any], settings: dict[str, Any], items: list[Item], warnings: list[str], secrets: set[str]
) -> None:
    """A project `.mcp.json`: project-scope Items, switched off unless Claude Code would have approved them."""
    first = len(items)
    _add_servers(data, scope, items, warnings, secrets, f"{scope}.mcp.json")
    items[first:] = [replace(i, scope="project", disabled=not _approved(i.name, entry, settings, secrets)) for i in items[first:]]


def _plugin_servers(meta: dict[str, Any], root: Path, scope: str, items: list[Item], warnings: list[str], secrets: set[str]) -> None:
    """MCP servers a plugin.json declares: an inline object, a path to a JSON file inside the plugin, a bundle, or a list of these."""
    declared = meta.get("mcpServers")
    for entry in declared if isinstance(declared, list) else [declared] if declared else []:
        label = f"plugin {meta['name']}"
        if isinstance(entry, dict):
            _add_servers(entry, scope, items, warnings, secrets, label)
        elif isinstance(entry, str) and entry.lower().endswith((".mcpb", ".dxt")):
            name = redact(PurePath(entry).stem, secrets)
            if not any(i.id == f"{SOURCE}:mcp_server:{scope}{name}" for i in items):
                items.append(Item(f"{SOURCE}:mcp_server:{scope}{name}", "mcp_server", name, "bundle: shape unknown", SOURCE))
        elif isinstance(entry, str) and (root / entry).resolve().is_relative_to(root.resolve()) and (root / entry).is_file():
            data = _load(root / entry, warnings, f"{label} MCP file")
            if data is not None:
                _add_servers(data, scope, items, warnings, secrets, label)
        else:
            warnings.append(f"skipped an MCP entry in {label}: not an inline object, a bundle, or a file inside the plugin")


def _command(path: Path, warnings: list[str]) -> tuple[str, str] | None:
    """(description, name) of a slash command, or None if the file is unreadable. The body is never kept: only skills and agents have
    a body that --count-bodies may send. Frontmatter is optional here: Claude Code uses the first line when it has none."""
    try:
        text = path.read_text()
    except (OSError, UnicodeDecodeError):
        warnings.append("skipped a command file: unreadable or not valid UTF-8")
        return None
    meta: dict[str, Any] = {}
    body = text
    if text.startswith("---") and len(text.split("---", 2)) == 3:
        meta, problem = _frontmatter(path)
        body = text.split("---", 2)[2]
        if problem:
            warnings.append(problem)
    first = next((line.strip() for line in body.splitlines() if line.strip()), "")
    return str(meta.get("description") or first)[:DESCRIPTION_CAP], path.stem


def _contained(path: Path, root: Path, scope: str, warnings: list[str]) -> bool:
    """In a plugin or project (non-empty scope) a file whose symlink resolves outside the root is refused, not read."""
    if scope and not path.resolve().is_relative_to(root.resolve()):
        warnings.append(f"skipped {path.name} in {scope.rstrip('/')}: it is a symlink pointing outside it")
        return False
    return True


def _inside(root: Path, pattern: str, scope: str, warnings: list[str]) -> Iterator[Path]:
    """Files matching `pattern`; in a plugin (non-empty scope) a symlink resolving outside the plugin is refused, not read."""
    for path in sorted(root.glob(pattern)):
        if scope and not path.resolve().is_relative_to(root.resolve()):
            warnings.append("skipped a file in a plugin: it is a symlink pointing outside the plugin")
        else:
            yield path


def _read_root(
    root: Path,
    scope: str,
    items: list[Item],
    warnings: list[str],
    relations: list[Relation],
    bodies: dict[str, str],
    secrets: set[str],
    lock: dict[str, str] | None,
    config_dir: Path,
) -> None:
    """Read the Items under one root: the config dir itself, or one plugin dir. `scope` keeps ids unique."""
    # "synced" holds skills synced from claude.ai, one folder deeper; its own id scope stops a synced copy colliding with a local skill.
    for kind, pattern, extra in (
        ("skill", "skills/*/SKILL.md", ""),
        ("skill", "skills/synced/*/*/SKILL.md", "synced/"),
        ("agent", "agents/*.md", ""),
    ):
        for path in _inside(root, pattern, scope, warnings):
            meta, problem = _frontmatter(path)
            if problem:
                warnings.append(problem)
            name, description = meta.get("name"), meta.get("description")
            if not name:
                warnings.append(f"skipped {kind} with no name ({_shown(path)})")
                continue
            if not description:
                warnings.append(f"skipped {kind} '{name}': no description ({_shown(path)})")
                continue
            # lock None = origins off; a plugin's contents get the plugin name in read_items, so only user skills look further.
            origin = (
                None if lock is None or scope else "claude.ai" if extra else find(Found(path.parent, config_dir, kind, meta, lock, secrets))
            )
            items.append(
                Item(f"{SOURCE}:{kind}:{scope}{extra}{name}", kind, name, description, SOURCE, origin=origin, changed_on=_changed_on(path))
            )
            bodies[items[-1].id] = path.read_text().split("---", 2)[2].strip()  # loaded only when invoked: the on-use text
    for path in _inside(root, "commands/*.md", scope, warnings):
        parsed = _command(path, warnings)
        if parsed is None:
            continue
        description, name = redact(parsed[0], secrets), parsed[1]
        if not description:
            warnings.append(f"skipped command '{name}': no description ({_shown(path)})")
            continue
        items.append(Item(f"{SOURCE}:command:{scope}{name}", "command", name, description, SOURCE, changed_on=_changed_on(path)))
    mcp_file = root / ".mcp.json"
    if mcp_file.exists() and _contained(mcp_file, root, scope, warnings):
        data = _load(mcp_file, warnings, f"{scope or 'config'}.mcp.json")
        if data is not None:
            _add_servers(data, scope, items, warnings, secrets, f"{scope or 'config'}.mcp.json")
    # User hooks live in settings.json; plugin hooks in hooks/hooks.json.
    for hooks_file in (root / "settings.json", root / "hooks" / "hooks.json"):
        if not hooks_file.exists() or not _contained(hooks_file, root, scope, warnings):
            continue
        data = _load(hooks_file, warnings, f"{scope or 'config/'}{hooks_file.name}")
        shown = f"{scope or 'config/'}{hooks_file.name}"
        if data is not None and not isinstance(data, dict):
            warnings.append(f"skipped {shown}: its top level is not an object")
        hooks = data.get("hooks", {}) if isinstance(data, dict) else {}
        if not isinstance(hooks, dict):
            warnings.append(f"skipped hooks in {shown}: not an object")
            hooks = {}
        for event, groups in hooks.items():
            if not isinstance(groups, list):
                warnings.append(f"skipped hooks for an event in {shown}: not a list")
                continue
            for group in groups:
                if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                    warnings.append(f"skipped a hook group in {shown}: it has no hooks list")
                    continue
                matcher = group.get("matcher")
                name = ":".join(filter(None, [event, matcher if isinstance(matcher, str) else None]))
                for handler in group["hooks"]:
                    is_mcp = isinstance(handler, dict) and handler.get("type") == "mcp_tool"
                    ok = (
                        isinstance(handler, dict)
                        and isinstance(handler.get("type"), str)
                        and (
                            all(isinstance(handler.get(k), str) for k in ("server", "tool"))
                            if is_mcp
                            else isinstance(handler.get("command"), str)
                        )
                    )
                    if not ok:
                        warnings.append(f"skipped a hook in {shown}: it has no command")
                        continue
                    # Index keeps ids unique when several handlers share an event and matcher.
                    id_ = f"{SOURCE}:hook:{scope}{name}:{len(items)}"
                    if is_mcp:
                        description = f"{handler['server']}.{handler['tool']}"
                        # A user's hook may call a ~/.claude.json (user-scope) server as well as a config-dir one.
                        for prefix in (scope, "user/") if not scope else (scope,):
                            server_id = f"{SOURCE}:mcp_server:{prefix}{handler['server']}"
                            if any(i.id == server_id for i in items):
                                relations.append(Relation(id_, server_id, "triggers"))
                                break
                    else:
                        description = handler["command"]
                    items.append(Item(id_, "hook", name, description, SOURCE))


def _installed(config_dir: Path) -> tuple[dict[Path, str], bool]:
    """installPath -> plugin key from installed_plugins.json, and whether the whole file was well formed. Bad entries are dropped."""
    try:
        plugins = _json_or_empty(config_dir / "plugins" / "installed_plugins.json").get("plugins", {})
    except (OSError, ValueError, AttributeError):
        return {}, False
    if not isinstance(plugins, dict):
        return {}, False
    found: dict[Path, str] = {}
    clean = True
    for key, entries in plugins.items():
        for e in entries if isinstance(entries, list) else []:
            if isinstance(e, dict) and isinstance(e.get("installPath"), str):
                found[Path(e["installPath"])] = key
            else:
                clean = False
        clean = clean and isinstance(entries, list)
    return found, clean


_PLUGIN_PARTS = ("skills", "agents", "commands", ".mcp.json", "hooks/hooks.json")


def _plugin_roots(config_dir: Path) -> list[Path]:
    """One root per plugin: the version installed_plugins.json names, else the newest cached one (stale versions duplicate ids).
    A manifest is optional in Claude Code, so a cached version with any default plugin folder or file counts too."""
    named = set(_installed(config_dir)[0])
    newest: dict[Path, Path] = {}
    for root in sorted(config_dir.glob("plugins/cache/*/*/*")):
        has = (root / ".claude-plugin" / "plugin.json").exists() or any((root / part).exists() for part in _PLUGIN_PARTS)
        if has and (not named or root in named):
            newest[root.parent] = root  # sorted, so the last version of a plugin wins when nothing names one
    cache = config_dir / "plugins" / "cache"
    for root in sorted(named):  # a local-directory marketplace installs outside the cache
        if not root.is_relative_to(cache) and (root / ".claude-plugin" / "plugin.json").exists():
            newest[root] = root
    return list(newest.values())


def _manifest(root: Path, warnings: list[str]) -> dict[str, Any] | None:
    """plugin.json, or for a plugin without one the folder name as its name. A malformed manifest is a warning, never the path."""
    path = root / ".claude-plugin" / "plugin.json"
    if not path.exists():
        return {"name": root.parent.name}
    if not _contained(path, root, "plugin/", warnings):
        return None
    meta = _quiet_json(path)  # {} when unreadable, invalid or not an object
    if not isinstance(meta.get("name"), str) or not meta["name"]:
        warnings.append("skipped a plugin: its plugin.json is unreadable, not valid JSON or has no name")
        return None
    return dict(meta)


def _read_project(
    project: Path,
    items: list[Item],
    warnings: list[str],
    relations: list[Relation],
    bodies: dict[str, str],
    secrets: set[str],
    entry: dict[str, Any],
    settings: dict[str, Any],
) -> None:
    """Items from a repo's `.claude/` and `.mcp.json`, scope `project`. Warnings show `<project>`, never the path."""
    root = project.resolve()
    first, mine = len(items), list[str]()
    claude = root / ".claude"
    if claude.is_dir() and _contained(claude, root, "project/", mine):
        _read_root(claude, "project/", items, mine, relations, bodies, secrets, None, root)
    mcp_file = root / ".mcp.json"
    if mcp_file.is_file() and _contained(mcp_file, root, "project/", mine):
        data = _load(mcp_file, mine, "project/.mcp.json")
        if data is not None:
            _add_project_servers(data, "project/", entry, settings, items, mine, secrets)
    items[first:] = [replace(i, scope="project") for i in items[first:]]
    for warning in mine:  # _shown wrote ~/... for a repo under home, the absolute path elsewhere
        warnings.append(warning.replace(_shown(root), "<project>").replace(str(root), "<project>"))


def read_items(
    config_dir: Path, lockfile: Path | None = None, project: Path | None = None, progress: Progress | None = None
) -> tuple[list[Item], list[str], list[Relation], dict[str, str]]:
    """`lockfile` is the skills CLI's lockfile; None turns origins off (no origin is set and the file is never opened)."""
    items: list[Item] = []
    warnings: list[str] = []
    relations: list[Relation] = []
    bodies: dict[str, str] = {}  # skill/agent Item id -> file text after the frontmatter
    config_dir = Path(config_dir)
    secrets = read_secrets(config_dir, project)
    lock = None
    if lockfile is not None:
        lock, lock_warnings = read_lock(lockfile, secrets)
        warnings += lock_warnings
    settings = _quiet_json(config_dir / "settings.json")
    if (config_dir / ".credentials.json").exists():
        # only for the warning; read_secrets takes the values (every depth, so a secret is never skipped)
        if _depth(_load(config_dir / ".credentials.json", warnings, ".credentials.json")) > MAX_NESTING:
            warnings.append(f"{CREDENTIALS} is nested unusually deeply; it was read in full but may be malformed")
    # first, so a hook can link to a user-scope server
    entries = _read_claude_json(config_dir, items, warnings, secrets, settings, Path(project) if project is not None else None)
    notify = progress or (lambda _: None)
    notify(ProgressEvent("mcp", len(items), len(items)))
    _read_root(config_dir, "", items, warnings, relations, bodies, secrets, lock, config_dir)
    enabled = settings.get("enabledPlugins", {})
    keys, clean = _installed(config_dir)
    if not clean:
        warnings.append("skipped malformed entries in installed_plugins.json")
    roots = _plugin_roots(config_dir)
    notify(ProgressEvent("skills", 1, 1 + len(roots)))
    for n, root in enumerate(roots, 2):
        notify(ProgressEvent("skills", n, 1 + len(roots)))
        meta = _manifest(root, warnings)
        if meta is None:
            continue
        plugin = Item(f"{SOURCE}:plugin:{meta['name']}", "plugin", meta["name"], meta.get("description", ""), SOURCE)
        if any(i.id == plugin.id for i in items):  # the same plugin installed twice (user and project scope)
            continue
        items.append(plugin)
        first = len(items)
        _plugin_servers(meta, root, f"{meta['name']}/", items, warnings, secrets)
        _read_root(root, f"{meta['name']}/", items, warnings, relations, bodies, secrets, lock, config_dir)
        relations += [Relation(plugin.id, item.id, "contains") for item in items[first:]]
        if lock is not None and (origin := clean_origin(meta["name"], secrets)):
            items[first - 1 :] = [replace(i, origin=origin) for i in items[first - 1 :]]
        key = keys.get(root) or f"{meta['name']}@{root.parent.parent.name}"
        if isinstance(enabled, dict) and enabled.get(key) is False:  # off in settings: still on the map, flagged, with its contents
            items[first - 1 :] = [replace(i, disabled=True) for i in items[first - 1 :]]
    notify(ProgressEvent("skills", len(items), len(items)))  # the final count, which is what a plain milestone line shows
    if project is not None:
        _read_project(Path(project), items, warnings, relations, bodies, secrets, entries.get(Path(project).resolve(), {}), settings)
    return items, warnings, relations, bodies


def _strings(node: object) -> Iterator[str]:
    """Every string under a JSON value; iterative so hostile nesting cannot exhaust the stack."""
    stack = [node]
    while stack:
        top = stack.pop()  # pragma: no mutate (the only mutant, top = None, never shrinks the stack: a timeout, not a survivor)
        if isinstance(top, str):
            yield top
        elif isinstance(top, dict):
            stack.extend(top.values())
        elif isinstance(top, list):
            stack.extend(top)


MAX_NESTING = 64
CREDENTIALS = ".credentials.json"


def _depth(node: object) -> int:
    """How deeply a JSON value nests, counted without recursion."""
    deepest, stack = 0, [(node, 0)]
    while stack:
        top, depth = stack.pop()
        deepest = max(deepest, depth)
        if isinstance(top, (dict, list)):
            stack.extend((child, depth + 1) for child in (top.values() if isinstance(top, dict) else top))
    return deepest


def _json_or_empty(path: Path) -> Any:
    return json.loads(path.read_text()) if path.exists() else {}


def _quiet_json(path: Path, *, only_object: bool = True) -> Any:
    """The parsed file, or {} when it is missing, unreadable, invalid or (by default) not an object. read_items gives the warning."""
    try:
        data = _json_or_empty(path)
    except (OSError, ValueError, RecursionError):
        return {}
    return data if isinstance(data, dict) or not only_object else {}


def _mcp_env(mcp: Path) -> list[str]:
    try:  # a malformed .mcp.json is read_items' warning to give; here it only means no env values to collect
        return [v for s in _quiet_json(mcp).get("mcpServers").values() for v in _strings(s.get("env"))]
    except (OSError, ValueError, AttributeError, RecursionError):
        return []


def _env_values(settings: Path, mcp: Path) -> list[str]:
    return [*_strings(_quiet_json(settings).get("env")), *_mcp_env(mcp)]


def _listed_projects(config_dir: Path) -> list[Path]:
    """Existing folders of the `.claude.json` project keys, for their `.mcp.json` env values. Nothing else is taken from that file."""
    path = _claude_json(config_dir, [])
    data = _load(path, [], "") if path else None  # pragma: no mutate (equivalent: the label only feeds a discarded warning)
    projects = data.get("projects") if isinstance(data, dict) else None
    return [d for key in projects if (d := _project_dir(key))] if isinstance(projects, dict) and LOCAL_SCOPE else []


def read_secrets(config_dir: Path, project: Path | None = None) -> set[str]:
    """Secret values held in the config's own secret-bearing files, and a --project repo's settings and .mcp.json env values.
    Never reads the process environment or anything else."""
    config_dir = Path(config_dir)
    plugin_roots = _plugin_roots(config_dir)
    auth = _quiet_json(config_dir / ".credentials.json", only_object=False)  # pragma: no mutate (None is as falsy as False)
    values = list(_strings(auth))  # an auth file: every value is secret
    for root in [config_dir, *plugin_roots]:
        values += _env_values(root / "settings.json", root / ".mcp.json")
    for folder in _listed_projects(config_dir):
        values += _mcp_env(folder / ".mcp.json")
    if project is not None:
        try:  # a repo's malformed settings.json is read_items' warning to give
            values += _env_values(Path(project) / ".claude" / "settings.json", Path(project) / ".mcp.json")
        except (OSError, ValueError, AttributeError, RecursionError):
            pass
    dotenv = config_dir / ".env"
    if dotenv.exists():
        for line in dotenv.read_text(errors="replace").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                values.append(line.split("=", 1)[1].strip().strip("\"'"))
    # shortcut: values under 8 chars are skipped so "1" or "true" doesn't get redacted everywhere; a short real secret would leak.
    return {v for v in values if len(v) >= 8}


def _env_in(node: object) -> Iterator[str]:
    """Every string under an `env` key, at any depth."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _strings(value) if key == "env" else _env_in(value)
    elif isinstance(node, list):
        for value in node:
            yield from _env_in(value)


def pack_secrets(root: Path) -> set[str]:
    """Secret values a pack's own manifests carry in `env`. Reads only these files inside root, never a `.env`."""
    values: list[str] = []
    for name in (".mcp.json", "settings.json", ".claude-plugin/plugin.json"):
        try:
            values += _env_in(json.loads((root / name).read_text()))
        except (OSError, ValueError, RecursionError):
            pass
    return {v for v in values if len(v) >= 8}


MAX_PACK_FILE = 1_000_000
# A YAML anchor or alias where a value starts. Expanding aliases turns 1 KB of frontmatter into gigabytes, so such a pack is refused.
_YAML_REFERENCE = re.compile(r"(?:^|[:\-\[{,])[ \t]*[&*][\w-]+", re.MULTILINE)


def _vet_pack_files(root: Path, meta: dict[str, Any] | None) -> None:
    """Refuse (ValueError) a frontmatter with a YAML anchor or alias, and a declared MCP file over the size cap, before either is read."""
    for pattern in ("SKILL.md", "skills/*/SKILL.md", "skills/synced/*/*/SKILL.md", "agents/*.md", "commands/*.md"):
        for path in _inside(root, pattern, "pack", []):
            parts = path.read_text().split("---") if path.is_file() else []
            if len(parts) > 1 and _YAML_REFERENCE.search(parts[1]):
                raise ValueError
    declared = meta.get("mcpServers") if meta else None
    for entry in declared if isinstance(declared, list) else [declared]:
        if isinstance(entry, str) and (root / entry).is_file() and (root / entry).stat().st_size > MAX_PACK_FILE:
            raise ValueError


def read_pack(root: Path) -> tuple[str, str, list[Item], list[str], list[Relation]]:
    """(pack name, layout "plugin"|"pack"|"skill", items, warnings, relations); reads only inside root. The caller has already refused
    symlinks pointing out of root (preview.check_tree); `_inside` refuses them again. Bodies are dropped, nothing is run."""
    root = Path(root).resolve()
    manifest = root / ".claude-plugin" / "plugin.json"
    if manifest.is_file():
        layout = "plugin"
    elif any((root / part).exists() for part in ("skills", "agents", "commands", ".mcp.json", "hooks/hooks.json")):
        layout = "pack"
    elif (root / "SKILL.md").is_file():
        layout = "skill"
    else:
        raise ValueError(f"No plugin, skill pack or SKILL.md found in {root.name}.")
    items: list[Item] = []
    warnings: list[str] = []
    relations: list[Relation] = []
    name = root.name
    secrets = pack_secrets(root)
    try:
        declared_in: Any = json.loads(manifest.read_text()) if layout == "plugin" else None
        _vet_pack_files(root, declared_in)
        if layout == "skill":
            meta, problem = _frontmatter(root / "SKILL.md")
            if problem:
                warnings.append(problem)
            if meta.get("name") and meta.get("description"):
                items.append(Item(f"{SOURCE}:skill:{root.name}/{meta['name']}", "skill", meta["name"], meta["description"], SOURCE))
            else:
                warnings.append("skipped SKILL.md: it needs a name and a description")
        else:
            scope = f"{name}/"
            if layout == "plugin":
                meta = declared_in
                name = meta["name"]
                if not isinstance(name, str) or not name:
                    raise ValueError
                scope = f"{name}/"
                about = meta.get("description", "")
                plugin = Item(f"{SOURCE}:plugin:{name}", "plugin", name, about if isinstance(about, str) else "", SOURCE)
                items.append(plugin)
                _plugin_servers(meta, root, scope, items, warnings, secrets)
            _read_root(root, scope, items, warnings, relations, {}, secrets, None, root)
            if any(not isinstance(i.name, str) or not isinstance(i.description, str) for i in items):
                warnings.append("skipped an item: its name or description is not text")
                items[:] = [i for i in items if isinstance(i.name, str) and isinstance(i.description, str)]
            if layout == "plugin":
                relations += [Relation(plugin.id, item.id, "contains") for item in items[1:]]
    except (KeyError, TypeError, AttributeError, ValueError, OSError, RecursionError):
        raise ValueError("could not read the pack: malformed file") from None
    # Warnings name files by their path; the pack folder's own path (absolute, or `~/` under home) becomes the pack name.
    for path in sorted({str(root), _shown(root)}, key=len, reverse=True):
        warnings = [w.replace(path, name) for w in warnings]
    return name, layout, items, warnings, relations
