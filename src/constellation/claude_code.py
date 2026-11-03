"""Claude Code Source adapter: reads a config dir, emits harness-neutral Items (ADR 0001)."""
import json
from pathlib import Path

import yaml

from .models import Item, Relation

SOURCE = "claude-code"


def _frontmatter(path: Path) -> dict:
    return yaml.safe_load(path.read_text().split("---", 2)[1])


def _read_root(root: Path, scope: str, items: list[Item], warnings: list[str]) -> None:
    """Read the Items under one root: the config dir itself, or one plugin dir. `scope` keeps ids unique."""
    for kind, pattern in (("skill", "skills/*/SKILL.md"), ("agent", "agents/*.md")):
        for path in sorted(root.glob(pattern)):
            meta = _frontmatter(path)
            name, description = meta["name"], meta.get("description")
            if not description:
                warnings.append(f"skipped {kind} '{name}': no description ({path})")
                continue
            items.append(Item(f"{SOURCE}:{kind}:{scope}{name}", kind, name, description, SOURCE))
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
                    items.append(Item(id_, "hook", name, handler["command"], SOURCE))


def read_items(config_dir: Path) -> tuple[list[Item], list[str], list[Relation]]:
    items, warnings, relations = [], [], []
    config_dir = Path(config_dir)
    _read_root(config_dir, "", items, warnings)
    # shortcut: only the plugin cache layout (plugins/cache/<marketplace>/<plugin>/<version>), not installed_plugins.json.
    for manifest in sorted(config_dir.glob("plugins/cache/*/*/*/.claude-plugin/plugin.json")):
        meta = json.loads(manifest.read_text())
        plugin = Item(f"{SOURCE}:plugin:{meta['name']}", "plugin", meta["name"], meta.get("description", ""), SOURCE)
        items.append(plugin)
        first = len(items)
        _read_root(manifest.parent.parent, f"{meta['name']}/", items, warnings)
        relations += [Relation(plugin.id, item.id, "contains") for item in items[first:]]
    return items, warnings, relations
