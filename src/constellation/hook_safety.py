"""Read-only hook safety lens over saved scan data."""

from typing import Any

CAN_BLOCK = {"UserPromptSubmit", "PreToolUse", "PermissionRequest", "Stop", "SubagentStop"}
PHASES = {
    "SessionStart": "session_start",
    "UserPromptSubmit": "before_prompt",
    "PreToolUse": "each_tool_call",
    "PostToolUse": "each_tool_call",
    "PermissionRequest": "each_tool_call",
}
PHASE_ORDER = ("before_prompt", "session_start", "each_tool_call", "other")


def hook_safety(data: dict[str, Any]) -> list[dict[str, Any]]:
    mcp_hooks = {relation["source"] for relation in data.get("relations", []) if relation["kind"] == "triggers"}
    rows = []
    for item in data.get("items", []):
        if item["kind"] != "hook" or item.get("disabled"):
            continue
        parts = item["name"].split(":", 1)
        weight = data.get("hook_weights", {}).get(item["id"], {})
        rows.append(
            {
                "id": item["id"],
                "name": item["name"],
                "event": parts[0],
                "matcher": parts[1] if len(parts) == 2 else None,
                "phase": PHASES.get(parts[0], "other"),
                "can_block": parts[0] in CAN_BLOCK,
                # shortcut: an mcp_tool hook whose server was not found reads as shell; upgrade when the scan stores the handler type
                "runs": "mcp_tool" if item["id"] in mcp_hooks else "shell",
                "bytes": weight.get("bytes"),
                "tokens": weight.get("tokens"),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            PHASE_ORDER.index(row["phase"]),
            not row["can_block"],
            row["bytes"] is None,
            -(row["bytes"] or 0),
            row["name"],
            row["id"],
        ),
    )
