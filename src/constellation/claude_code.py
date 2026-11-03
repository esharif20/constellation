"""Claude Code Source adapter: reads a config dir, emits harness-neutral Items (ADR 0001)."""
import json
from pathlib import Path

import yaml

from .models import Item

SOURCE = "claude-code"


def _frontmatter(path: Path) -> dict:
    return yaml.safe_load(path.read_text().split("---", 2)[1])


def read_items(config_dir: Path) -> tuple[list[Item], list[str]]:
    items, warnings = [], []
    config_dir = Path(config_dir)
    for kind, pattern in (("skill", "skills/*/SKILL.md"), ("agent", "agents/*.md")):
        for path in sorted(config_dir.glob(pattern)):
            meta = _frontmatter(path)
            name, description = meta["name"], meta.get("description")
            if not description:
                warnings.append(f"skipped {kind} '{name}': no description ({path})")
                continue
            items.append(Item(f"{SOURCE}:{kind}:{name}", kind, name, description, SOURCE))
    mcp_file = config_dir / ".mcp.json"
    if mcp_file.exists():
        for name, server in json.loads(mcp_file.read_text())["mcpServers"].items():
            # Connectors live in the user's claude.ai account, not on disk; a remote (url) server is the closest local signal.
            kind = "connector" if "url" in server else "mcp_server"
            description = server.get("url") or " ".join([server["command"], *server.get("args", [])])
            items.append(Item(f"{SOURCE}:{kind}:{name}", kind, name, description, SOURCE))
    settings_file = config_dir / "settings.json"
    if settings_file.exists():
        for event, groups in json.loads(settings_file.read_text()).get("hooks", {}).items():
            for group in groups:
                name = ":".join(filter(None, [event, group.get("matcher")]))
                for handler in group["hooks"]:
                    # Index keeps ids unique when several handlers share an event and matcher.
                    id_ = f"{SOURCE}:hook:{name}:{len(items)}"
                    items.append(Item(id_, "hook", name, handler["command"], SOURCE))
    return items, warnings
