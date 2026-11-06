"""The smarter verdict engine (docs/design/smarter-verdict.md §2, §4, §7b, §7c, §7g). Pure: no IO, no provider call.

`data` is the saved scan (items, overlaps, conflicts, plugin_children, hook_bytes). Overlaps, conflicts, plugin_children,
hook_bytes, Evidence.items and Habits.items are keyed by Item *name*; Assessments are keyed by Item id.
"""

import math
import re
from dataclasses import dataclass, replace
from datetime import date
from typing import Any

from .verdict_types import Action, Assessment, Confidence, Evidence, Group, Habits, ItemEvidence, ItemHabits, PurposeClass, Reason, Tier

# Exposure to call a never-seen Item unused: (active days, sessions) for medium and for high (None = never high).
NEED: dict[str, tuple[tuple[int, int], tuple[int, int] | None]] = {
    "everyday": ((10, 15), (25, 40)),
    "occasional": ((30, 0), (60, 0)),
    "rare": ((90, 0), None),
}
COST_FLOOR = 50  # always-on tokens; below it removal is not worth the risk
GRACE_DAYS = 14  # added or changed this recently -> too_early
STALE_MIN = 30  # active days; a used Item is stale at max(STALE_MIN, STALE_MULT * mean_gap)
STALE_MULT = 3
BOTTOM_PCT = 10  # habit-based Review
TOP_PCT = 90  # percentile from which the reason says "in your top N%"
TOP_HALF = 50  # a partner counts as "used" from this percentile
MIN_SESSIONS = 15  # sessions that make a verdict confident
MOVE_MIN_USES = 3
MOVE_MIN_SHARE = 0.8
SKIP_LIMIT = 0.05
MAX_TEXT = 90

PURPOSE_CUES: dict[str, tuple[str, ...]] = {
    "rare": (
        "release",
        "changelog",
        "quarterly",
        "annual",
        "yearly",
        "tax",
        "invoice",
        "incident",
        "postmortem",
        "onboarding",
        "offboarding",
        "migration",
        "migrate",
        "upgrade",
        "audit",
        "interview",
        "retro",
    ),  # fmt: skip
    "occasional": ("deploy", "setup", "install", "scaffold", "new project", "init", "benchmark", "report", "review"),
}
LABELS: dict[str, str] = {
    "keep": "Keep",
    "keep_rare": "Keep (rarely needed)",
    "review": "Review",
    "redundant": "Likely redundant",
    "could_go": "Could go",
    "too_early": "Not enough history yet",
    "off": "Switched off",
    "untracked": "Not tracked",
}
LOWER: dict[str, Confidence] = {"high": "medium", "medium": "low", "low": "low"}

Item = dict[str, Any]


def clip(text: str) -> str:
    return text if len(text) <= MAX_TEXT else text[: MAX_TEXT - 1] + "…"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def purpose_cue(description: str, name: str) -> tuple[PurposeClass, str | None]:
    """Class and the first matching cue (whole word, case-insensitive). Narrow-file-type rule of §2.3 is not built."""
    text = f"{name} {description}".lower().replace("-", " ").replace("_", " ")
    for cls in ("rare", "occasional"):
        for cue in PURPOSE_CUES[cls]:
            if re.search(rf"\b{re.escape(cue)}\b", text):
                return cls, cue
    return "everyday", None


def purpose_class(description: str, name: str) -> PurposeClass:
    return purpose_cue(description, name)[0]


def specificity(description: str) -> tuple[int, bool]:
    """(word count, vague); vague = under 8 words, as triggers.py."""
    words = len(description.split())
    return words, words < 8


def referenced_by(item: Item, data: dict[str, Any]) -> tuple[str, ...]:
    """Names of enabled Items that lean on this one: a wrapper over it, or a description naming it (whole word)."""
    name = item["name"]
    found = {o["a"] for o in data.get("overlaps", []) if o["verdict"] == "wrapper" and o["b"] == name}
    pattern = re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])", re.IGNORECASE)
    for other in data["items"]:
        if other["name"] != name and not other.get("disabled") and pattern.search(other["description"]):
            found.add(other["name"])
    return tuple(sorted(found))


def evidence(data: dict[str, Any], habits: Habits, base: Evidence, pins: frozenset[str] = frozenset()) -> Evidence:
    """Fill the per-Item fields that come from the scan and the profile; `base` carries the ledger's setup-wide facts."""
    items: dict[str, ItemEvidence] = {}
    for item in data["items"]:
        name, description = item["name"], item["description"]
        fields: dict[str, Any] = {
            "purpose_class": purpose_class(description, name),
            "vague": specificity(description)[1],
            "always_on": item.get("always_on"),
            "pinned": item["id"] in pins,
            "referenced_by": referenced_by(item, data),
        }
        if (h := habits.items.get(name)) is not None:
            fields |= {"count": h.all_time, "trend": h.trend, "percentile": h.percentile}
        items[name] = replace(base.items.get(name, ItemEvidence()), **fields)
    return replace(base, items=items)


@dataclass(frozen=True)
class _Ctx:
    ev: Evidence
    habits: Habits
    today: date
    pins: frozenset[str]
    data: dict[str, Any]
    by_name: dict[str, Item]

    def ie(self, name: str) -> ItemEvidence:
        return self.ev.items.get(name, ItemEvidence())

    def hab(self, name: str) -> ItemHabits:
        return self.habits.items.get(name, ItemHabits())

    def pinned(self, item: Item) -> bool:
        return item["id"] in self.pins or self.ie(item["name"]).pinned

    def links(self, name: str, verdict: str) -> list[dict[str, str]]:
        return [o for o in self.data.get("overlaps", []) if o["verdict"] == verdict and name in (o["a"], o["b"])]


def need_confidence(cls: str, active_days: int, sessions: int) -> Confidence | None:
    medium, high = NEED[cls]
    if high is not None and active_days >= high[0] and sessions >= high[1]:
        return "high"
    if active_days >= medium[0] and sessions >= medium[1]:
        return "medium"
    return None


def _group(tier: Tier, action: Action, conf: Confidence | None, saves: int | None, seen: bool) -> Group | None:
    if tier in ("off", "keep"):
        return None
    if tier == "keep_rare":
        return None if seen else "wait"
    if tier in ("too_early", "untracked"):
        return "wait"
    if tier == "review":
        return "look" if action != "none" else "wait"
    return "safe" if conf == "high" and saves is not None and saves >= COST_FLOOR else "look"


def _make(
    ctx: _Ctx, item: Item, tier: Tier, conf: Confidence | None, code: str, text: str, action: Action = "none",
    recheck: int | None = None, label: str | None = None, twin: bool = False, extra: tuple[Reason, ...] = (),
) -> Assessment:  # fmt: skip
    saves = item.get("always_on") if action != "none" else None
    reversible = bool(item.get("origin")) or twin  # a pack/plugin can be reinstalled; a twin stays
    risk = 1 if action == "none" or (conf == "high" and reversible) else 2
    seen = ctx.ie(item["name"]).count > 0
    return Assessment(
        id=item["id"], tier=tier, label=label or LABELS[tier], confidence=conf, reasons=(Reason(code, clip(text)),) + extra,
        action=action, saves=saves, risk=risk, group=_group(tier, action, conf, saves, seen), recheck_after=recheck,
    )  # fmt: skip


def _penalised(ctx: _Ctx, conf: Confidence, item: Item, twin: bool = False) -> Confidence:
    """One step down for each of: many skipped files, hand-written with no twin (not reversible), thin sessions."""
    steps = (ctx.ev.skipped_share > SKIP_LIMIT) + (not item.get("origin") and not twin) + (ctx.ev.sessions < MIN_SESSIONS)
    for _ in range(steps):
        conf = LOWER[conf]
    return conf


def _loser(ctx: _Ctx, a: str, b: str) -> str:
    """§7b/O3: pinned stays, then the less used goes, then the more expensive, then the smaller id."""

    def key(name: str) -> tuple[bool, float, int]:
        item = ctx.by_name[name]
        return ctx.pinned(item), ctx.hab(name).decayed_use, -(item.get("always_on") or 0)

    return min(sorted((a, b), key=lambda n: ctx.by_name[n]["id"]), key=key)


def _top_half(ie: ItemEvidence) -> bool:
    return ie.percentile is not None and ie.percentile >= TOP_HALF


def _twin_loser(ctx: _Ctx, item: Item, other: str) -> Assessment:
    mine, theirs = ctx.ie(item["name"]).count, ctx.ie(other).count
    if mine and theirs and _top_half(ctx.ie(item["name"])):
        return _make(ctx, item, "review", "medium", "twin_both_used", f"{other} does the same job and you use both")
    conf: Confidence
    if not mine and theirs:
        text, conf = f"Does the same job as {other}; you used that {theirs} times, this one never", "high"
        if need_confidence("everyday", ctx.ev.active_days, ctx.ev.sessions) is None:
            conf = "medium"
    elif not mine:
        text, conf = f"Does the same job as {other}; neither has been used", "medium"
    else:
        text, conf = f"Does the same job as {other}, which you use more ({theirs} vs {mine} times)", "medium"
    return _make(ctx, item, "redundant", _penalised(ctx, conf, item, True), "duplicate_loser", text, "remove_twin", twin=True)


def _wrapper(ctx: _Ctx, item: Item, link: dict[str, str]) -> Assessment | None:
    name = item["name"]
    if link["a"] == name:  # this Item only hands off to link["b"]
        target = link["b"]
        if ctx.ie(name).count and not ctx.ie(target).count:
            return _make(ctx, item, "keep", "medium", "via_wrapper", f"You reach {target} through it")
        conf: Confidence = (
            "high" if not ctx.ie(name).count and need_confidence("everyday", ctx.ev.active_days, ctx.ev.sessions) else "medium"
        )
        return _make(
            ctx, item, "redundant", _penalised(ctx, conf, item, True), "wrapper", f"Only hands off to {target}", "use_underlying", twin=True
        )
    if ctx.ie(name).count == 0 and ctx.ie(link["a"]).count:
        return _make(ctx, item, "keep", "medium", "wrapped", f"{link['a']} calls it")
    return None


def _shadowed(ctx: _Ctx, item: Item) -> Assessment | None:
    for c in ctx.data.get("conflicts", []):
        if c["kind"] == "mcp_name" and item["kind"] == "mcp_server" and item["name"] in c["ids"]:
            scope = m.group(1) if (m := re.search(r"shadowed by (\w+) scope", c["detail"])) else "local"
            conf = _penalised(ctx, "high", item, True)
            return _make(ctx, item, "redundant", conf, "shadowed", f"Never loaded: the {scope} server with this name wins", "remove")
    return None


def _redundancy(ctx: _Ctx, item: Item) -> Assessment | None:
    name = item["name"]
    if (shadow := _shadowed(ctx, item)) is not None:
        return shadow
    for link in ctx.links(name, "duplicate"):
        other = link["b"] if link["a"] == name else link["a"]
        if _loser(ctx, name, other) == name:
            return _twin_loser(ctx, item, other)
        if ctx.ie(name).count == 0:
            return _make(ctx, item, "keep", "medium", "twin_loser", f"Its twin {other} could go")
    for link in ctx.links(name, "wrapper"):
        if (found := _wrapper(ctx, item, link)) is not None:
            return found
    return None


def _untracked(ctx: _Ctx, item: Item) -> Assessment | None:
    name, kind = item["name"], item["kind"]
    has_children = name in ctx.data.get("plugin_children", {}) or any(i.get("plugin") == name for i in ctx.data["items"])
    if kind not in ("hook", "command") and not (kind == "plugin" and not has_children):
        return None
    size = ctx.data.get("hook_bytes", {}).get(name)
    if size is None:
        text = "Not judged from usage; its cost is unknown"
    else:
        amount = f"{size / 1000:.1f} KB" if size >= 1000 else f"{size} bytes"
        event = name.split(":")[0]
        when = {"UserPromptSubmit": "before every prompt", "SessionStart": "at every session start"}.get(event, f"on every {event}")
        text = f"Adds {amount} {when}"
    return _make(ctx, item, "untracked", None, "hook_weight", text)


def _too_new(ctx: _Ctx, item: Item) -> Assessment | None:
    ie = ctx.ie(item["name"])
    ages = []
    for verb, day in (("Added", ie.first_seen), ("Changed", ie.changed_on)):
        if day is not None and 0 <= (age := (ctx.today - date.fromisoformat(day)).days) <= GRACE_DAYS:
            ages.append((age, verb))
    if not ages:
        return None
    age, verb = min(ages)
    return _make(ctx, item, "too_early", "low", "too_early", f"{verb} {_plural(age, 'day') + ' ago' if age else 'today'}")


def _used(ctx: _Ctx, item: Item) -> Assessment:
    name = item["name"]
    ie, hab = ctx.ie(name), ctx.hab(name)
    cost = item.get("always_on")
    if ctx.ev.active_days >= STALE_MIN and ie.idle_active_days is not None:
        gap = ie.mean_gap
        if ie.idle_active_days >= (max(STALE_MIN, STALE_MULT * gap) if gap else STALE_MIN):
            text = f"Not used in {ie.idle_active_days} active days" + (f"; you used it about every {gap:.0f} before" if gap else "")
            return _make(ctx, item, "review", "medium", "fading" if ie.trend == "fading" else "stale", text, "remove")
    if ie.count >= MOVE_MIN_USES and hab.top_project_share >= MOVE_MIN_SHARE and item.get("scope") != "project":
        where = "all in one repo" if hab.top_project_share >= 1 else "mostly in one repo"
        tail = f"; move it there to save {cost} elsewhere" if cost is not None else "; move it there"
        return _make(ctx, item, "review", "medium", "single_project", f"Used {ie.count} times, {where}{tail}", "move_to_project")
    if ie.percentile is not None and ie.percentile <= BOTTOM_PCT and ie.trend == "fading":
        return _make(ctx, item, "review", "low", "fading", f"Used {ie.count} times; in your bottom {BOTTOM_PCT}% and fading")
    conf: Confidence = "high" if ie.sessions_used >= MIN_SESSIONS else "medium"
    if ie.purpose_class == "rare":
        cue = purpose_cue(item["description"], name)[1] or "occasional"
        return _make(ctx, item, "keep_rare", conf, "rare_purpose", f"Used {ie.count} times; made for {cue} work", label="Keep")
    where = f" in {hab.projects_used} of {ctx.habits.projects_active} projects" if hab.projects_used and ctx.habits.projects_active else ""
    top = f"; in your top {100 - ie.percentile}%" if ie.percentile is not None and ie.percentile >= TOP_PCT else ""
    return _make(ctx, item, "keep", conf, "heavy_use", f"Used {ie.count} times{where}{top}")


def _recheck(ctx: _Ctx, cls: str) -> int:
    """Active days of extra history that would meet NEED.medium (days, and the sessions at the usual pace)."""
    (days, sessions), _ = NEED[cls]
    by_sessions = math.ceil((sessions - ctx.ev.sessions) / (ctx.ev.sessions_per_day or 1.0))
    return max(days - ctx.ev.active_days, by_sessions)


def _cost(ctx: _Ctx, item: Item) -> int | None:
    """Always-on tokens; a plugin without its own figure is the sum of its children."""
    own = item.get("always_on")
    if own is not None or item["kind"] != "plugin":
        return own
    return sum(filter(None, (c.get("always_on") for c in ctx.data["items"] if c.get("plugin") == item["name"]))) or None


def _never_seen(ctx: _Ctx, item: Item) -> Assessment:
    name = item["name"]
    ie = ctx.ie(name)
    cls = ie.purpose_class
    ev = ctx.ev
    conf = need_confidence(cls, ev.active_days, ev.sessions)
    if conf is None:
        if cls == "rare":
            cue = purpose_cue(item["description"], name)[1] or "occasional"
            text = f"Made for {cue} work; {ev.active_days} active days can't tell yet"
            return _make(ctx, item, "keep_rare", "low", "rare_purpose", text, recheck=_recheck(ctx, cls))
        if ev.sessions == 0:
            text = "No session history yet"
        else:
            seen = f"{_plural(ev.sessions, 'session')} over {_plural(ev.active_days, 'active day')}"
            text = f"Only {seen}; check back after ~{_recheck(ctx, cls)} more"
        return _make(ctx, item, "too_early", "low", "too_early", text, recheck=_recheck(ctx, cls))
    if ie.vague:
        words = specificity(item["description"])[0]
        return _make(
            ctx,
            item,
            "review",
            "low",
            "vague_description",
            f"Its description is {_plural(words, 'word')}, so Claude may never pick it",
            "fix_description",
        )
    for link in ctx.links(name, "overlap"):
        other = link["b"] if link["a"] == name else link["a"]
        if ctx.ie(other).count and _top_half(ctx.ie(other)):
            return _make(
                ctx,
                item,
                "redundant",
                _penalised(ctx, "medium", item, True),
                "overlap_used",
                f"You use {other} for this",
                "remove",
            )
    cost = _cost(ctx, item)
    if cost is None or cost < COST_FLOOR:
        text = "Not used, but costs little; no rush" if cost is not None else "Not used, and its cost is unknown; no rush"
        return _make(ctx, item, "review", "low", "costs_little", text)
    text = f"0 uses in {ev.active_days} active days ({_plural(ev.sessions, 'session')}); costs {cost:,} tokens every session"
    return _make(ctx, {**item, "always_on": cost}, "could_go", _penalised(ctx, conf, item), "never_seen", text, "remove")


def _guard(ctx: _Ctx, item: Item, a: Assessment) -> Assessment:
    """§7c blast radius: an Item something else leans on is never could_go / redundant."""
    refs = ctx.ie(item["name"]).referenced_by
    if refs and a.tier in ("could_go", "redundant"):
        conf: Confidence = "low" if a.confidence == "low" else "medium"
        return _make(ctx, item, "review", conf, "referenced", f"{', '.join(refs)} calls it", extra=a.reasons)
    return a


def _trigger_conflict(ctx: _Ctx, item: Item, a: Assessment) -> Assessment:
    if not any(c["kind"] == "trigger" and item["name"] in c["ids"] for c in ctx.data.get("conflicts", [])):
        return a
    reasons = a.reasons + (Reason("trigger_conflict", "Shares trigger phrases with another Item"),)
    if a.tier == "keep" and ctx.ie(item["name"]).count == 0:
        return replace(a, tier="review", label=LABELS["review"], group="wait", reasons=reasons)
    return replace(a, reasons=reasons)


def _verdict(ctx: _Ctx, item: Item) -> Assessment:
    if item.get("disabled"):
        return _make(ctx, item, "off", None, "off", "Switched off; the scan still counts its cost.")
    if ctx.pinned(item):
        return _make(ctx, item, "keep", "high", "pinned", "You pinned it.")
    found = _redundancy(ctx, item) or _untracked(ctx, item) or _too_new(ctx, item)
    if found is None:
        found = _used(ctx, item) if ctx.ie(item["name"]).count > 0 else _never_seen(ctx, item)
    return _trigger_conflict(ctx, item, _guard(ctx, item, found))


def _plugin(ctx: _Ctx, item: Item, own: Assessment, children: list[Item], pre: dict[str, Assessment]) -> Assessment:
    """§4.3 step 8 and §7g: one verdict for the whole plugin; it can't be split."""
    name = item["name"]
    count = ctx.data.get("plugin_children", {}).get(name) or len(children)
    used = [c["name"] for c in children if ctx.ie(c["name"]).count > 0]
    if used:
        cost = sum(filter(None, (c.get("always_on") for c in children if c["name"] not in used)))
        split = Reason(
            "plugin_cannot_split", clip(f"The other {len(children) - len(used)} cost {cost:,} tokens; the plugin can't be split")
        )
        text = f"You use {len(used)} of its {count} skills ({', '.join(used)})."
        return _make(ctx, item, "keep", "medium", "plugin_partly_used", text, extra=(split,) if cost else ())
    if children and any(pre[c["id"]].tier not in ("could_go", "redundant") for c in children):
        return _make(ctx, item, "review", "low", "children_unclear", "Some of its skills are too new to judge")
    if own.tier != "could_go":
        return own
    conf: Confidence = "low" if any(pre[c["id"]].confidence == "low" for c in children) else "medium"  # never high: can't be split
    text = f"None of its {count} skills used in {ctx.ev.active_days} active days; turning it off saves {own.saves:,}"
    return _make(ctx, {**item, "always_on": own.saves}, "could_go", conf, "children_unused", text, "disable_plugin")


def assess(data: dict[str, Any], ev: Evidence, habits: Habits, pins: frozenset[str], today: date) -> dict[str, Assessment]:
    ctx = _Ctx(ev, habits, today, pins, data, {i["name"]: i for i in data["items"]})
    pre = {item["id"]: _verdict(ctx, item) for item in data["items"]}
    result = dict(pre)
    for item in data["items"]:
        if item["kind"] != "plugin":
            continue
        children = [c for c in data["items"] if c.get("plugin") == item["name"]]
        result[item["id"]] = _plugin(ctx, item, pre[item["id"]], children, pre)
        for child in children:  # a plugin child has no action of its own
            if pre[child["id"]].tier in ("could_go", "redundant"):
                result[child["id"]] = _make(ctx, child, "review", pre[child["id"]].confidence, "part_of_plugin", f"Part of {item['name']}")
    return result


def totals(assessments: dict[str, Assessment]) -> dict[str, int]:
    """The Brief's reclaimable range from the assessments: safe saves, look saves, rows with unknown saves."""
    rows = [a for a in assessments.values() if a.group in ("safe", "look")]
    safe = sum(a.saves for a in rows if a.group == "safe" and a.saves)
    look = sum(a.saves for a in rows if a.group == "look" and a.saves)
    return {"low": safe, "high": safe + look, "unknown": sum(a.saves is None for a in rows), "safe_saves": safe, "look_saves": look}
