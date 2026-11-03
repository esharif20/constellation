from pathlib import Path

from .claude_code import read_items
from .models import Constellation, Item


def scan(config_dir: Path, llm=None, embedder=None) -> Constellation:
    # llm/embedder are the provider seam; unused until the LLM boundary ticket (#3).
    items, warnings = read_items(config_dir)
    return Constellation(items, warnings)


__all__ = ["scan", "Constellation", "Item"]
