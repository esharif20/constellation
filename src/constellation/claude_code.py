"""Claude Code Source adapter: reads a config dir, emits harness-neutral Items (ADR 0001)."""
from pathlib import Path

import yaml

from .models import Item

SOURCE = "claude-code"


def read_items(config_dir: Path) -> tuple[list[Item], list[str]]:
    items, warnings = [], []
    for skill_file in sorted(Path(config_dir).glob("skills/*/SKILL.md")):
        _, front, _ = skill_file.read_text().split("---", 2)
        meta = yaml.safe_load(front)
        name, description = meta["name"], meta.get("description")
        if not description:
            warnings.append(f"skipped skill '{name}': no description ({skill_file})")
            continue
        items.append(Item(f"{SOURCE}:skill:{name}", "skill", name, description, SOURCE))
    return items, warnings
