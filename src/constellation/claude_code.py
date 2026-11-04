"""Claude Code Source adapter: reads a config dir, emits harness-neutral Items (ADR 0001)."""

import json
import re
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path, PurePath
from typing import Any
from urllib.parse import urlsplit

import yaml

from .models import Item, Relation
from .origins import Found, find, read_lock
from .origins import clean as clean_origin
from .redact import redact

SOURCE = "claude-code"
LOCAL_SCOPE = True  # approved deviation from plan A item 8: read project/local-scope servers from .claude.json; False drops them
DESCRIPTION_CAP = 200  # a command's first line can be a whole paragraph
_SCHEMES = {"http", "https", "ws", "wss"}


def _shown(path: Path) -> str:
    """The path as shown in warnings: the home folder written as `~`, so the scan JSON never holds the username."""
    try:
        return f"~/{path.relative_to(Path.home())}"
    except ValueError:
        return str(path)


def _frontmatter(path: Path) -> tuple[dict[str, Any], str | None]:
    """The file's frontmatter, and a warning if it was not clean. Real files are not always valid YAML (an unquoted ': ' in a
    description), and Claude Code still loads them, so fall back to reading name and description line by line."""
    parts = path.read_text().split("---", 2)
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
    except (OSError, ValueError):
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
    if config_dir.name != ".claude":
        return None
    beside = config_dir.parent / ".claude.json"
    if not beside.exists():
        warnings.append("no .claude.json found beside the config dir, so user-scope MCP servers are not listed")
        return None
    return beside


def _read_claude_json(config_dir: Path, items: list[Item], warnings: list[str], secrets: set[str]) -> None:
    """User and local-scope MCP servers. The file also holds OAuth tokens: it is parsed in memory, only the `mcpServers` shapes are
    taken, and nothing else from it is kept, logged or put in a warning."""
    path = _claude_json(config_dir, warnings)
    data = _load(path, warnings, ".claude.json") if path else None
    if not isinstance(data, dict):
        return
    _add_servers(data.get("mcpServers", {}), "user/", items, warnings, secrets, ".claude.json")
    projects = data.get("projects")
    if not LOCAL_SCOPE or not isinstance(projects, dict):
        return
    # The project path stays out of the id (it holds the username); a per-scan index in sorted path order keeps same-named servers apart.
    having = [p for p in sorted(projects, key=str) if isinstance(projects[p], dict) and projects[p].get("mcpServers")]
    for number, project in enumerate(having, 1):
        _add_servers(projects[project]["mcpServers"], f"local/{number}/", items, warnings, secrets, ".claude.json")


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
            items.append(Item(f"{SOURCE}:{kind}:{scope}{extra}{name}", kind, name, description, SOURCE, origin=origin))
            bodies[items[-1].id] = path.read_text().split("---", 2)[2].strip()  # loaded only when invoked: the on-use text
    for path in _inside(root, "commands/*.md", scope, warnings):
        parsed = _command(path, warnings)
        if parsed is None:
            continue
        description, name = redact(parsed[0], secrets), parsed[1]
        if not description:
            warnings.append(f"skipped command '{name}': no description ({path})")
            continue
        items.append(Item(f"{SOURCE}:command:{scope}{name}", "command", name, description, SOURCE))
    mcp_file = root / ".mcp.json"
    if mcp_file.exists():
        data = _load(mcp_file, warnings, f"{scope or 'config'}.mcp.json")
        if data is not None:
            _add_servers(data, scope, items, warnings, secrets, f"{scope or 'config'}.mcp.json")
    # User hooks live in settings.json; plugin hooks in hooks/hooks.json.
    for hooks_file in (root / "settings.json", root / "hooks" / "hooks.json"):
        if not hooks_file.exists():
            continue
        for event, groups in json.loads(hooks_file.read_text()).get("hooks", {}).items():
            for group in groups:
                name = ":".join(filter(None, [event, group.get("matcher")]))
                for handler in group["hooks"]:
                    # Index keeps ids unique when several handlers share an event and matcher.
                    id_ = f"{SOURCE}:hook:{scope}{name}:{len(items)}"
                    if handler["type"] == "mcp_tool":
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


def _plugin_manifests(config_dir: Path) -> list[Path]:
    """One manifest per plugin: the version installed_plugins.json names, else the newest cached one (stale versions duplicate ids)."""
    named = set(_installed(config_dir)[0])
    newest: dict[Path, Path] = {}
    for manifest in sorted(config_dir.glob("plugins/cache/*/*/*/.claude-plugin/plugin.json")):
        root = manifest.parent.parent
        if not named or root in named:
            newest[root.parent] = manifest  # sorted, so the last version of a plugin wins when nothing names one
    cache = config_dir / "plugins" / "cache"
    for root in sorted(named):  # a local-directory marketplace installs outside the cache
        if not root.is_relative_to(cache) and (root / ".claude-plugin" / "plugin.json").exists():
            newest[root] = root / ".claude-plugin" / "plugin.json"
    return list(newest.values())


def read_items(config_dir: Path, lockfile: Path | None = None) -> tuple[list[Item], list[str], list[Relation], dict[str, str]]:
    """`lockfile` is the skills CLI's lockfile; None turns origins off (no origin is set and the file is never opened)."""
    items: list[Item] = []
    warnings: list[str] = []
    relations: list[Relation] = []
    bodies: dict[str, str] = {}  # skill/agent Item id -> file text after the frontmatter
    config_dir = Path(config_dir)
    secrets = read_secrets(config_dir)
    lock = None
    if lockfile is not None:
        lock, lock_warnings = read_lock(lockfile, secrets)
        warnings += lock_warnings
    _read_claude_json(config_dir, items, warnings, secrets)  # first, so a hook can link to a user-scope server
    _read_root(config_dir, "", items, warnings, relations, bodies, secrets, lock, config_dir)
    enabled = _json_or_empty(config_dir / "settings.json").get("enabledPlugins", {})
    keys, clean = _installed(config_dir)
    if not clean:
        warnings.append("skipped malformed entries in installed_plugins.json")
    for manifest in _plugin_manifests(config_dir):
        meta = json.loads(manifest.read_text())
        root = manifest.parent.parent
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
    return items, warnings, relations, bodies


def _strings(node: object) -> Iterator[str]:
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)


def _json_or_empty(path: Path) -> Any:
    return json.loads(path.read_text()) if path.exists() else {}


def read_secrets(config_dir: Path) -> set[str]:
    """Secret values held in the config's own secret-bearing files. Never reads the process environment or anything outside config_dir."""
    config_dir = Path(config_dir)
    plugin_roots = [m.parent.parent for m in _plugin_manifests(config_dir)]
    values = list(_strings(_json_or_empty(config_dir / ".credentials.json")))  # an auth file: every value is secret
    for root in [config_dir, *plugin_roots]:
        values += _strings(_json_or_empty(root / "settings.json").get("env", {}))
        try:  # a malformed .mcp.json is read_items' warning to give; here it only means no env values to collect
            values += [v for s in _json_or_empty(root / ".mcp.json").get("mcpServers", {}).values() for v in _strings(s.get("env", {}))]
        except (ValueError, AttributeError):
            pass
    dotenv = config_dir / ".env"
    if dotenv.exists():
        for line in dotenv.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                values.append(line.split("=", 1)[1].strip().strip("\"'"))
    # shortcut: values under 8 chars are skipped so "1" or "true" doesn't get redacted everywhere; a short real secret would leak.
    return {v for v in values if len(v) >= 8}
