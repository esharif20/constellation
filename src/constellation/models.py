from collections.abc import Callable
from dataclasses import dataclass, field

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


@dataclass
class Constellation:
    items: list[Item] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)  # Item id -> free-text purpose label, set when scan() gets an llm
    clusters: list[Cluster] = field(default_factory=list)
    costs: dict[str, Cost] = field(default_factory=dict)  # Item id -> Context cost, set when scan() gets a token counter
