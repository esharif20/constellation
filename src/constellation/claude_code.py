"""Claude Code Source adapter: reads a config dir, emits harness-neutral Items (ADR 0001)."""
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
    return items, warnings
