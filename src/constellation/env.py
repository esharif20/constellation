"""Load KEY=VALUE lines from a .env file into the environment. The file holds the user's API key: never print its contents."""

import os
from pathlib import Path


def load_env(path: Path = Path(".env")) -> None:
    """Read `path` if it exists. A variable already set in the environment wins over the file."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip().removeprefix("export ")
        if line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        # shortcut: no inline comments or multi-line values; enough for a one-line API key.
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
