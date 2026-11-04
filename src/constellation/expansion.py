"""On-demand MCP tool discovery. Connection settings are ephemeral and never returned."""

import json
import logging
import os
import re
import tempfile
import threading
from collections.abc import Awaitable, Callable, Iterator
from contextvars import ContextVar
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path, PurePath
from typing import Any, Literal
from urllib.parse import unquote, urlsplit

import anyio
from mcp import ClientSession, StdioServerParameters, stdio_client
from mcp.types import PaginatedRequestParams

from . import claude_code
from .claude_code import SOURCE, read_secrets
from .models import Item, Relation
from .redact import redact
from .redact import redact as redact_id

QUERY_TIMEOUT = 10.0
MAX_TOOLS = 1000
MAX_TEXT_BYTES = 4096
MAX_PAGES = 100
_MCP_FILE = ".mcp.json"
_INFLIGHT: set[tuple[Path, str]] = set()
_INFLIGHT_LOCK = threading.Lock()
_PRIVATE_QUERY: ContextVar[bool] = ContextVar("private_mcp_query", default=False)


class _PrivateDiagnostics(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not _PRIVATE_QUERY.get()


# Install on each emitting logger, including SDK children created after this import.
# Ancestor filters do not run for propagated records.
class _PrivateLogger(logging.Logger):
    def __init__(self, name: str, level: int = logging.NOTSET) -> None:
        super().__init__(name, level)
        if name in ("mcp", "client", "asyncio") or name.startswith("mcp."):
            self.addFilter(_PrivateDiagnostics())


logging.setLoggerClass(_PrivateLogger)
for _name in list(logging.Logger.manager.loggerDict):
    if _name in ("mcp", "client", "asyncio") or _name.startswith("mcp."):
        logging.getLogger(_name).addFilter(_PrivateDiagnostics())


@dataclass(frozen=True)
class Registration:
    command: str
    args: list[str]
    env: dict[str, str]
    cwd: Path


Query = Callable[[Registration], Awaitable[list[tuple[str, str | None]]]]


@dataclass(frozen=True)
class Expansion:
    item_id: str
    status: Literal["expanded", "unreachable", "not_expandable", "unavailable"]
    items: list[Item] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    message: str = ""


def _registrations(config_dir: Path) -> Iterator[tuple[str, dict[str, Any], Path]]:
    """Resolve private settings using the reader's naming/shape rules, without reading bodies."""
    secrets = read_secrets(config_dir)
    found: list[tuple[str, dict[str, Any], Path]] = []
    root = config_dir

    def add(data: Any, scope: str) -> None:
        for raw_name, settings in data.get("mcpServers", data).items():
            if not isinstance(settings, dict):
                raise ValueError
            name = redact_id(str(raw_name), secrets)
            registration = (f"{SOURCE}:mcp_server:{scope}{name}", settings, root)
            if registration not in found:
                found.append(registration)

    path = claude_code._claude_json(config_dir, [])
    state = claude_code._json_or_empty(path) if path else {}
    if isinstance(state, dict):
        add(state.get("mcpServers", {}), "user/")
        projects = state.get("projects")
        if claude_code.LOCAL_SCOPE and isinstance(projects, dict):
            having = [p for p in sorted(projects) if isinstance(projects[p], dict) and projects[p].get("mcpServers")]
            for number, project in enumerate(having, 1):
                add(projects[project]["mcpServers"], f"local/{number}/")
    add(claude_code._json_or_empty(config_dir / _MCP_FILE), "")
    plugins: set[str] = set()
    for manifest in claude_code._plugin_manifests(config_dir):
        meta = json.loads(manifest.read_text())
        name, root = meta["name"], manifest.parent.parent
        if name in plugins:
            continue
        plugins.add(name)
        scope = f"{name}/"
        declared = meta.get("mcpServers")
        for entry in declared if isinstance(declared, list) else [declared] if declared else []:
            if isinstance(entry, dict):
                add(entry, scope)
            elif isinstance(entry, str) and entry.lower().endswith((".mcpb", ".dxt")):
                add({PurePath(entry).stem: {"type": "bundle"}}, scope)
            elif isinstance(entry, str) and (root / entry).resolve().is_relative_to(root.resolve()) and (root / entry).is_file():
                add(claude_code._json_or_empty(root / entry), scope)
            else:
                raise ValueError
        add(claude_code._json_or_empty(root / _MCP_FILE), scope)
    yield from found


async def expand(data: Any, item_id: str, config_dir: Path | None, query: Query | None = None) -> Expansion:
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ValueError
    if not all(isinstance(i, dict) and all(isinstance(i.get(k), str) for k in ("id", "kind", "source")) for i in data["items"]):
        raise ValueError
    matches = [i for i in data["items"] if i["id"] == item_id]
    if not matches:
        raise KeyError
    if len(matches) != 1:
        raise ValueError
    item = matches[0]
    if item["kind"] != "mcp_server" or item["source"] != SOURCE:
        return Expansion(item_id, "not_expandable", message="This Item has no local MCP tool list.")
    if config_dir is None:
        return Expansion(item_id, "unavailable", message="Open with --config-dir to enable live Expansion.")
    try:
        config_dir = config_dir.resolve()
    except OSError:
        raise ValueError from None
    if not config_dir.is_dir():
        raise ValueError
    unreachable = Expansion(item_id, "unreachable", message="The configured MCP server is unreachable.")
    started = anyio.current_time()
    try:
        with anyio.fail_after(QUERY_TIMEOUT):
            registrations = await anyio.to_thread.run_sync(
                lambda: [(id_, settings, root) for id_, settings, root in _registrations(config_dir) if id_ == item_id],
                abandon_on_cancel=True,
            )
    except TimeoutError:
        return unreachable
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise ValueError from None
    if not registrations:
        return unreachable
    if len(registrations) != 1:
        raise ValueError
    _, settings, root = registrations[0]
    if "url" in settings or settings.get("type") == "bundle":
        return Expansion(item_id, "not_expandable", message="This Item has no local MCP tool list.")
    command, args, env = settings.get("command"), settings.get("args", []), settings.get("env", {})
    if (
        not isinstance(command, str)
        or not command
        or not isinstance(args, list)
        or not all(isinstance(v, str) for v in args)
        or not isinstance(env, dict)
        or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items())
    ):
        raise ValueError
    if any("$" in value for value in [command, *args, *env.values()]):
        return unreachable
    key = (config_dir, item_id)
    with _INFLIGHT_LOCK:
        if key in _INFLIGHT:
            return unreachable
        _INFLIGHT.add(key)
    items: list[Item] | None
    try:
        with anyio.fail_after(QUERY_TIMEOUT - (anyio.current_time() - started)):
            tools = await (query or query_tools)(Registration(command, args, env, root))
            items = await anyio.to_thread.run_sync(_tool_items, item_id, tools, config_dir, env, args, abandon_on_cancel=True)
    except* Exception:
        items = None
    finally:
        with _INFLIGHT_LOCK:
            _INFLIGHT.remove(key)
    if items is None:
        return unreachable
    return Expansion(item_id, "expanded", items, [Relation(item_id, i.id, "contains") for i in items], "Tools listed.")


def _validate_tools(tools: list[tuple[str, str | None]]) -> None:
    if len(tools) > MAX_TOOLS:
        raise ValueError
    for name, description in tools:
        if len(name.encode()) > MAX_TEXT_BYTES or len((description or "").encode()) > MAX_TEXT_BYTES:
            raise ValueError


def _tool_items(item_id: str, tools: list[tuple[str, str | None]], config_dir: Path, env: dict[str, str], args: list[str]) -> list[Item]:
    _validate_tools(tools)
    unique: dict[str, str | None] = {}
    for name, description in tools:
        if name in unique and unique[name] != description:
            raise ValueError
        unique[name] = description
    # Treat every explicit argument value as private, including short and --name=value forms.
    argument_values = []
    for arg in args:
        argument_values += [arg, *re.split(r"[=:\s/@?&#]+", unquote(arg))]
        for value in (arg, arg.partition("=")[2]):
            parts = urlsplit(value)
            argument_values += [unquote(parts.username or ""), unquote(parts.password or "")]
    known = [*read_secrets(config_dir), *(v for v in [*env.values(), *argument_values] if v)]
    return [
        Item(
            f"{item_id}:tool:{sha256(name.encode()).hexdigest()}",
            "mcp_tool",
            redact(name, known),
            redact(description or "", known),
            SOURCE,
        )
        for name, description in sorted(unique.items())
    ]


async def query_tools(registration: Registration) -> list[tuple[str, str | None]]:
    token = _PRIVATE_QUERY.set(True)
    try:
        with tempfile.TemporaryDirectory() as home, open(os.devnull, "w") as errlog:
            env = {
                "HOME": home,
                "LOGNAME": "constellation",
                "PATH": "/usr/bin:/bin",
                "SHELL": "/bin/sh",
                "TERM": "dumb",
                "USER": "constellation",
            }
            env.update(registration.env)
            parameters = StdioServerParameters(command=registration.command, args=registration.args, env=env, cwd=registration.cwd)
            async with stdio_client(parameters, errlog=errlog) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    tools: list[tuple[str, str | None]] = []
                    cursors: set[str] = set()
                    cursor = None
                    for _ in range(MAX_PAGES):
                        page = await session.list_tools(params=PaginatedRequestParams(cursor=cursor))
                        if len(tools) + len(page.tools) > MAX_TOOLS:
                            raise ValueError
                        page_tools = [(tool.name, tool.description) for tool in page.tools]
                        await anyio.to_thread.run_sync(_validate_tools, page_tools, abandon_on_cancel=True)
                        tools.extend(page_tools)
                        cursor = page.next_cursor
                        if cursor is None:
                            return tools
                        if cursor in cursors:
                            raise ValueError
                        cursors.add(cursor)
                    raise ValueError
    finally:
        _PRIVATE_QUERY.reset(token)
