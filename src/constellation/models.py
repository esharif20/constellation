from dataclasses import dataclass, field


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


@dataclass
class Constellation:
    items: list[Item] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
