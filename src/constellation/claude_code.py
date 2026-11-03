"""Claude Code Source adapter: reads a config dir, emits harness-neutral Items (ADR 0001)."""

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

from .models import Item, Relation

SOURCE = "claude-code"


def _frontmatter(path: Path) -> tuple[dict[str, Any], str | None]:
    """The file's frontmatter, and a warning if it was not clean. Real files are not always valid YAML (an unquoted ': ' in a
    description), and Claude Code still loads them, so fall back to reading name and description line by line."""
    parts = path.read_text().split("---", 2)
    if len(parts) < 3:
        return {}, f"no frontmatter in {path}"
    try:
        meta = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        lines = {m[1]: m[2].strip() for m in re.finditer(r"^(name|description):[ \t]*(.*)$", parts[1], re.MULTILINE)}
        return lines, f"frontmatter is not valid YAML, read name and description leniently ({path})"
    return (meta if isinstance(meta, dict) else {}), None


def _read_root(root: Path, scope: str, items: list[Item], warnings: list[str], relations: list[Relation], bodies: dict[str, str]) -> None:
    """Read the Items under one root: the config dir itself, or one plugin dir. `scope` keeps ids unique."""
    for kind, pattern in (("skill", "skills/*/SKILL.md"), ("agent", "agents/*.md")):
        for path in sorted(root.glob(pattern)):
            meta, problem = _frontmatter(path)
            if problem:
                warnings.append(problem)
            name, description = meta.get("name"), meta.get("description")
            if not name:
                warnings.append(f"skipped {kind} with no name ({path})")
                continue
            if not description:
                warnings.append(f"skipped {kind} '{name}': no description ({path})")
                continue
            items.append(Item(f"{SOURCE}:{kind}:{scope}{name}", kind, name, description, SOURCE))
            bodies[items[-1].id] = path.read_text().split("---", 2)[2].strip()  # loaded only when invoked: the on-use text
    mcp_file = root / ".mcp.json"
    if mcp_file.exists():
        for name, server in json.loads(mcp_file.read_text())["mcpServers"].items():
            # Connectors live in the user's claude.ai account, not on disk; a remote (url) server is the closest local signal.
            kind = "connector" if "url" in server else "mcp_server"
            description = server.get("url") or " ".join([server["command"], *server.get("args", [])])
            items.append(Item(f"{SOURCE}:{kind}:{scope}{name}", kind, name, description, SOURCE))
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
                        server_id = f"{SOURCE}:mcp_server:{scope}{handler['server']}"
                        if any(i.id == server_id for i in items):
                            relations.append(Relation(id_, server_id, "triggers"))
                    else:
                        description = handler["command"]
                    items.append(Item(id_, "hook", name, description, SOURCE))


def _plugin_manifests(config_dir: Path) -> list[Path]:
    """One manifest per plugin: the version installed_plugins.json names, else the newest cached one (stale versions duplicate ids)."""
    installed = _json_or_empty(config_dir / "plugins" / "installed_plugins.json").get("plugins", {})
    named = {Path(e["installPath"]) for entries in installed.values() for e in entries if "installPath" in e}
    newest: dict[Path, Path] = {}
    for manifest in sorted(config_dir.glob("plugins/cache/*/*/*/.claude-plugin/plugin.json")):
        root = manifest.parent.parent
        if not named or root in named:
            newest[root.parent] = manifest  # sorted, so the last version of a plugin wins when nothing names one
    return list(newest.values())


def read_items(config_dir: Path) -> tuple[list[Item], list[str], list[Relation], dict[str, str]]:
    items: list[Item] = []
    warnings: list[str] = []
    relations: list[Relation] = []
    bodies: dict[str, str] = {}  # skill/agent Item id -> file text after the frontmatter
    config_dir = Path(config_dir)
    _read_root(config_dir, "", items, warnings, relations, bodies)
    for manifest in _plugin_manifests(config_dir):
        meta = json.loads(manifest.read_text())
        plugin = Item(f"{SOURCE}:plugin:{meta['name']}", "plugin", meta["name"], meta.get("description", ""), SOURCE)
        items.append(plugin)
        first = len(items)
        _read_root(manifest.parent.parent, f"{meta['name']}/", items, warnings, relations, bodies)
        relations += [Relation(plugin.id, item.id, "contains") for item in items[first:]]
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
        for server in _json_or_empty(root / ".mcp.json").get("mcpServers", {}).values():
            values += _strings(server.get("env", {}))
    dotenv = config_dir / ".env"
    if dotenv.exists():
        for line in dotenv.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                values.append(line.split("=", 1)[1].strip().strip("\"'"))
    # shortcut: values under 8 chars are skipped so "1" or "true" doesn't get redacted everywhere; a short real secret would leak.
    return {v for v in values if len(v) >= 8}
