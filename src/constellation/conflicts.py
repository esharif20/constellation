import re
from typing import Any


def conflicts(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Find deterministic collisions in a saved scan without reading the setup."""
    hooks: dict[str, list[str]] = {}
    servers: dict[str, list[str]] = {}
    phrases: dict[str, list[str]] = {}
    # shortcut: plugin servers are namespaced by Claude Code, so they are left out;
    # tool-name collisions need Expansion (#9) mcp_tool Items
    contained = {relation["target"] for relation in data.get("relations", []) if relation["kind"] == "contains"}
    for item in data["items"]:
        if item.get("disabled", False):
            continue
        if item["kind"] == "hook":
            hooks.setdefault(item["name"], []).append(item["id"])
        elif item["kind"] == "mcp_server" and item["id"] not in contained:
            servers.setdefault(item["name"], []).append(item["id"])
        elif item["kind"] == "skill":
            unique_phrases = {
                " ".join(quoted.lower().split()) for quoted in re.findall(r'["“]([^"”]{3,80})["”]', item.get("description", ""))
            }
            for phrase in unique_phrases:
                if len(phrase.split()) >= 2:
                    phrases.setdefault(phrase, []).append(item["id"])
    rows = []
    for name, ids in hooks.items():
        if len(ids) >= 2:
            event, _, matcher = name.partition(":")
            rows.append(
                {
                    "kind": "hook",
                    "key": name,
                    "item_ids": sorted(ids),
                    "reason": (
                        f"{len(ids)} hooks run on {event} ({matcher or 'every match'}). "
                        "Claude Code runs them in parallel, so their order is not fixed."
                    ),
                }
            )
    for name, ids in servers.items():
        if len(ids) >= 2:
            rows.append(
                {
                    "kind": "mcp_name",
                    "key": name,
                    "item_ids": sorted(ids),
                    "reason": (
                        f"{len(ids)} MCP servers are named {name}. Only one is used: local scope wins over project, project over user."
                    ),
                }
            )
    for phrase, ids in phrases.items():
        if len(ids) >= 2:
            rows.append(
                {
                    "kind": "trigger",
                    "key": phrase,
                    "item_ids": sorted(ids),
                    "reason": f'{len(ids)} skills claim the phrase "{phrase}", so either may answer it.',
                }
            )
    return sorted(rows, key=lambda row: (row["kind"], row["key"]))
