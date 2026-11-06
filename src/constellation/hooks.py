"""Session-start weight: what SessionStart and UserPromptSubmit hooks inject before you type, read statically.
Nothing is ever executed; the size comes from literal echo/printf text or a script file inside the config dir."""

import re
import shlex
from pathlib import Path

from .claude_code import SOURCE, _manifest, _plugin_roots
from .models import Item

PROMPT_TIME = ("SessionStart", "UserPromptSubmit")
_DYNAMIC = re.compile(r"[$`|;&<>()\n]")  # anything the shell would expand, chain, redirect or substitute


def _command_text(command: str, config_dir: Path, plugin_root: Path | None) -> str | None:
    if plugin_root:
        command = command.replace("${CLAUDE_PLUGIN_ROOT}", str(plugin_root))
    if _DYNAMIC.search(command):
        return None
    try:
        words = shlex.split(command)
    except ValueError:
        return None
    if words and words[0] in ("echo", "printf"):
        # shortcut: printf escapes and format specifiers are not interpreted, so its size is approximate; fine for a weight.
        return " ".join(w for w in words[1:] if not re.fullmatch(r"-[neE]+", w))
    for word in words:
        path = Path(word)
        if path.is_absolute():
            try:
                resolved = path.resolve()
                if resolved.is_file() and resolved.is_relative_to(config_dir.resolve()):
                    # shortcut: invalid UTF-8 becomes U+FFFD, so the byte count of such a script is slightly off.
                    return resolved.read_bytes().decode(errors="replace")
            except OSError:
                pass
            return None
    return None


def static_hook_texts(config_dir: Path, items: list[Item]) -> dict[str, str | None]:
    """Hook Item id -> the text it statically injects, or None when that cannot be known. Only prompt-time hooks are listed."""
    config_dir = Path(config_dir)
    roots = {meta["name"]: r for r in _plugin_roots(config_dir) if (meta := _manifest(r, []))}
    texts: dict[str, str | None] = {}
    for item in items:
        if item.kind != "hook" or item.name.split(":")[0] not in PROMPT_TIME:
            continue
        root = next((r for name, r in roots.items() if item.id.startswith(f"{SOURCE}:hook:{name}/")), None)
        texts[item.id] = _command_text(item.description, config_dir, root)
    return texts
