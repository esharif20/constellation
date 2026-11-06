"""Contract types for the smarter verdict (docs/design/smarter-verdict.md §3.1, §4.1, §5.4). No logic."""

from dataclasses import dataclass, field
from typing import Literal, TypedDict

Tier = Literal["keep", "keep_rare", "review", "redundant", "could_go", "too_early", "off", "untracked"]
Confidence = Literal["high", "medium", "low"]
Action = Literal["none", "remove", "disable_plugin", "remove_twin", "use_underlying", "move_to_project", "fix_description"]
Group = Literal["safe", "look", "wait"]
Trend = Literal["rising", "steady", "fading", "new"]
PurposeClass = Literal["everyday", "occasional", "rare"]


@dataclass(frozen=True)
class Reason:
    code: str  # stable, e.g. "never_seen", "duplicate_loser", "rare_purpose"
    text: str  # plain English, max 90 chars, redacted


@dataclass(frozen=True)
class Assessment:
    id: str
    tier: Tier
    label: str  # "Keep", "Keep (rarely needed)", "Review", "Likely redundant", "Could go", "Not enough history yet", ...
    confidence: Confidence | None  # None for off / untracked
    reasons: tuple[Reason, ...]  # 1-3, most important first
    action: Action
    saves: int | None  # always-on tokens per session start; None = unknown, never 0
    risk: int  # 1 low, 2 medium, 4 high
    group: Group | None
    recheck_after: int | None  # active days of extra history that would settle a too_early / keep_rare verdict
    twin_id: str | None = None  # remove_twin: the id of the Item this was compared with (the one that stays)


@dataclass(frozen=True)
class ItemEvidence:  # per-Item fields of §2.2 (subset the engine needs)
    count: int = 0
    sessions_used: int = 0
    days_used: int = 0
    last_used: str | None = None
    idle_active_days: int | None = None
    mean_gap: float | None = None
    trend: Trend | None = None
    percentile: int | None = None  # 0-100, rank among same-kind tracked Items by decayed use
    purpose_class: PurposeClass = "everyday"
    vague: bool = False
    always_on: int | None = None
    first_seen: str | None = None
    changed_on: str | None = None
    pinned: bool = False
    referenced_by: tuple[str, ...] = ()


@dataclass(frozen=True)
class Evidence:  # setup-wide fields of §2.1
    sessions: int
    active_days: int
    span_days: int
    sessions_per_day: float
    projects: dict[str, tuple[str | None, int]]  # project hash -> (last active day, sessions)
    skipped_share: float
    items: dict[str, ItemEvidence] = field(default_factory=dict)


@dataclass(frozen=True)
class ItemHabits:  # per-Item output of profile() (§3.3)
    decayed_use: float = 0.0
    all_time: int = 0
    trend: Trend | None = None
    percentile: int | None = None
    co_used: tuple[tuple[str, float], ...] = ()  # (partner id, lift)
    projects_used: int = 0
    top_project_share: float = 0.0
    # Additive learner outputs (habits.profile). Probabilities are P(used in a given active session), recency-weighted.
    use_prob: float = 0.0  # Beta-Binomial posterior mean
    prob_low: float = 0.0  # 90% credible interval; wide when there is little history
    prob_high: float = 1.0
    prior_prob: float | None = None  # mean borrowed from neighbours; a prior, never evidence
    prior_from: Literal["group", "kind"] | None = None
    typical_gap: float | None = None  # median gap between use days, in active days; None below 3 use days
    idle_active_days: int | None = None  # active days since the last use; None when never used
    overdue: bool = False  # idle for more than OVERDUE_MULT typical gaps
    needs: tuple[tuple[str, float], ...] = ()  # (partner id, P(partner used | this used)) for one-way dependencies
    project_shares: tuple[tuple[str, float], ...] = ()  # (project hash, share of this Item's uses), largest first


@dataclass(frozen=True)
class Habits:  # profile(ledger, today) result (§3.3)
    active_days: int
    projects_active: int
    items: dict[str, ItemHabits] = field(default_factory=dict)


class BriefRow(TypedDict, total=False):  # a Suggestion row (§5.4)
    id: str
    kind: str
    item_ids: list[str]
    removes: str | None
    reason: str
    saves: int | None
    tier: Tier
    confidence: Confidence | None
    reasons: list[dict[str, str]]


class BriefGroup(TypedDict, total=False):
    rows: list[BriefRow]
    saves: int
    unknown: int


class WaitSummary(TypedDict):
    code: str
    count: int
    recheck_after: int | None


class BriefWait(TypedDict):
    summary: list[WaitSummary]
    rows: list[BriefRow]


class BriefRange(TypedDict):
    low: int
    high: int
    per_day: tuple[int, int]
    unknown: int


class BriefResponse(TypedDict):
    evidence: dict[str, object]
    safe: BriefGroup
    look: BriefGroup
    wait: BriefWait
    range: BriefRange
    scope: dict[str, object]
    checklist: dict[str, object]
