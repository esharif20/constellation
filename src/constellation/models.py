from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

LLM = Callable[[str], str]  # prompt in, reply out
Embedder = Callable[[list[str]], list[list[float]]]  # texts in, one vector per text out
TokenCounter = Callable[[list[str]], list[int]]  # texts in, one token count per text out


@dataclass(frozen=True)
class Item:
    id: str
    kind: str
    name: str
    description: str
    source: str
    disabled: bool = False  # a plugin switched off in enabledPlugins, and what it contains: kept on the map, shown dimmed
    origin: str | None = None  # the pack, plugin or "claude.ai" it came from; local display data, never sent to a provider (origins.py)
    scope: str = "global"  # "project" for Items read from --project PATH and local/<n>/ MCP servers
    project: str | None = None  # opaque key (p1..pN) of the project an Item lives in; never a label or path


@dataclass(frozen=True)
class Relation:
    source: str  # Item id
    target: str  # Item id
    kind: str  # "contains", "triggers"


@dataclass(frozen=True)
class Cluster:
    name: str  # the free-text label of the member nearest the cluster centre
    item_ids: tuple[str, ...]


@dataclass(frozen=True)
class Cost:
    always_on: int | None  # tokens paid every session; None = unknown
    on_use: int | None  # tokens paid only when invoked; None = unknown


@dataclass(frozen=True)
class Weight:
    bytes: int | None  # statically known size of what a prompt-time hook injects; None = unknown
    tokens: int | None  # counted only with --count-bodies (or already cached); None = not counted


Verdict = Literal["duplicate", "wrapper", "overlap", "distinct"]


@dataclass(frozen=True)
class Overlap:
    a_id: str  # Item ids; a_id < b_id, except for a wrapper, where a_id is the wrapper and b_id is what it calls
    b_id: str
    verdict: Verdict
    reason: str  # one plain-English line


@dataclass(frozen=True)
class Usage:
    count: int
    last_used: str | None


@dataclass(frozen=True)
class UsageWindow:
    files: int
    first: str | None
    last: str | None
    skipped: int


@dataclass(frozen=True)
class ProjectUsage:
    projects: dict[str, str] = field(default_factory=dict)  # opaque key p1..pN -> display label; local only
    by_project: dict[str, dict[str, Usage]] = field(default_factory=dict)  # Item id -> key -> Usage
    current: str | None = None  # key of --project PATH, else None


@dataclass
class Constellation:
    items: list[Item] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)  # Item id -> free-text purpose label, set when scan() gets an llm
    clusters: list[Cluster] = field(default_factory=list)
    costs: dict[str, Cost] = field(default_factory=dict)  # Item id -> Context cost, set when scan() gets a token counter
    overlaps: list[Overlap] = field(default_factory=list)  # sorted by (a_id, b_id)
    hook_weights: dict[str, Weight] = field(default_factory=dict)  # hook Item id -> what it injects at SessionStart / UserPromptSubmit
    usage: dict[str, Usage] = field(default_factory=dict)
    usage_window: UsageWindow | None = None
    projects: dict[str, str] = field(default_factory=dict)  # key -> label; local only, dropped by snapshot()
    usage_by_project: dict[str, dict[str, Usage]] = field(default_factory=dict)  # kept apart from `usage` so nothing else sees keys
    current_project: str | None = None
    memory_bytes: int | None = None  # size of the user CLAUDE.md, from stat only; None when absent
    scanned_at: str | None = None  # UTC date of the scan, set by the CLI; dropped by snapshot()
    setup: str | None = None  # hash of the config dir, keys the scan history; dropped by snapshot()
