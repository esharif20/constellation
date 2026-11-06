"""Habit ledger: per-day usage counts kept across scans, so history outlives Claude Code's transcript deletion.

Privacy: the file holds a local random salt, salted 12-hex Item hashes and 6-hex project hashes, per-day counts, co-use pair
hashes with month counts, and digit dates. It NEVER holds Item ids or names, descriptions, labels, project folder names, paths,
prompt text, tool inputs, timestamps finer than a day or costs. It is private (0600 in a 0700 directory), local only, and never
reaches snapshot(), the public export, a report or a provider. A corrupt or unwritable file is a warning, never a crash.
"""

import fcntl
import json
import math
import os
import re
import secrets
import stat
import statistics
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import date, timedelta
from itertools import combinations, pairwise
from pathlib import Path
from typing import Any

from . import history, usage
from .models import Item, Relation, UsageWindow
from .usage import TRACKED, Fresh, mac
from .verdict_types import Habits, ItemHabits, Trend

DEFAULT_CACHE = Path.home() / ".cache" / "constellation" / "habits.json"
VERSION = 1
HALF_LIFE = 60  # days
CO_PAIRS = 200
NEW_DAYS = 30
RECENT = 30  # active days
BEFORE = 90  # active days before those
PRIOR_N = 2  # pseudo-sessions behind the prior
Z90 = 1.645
MIN_USE_DAYS = 3  # use days needed to estimate a typical gap
OVERDUE_MULT = 3
MIN_NEIGHBOURS = 2  # neighbours with history needed to lend a prior
MIN_SUPPORT = 3  # sessions both Items share before a pair is reported
NEEDS_SHARE = 0.9
MAX_COUNT = 2**53  # beyond this a float loses integers, and a later float() could overflow
MAX_FILE = 16 * 1024 * 1024
ITEM_KEY = re.compile(r"[0-9a-f]{12}")
PROJECT_KEY = re.compile(r"[0-9a-f]{6}")
PAIR_KEY = re.compile(r"[0-9a-f]{12}\|[0-9a-f]{12}")
Ledger = dict[str, Any]


def new() -> Ledger:
    return {"salt": secrets.token_hex(32), "days": {}, "items": {}, "co": {}}  # pragma: no mutate  (None means the same 32 bytes)


def _is_day(value: object) -> bool:
    try:
        return isinstance(value, str) and date.fromisoformat(value).isoformat() == value  # 3.13 also accepts 20261105
    except ValueError:
        return False


def _count(n: object) -> bool:
    return type(n) is int and 0 <= n < MAX_COUNT


def _counts(value: object, key: re.Pattern[str]) -> bool:
    return isinstance(value, dict) and all(isinstance(k, str) and key.fullmatch(k) and _count(n) for k, n in value.items())


def _cell(value: object, count_keys: tuple[str, ...], map_key: str) -> bool:
    if not isinstance(value, dict) or value.keys() != {*count_keys, map_key}:
        return False
    return all(_count(value[k]) for k in count_keys) and _counts(value[map_key], PROJECT_KEY)


def _months(value: object) -> bool:
    return isinstance(value, dict) and all(_is_day(m + "-01") and _count(n) for m, n in value.items())


def _valid(r: object) -> bool:
    if not isinstance(r, dict) or r.keys() != {"salt", "days", "items", "co"}:
        return False
    salt, days, items, co = r["salt"], r["days"], r["items"], r["co"]
    if not isinstance(salt, str) or len(salt) != 64 or any(c not in "0123456789abcdef" for c in salt):
        return False
    if not isinstance(days, dict) or not all(_is_day(d) and _cell(c, ("sessions",), "projects") for d, c in days.items()):
        return False
    if not isinstance(items, dict):
        return False
    for h, rec in items.items():
        if (
            not isinstance(h, str)
            or not ITEM_KEY.fullmatch(h)
            or not isinstance(rec, dict)
            or rec.keys() != {"first_seen", "days"}
            or not _is_day(rec["first_seen"])
        ):
            return False
        if not isinstance(rec["days"], dict) or not all(_is_day(d) and _cell(c, ("n", "s"), "p") for d, c in rec["days"].items()):
            return False
    if not isinstance(co, dict):
        return False
    return all(isinstance(k, str) and PAIR_KEY.fullmatch(k) and _months(v) for k, v in co.items())


def _read(path: Path) -> bytes:
    """The file's bytes: never through a symlink, only a regular file, at most MAX_FILE."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as f:
        if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
            raise OSError("not a regular file")
        data = f.read(MAX_FILE + 1)
    if len(data) > MAX_FILE:
        raise ValueError("too large")
    return data


def load(path: Path) -> tuple[dict[str, Ledger], str | None]:
    """Every valid per-setup record, and a warning when anything unreadable was left out."""
    try:
        raw = json.loads(_read(path))
    except FileNotFoundError:
        return {}, None
    except (OSError, ValueError, RecursionError):
        raw = None  # pragma: no mutate  (any non-dict value takes the same branch below)
    if not isinstance(raw, dict) or raw.get("version") != VERSION or not isinstance(raw.get("setups"), dict):
        return {}, "habit ledger could not be read; starting it over"
    good = {k: v for k, v in raw["setups"].items() if isinstance(k, str) and _valid(v)}
    return good, None if len(good) == len(raw["setups"]) else "part of the habit ledger could not be read; starting that part over"


def _private_dir(directory: Path) -> None:
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)  # pragma: no mutate  (equivalent: the chmod below fixes the mode)
    try:
        if directory.stat().st_uid == os.getuid():
            directory.chmod(0o700)  # an existing directory keeps its mode otherwise
    except OSError:
        pass


@contextmanager
def _locked(path: Path) -> Iterator[None]:
    """One scan at a time reads, merges and writes the ledger, so a second scan cannot overwrite the first one's days."""
    _private_dir(path.parent)
    fd = os.open(path.with_name(path.name + ".lock"), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def save(path: Path, records: dict[str, Ledger]) -> None:
    """Atomic rewrite, 0600 file in a 0700 directory (as history.record)."""
    _private_dir(path.parent)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".habits-")  # mkstemp creates the file 0600
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps({"version": VERSION, "setups": records}, sort_keys=True))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def _max(a: Any, b: Any) -> Any:
    """Field-wise maximum of two count records (ints, or dicts of them)."""
    if isinstance(a, dict):
        return {**a, **b, **{k: _max(a[k], b[k]) for k in a.keys() & b.keys()}}
    return max(a, b)


def merge(ledger: Ledger, fresh: Fresh, window: UsageWindow, ids: list[str], today: str) -> Ledger:
    """Days inside the window are replaced by what the transcripts show now (a re-scan must not add twice); days outside come from
    transcripts Claude Code has since deleted and are kept. The first day may have been cut by deletion: field-wise maximum there."""
    salt = ledger["salt"]
    first, last = window.first or "", window.last or ""  # pragma: no mutate  (no window: any default below every date replaces nothing)
    newest = min(today, window.last or today)  # a wrong clock must not decide what is old: the newest evidence does (as history.record)
    cutoff = (date.fromisoformat(newest) - timedelta(days=history.KEEP_DAYS)).isoformat()

    def stale(day: str) -> bool:
        """Replaced by the fresh read: only when every transcript was read and the day will be written back (not the first day,
        which keeps its old counts to take the maximum with)."""
        return window.skipped == 0 and first < day <= min(last, today)

    def put(days: dict[str, Any], day: str, cell: Any) -> None:
        if day <= today:  # a future date (clock skew) is never evidence
            days[day] = _max(days[day], cell) if day in days else cell

    days = {d: r for d, r in ledger["days"].items() if not stale(d)}
    for day, sessions in fresh.sessions.items():
        put(days, day, {"sessions": sessions, "projects": fresh.projects[day]})
    hashes = {id_: mac(salt, id_, 12) for id_ in {*ids, *fresh.items}}
    items: dict[str, Any] = {}
    for h, r in ledger["items"].items():
        items[h] = {"first_seen": r["first_seen"], "days": {d: c for d, c in r["days"].items() if not stale(d)}}
    for id_ in sorted(hashes):
        record = items.setdefault(hashes[id_], {"first_seen": today, "days": {}})
        for day, (n, s, p) in fresh.items.get(id_, {}).items():
            put(record["days"], day, {"n": n, "s": s, "p": p})
        record["first_seen"] = min([record["first_seen"], *record["days"]])
    current = set(hashes.values())
    days = {d: r for d, r in days.items() if d >= cutoff}
    kept: dict[str, Any] = {}
    for h, record in items.items():
        record["days"] = {d: c for d, c in record["days"].items() if d >= cutoff}
        if h in current or max([record["first_seen"], *record["days"]]) >= cutoff:
            kept[h] = record
    return {"salt": salt, "days": days, "items": kept, "co": _co(ledger["co"], fresh, window, hashes, kept, today, cutoff)}


def _co(
    old: dict[str, Any], fresh: Fresh, window: UsageWindow, hashes: dict[str, str], kept: dict[str, Any], today: str, cutoff: str
) -> Any:
    lo, hi = (window.first or "")[:7], min(window.last or "", today)[:7]  # pragma: no mutate  (a month slice's length is equivalent)
    if window.skipped:
        lo = hi = ""  # an unreadable transcript may hide sessions: nothing is replaced, counts only grow
    pairs: dict[str, dict[str, int]] = {
        k: {m: n for m, n in per.items() if not lo < m <= hi} for k, per in old.items()
    }  # months strictly after the window's first are recomputed; that first month is partial, so it takes the maximum
    counted: dict[str, dict[str, int]] = {}
    for day, session_ids in fresh.co:
        if day > today:
            continue
        for a, b in combinations(sorted(hashes[i] for i in session_ids), 2):
            per = counted.setdefault(f"{a}|{b}", {})
            per[day[:7]] = per.get(day[:7], 0) + 1
    for key, per in counted.items():
        mine = pairs.setdefault(key, {})
        for month, n in per.items():
            mine[month] = max(mine.get(month, 0), n)  # pragma: no mutate  (counts are at least 1: any default of 1 or less is equivalent)
    ranked: list[tuple[int, str, dict[str, int]]] = []
    for key, per in pairs.items():
        months = {m: n for m, n in per.items() if m >= cutoff[:7]}
        if all(h in kept for h in key.split("|")) and sum(months.values()) >= 2:
            ranked.append((-sum(months.values()), key, months))
    return {key: months for _, key, months in sorted(ranked)[:CO_PAIRS]}


def _trend(first_seen: str | None, today: date, uses: tuple[int, int, int, int, int]) -> Trend | None:
    total, recent, before, recent_days, before_days = uses
    if first_seen is not None and (today - date.fromisoformat(first_seen)).days <= NEW_DAYS:
        return "new"
    if not total:
        return None
    if before >= 3 and recent * before_days * 3 < before * recent_days:  # rates per active day, compared without dividing
        return "fading"
    if recent * before_days > 3 * before * recent_days:
        return "rising"
    return "steady"


def _weight(day: str, now: date) -> float:
    return float(0.5 ** ((now - date.fromisoformat(day)).days / HALF_LIFE))


def _beta(used: float, total: float, prior: float) -> tuple[float, float, float]:
    """Beta-Binomial posterior over P(used in a given active session): mean and a 90% interval (normal approximation of the Beta).
    The prior has PRIOR_N pseudo-sessions at mean `prior`, so little history leaves the interval wide."""
    a, b = prior * PRIOR_N + used, (1 - prior) * PRIOR_N + max(total - used, 0.0)
    mean = a / (a + b)
    sd = math.sqrt(a * b / ((a + b) ** 2 * (a + b + 1)))
    return round(mean, 4), round(max(mean - Z90 * sd, 0.0), 4), round(min(mean + Z90 * sd, 1.0), 4)


def _gaps(use_days: set[str], active: list[str]) -> tuple[float | None, int | None]:
    """(typical gap between use days, active days since the last use), both counted in active days so a quiet week is not idleness."""
    positions = [i for i, d in enumerate(active) if d in use_days]
    if not positions:
        return None, None
    typical = statistics.median(b - a for a, b in pairwise(positions)) if len(positions) >= MIN_USE_DAYS else None
    return typical, len(active) - 1 - positions[-1]


def _prior(id_: str, rates: dict[str, float], kinds: dict[str, str], groups: dict[str, str]) -> tuple[float, str | None]:
    """Mean use rate of the neighbours that have history: the same plugin or group first, then the same kind."""
    for label, same in (("group", groups), ("kind", kinds)):
        mates = [r for i, r in rates.items() if i != id_ and id_ in same and i in same and same[i] == same[id_]]
        if len(mates) >= MIN_NEIGHBOURS:
            return sum(mates) / len(mates), label
    return 0.5, None


def profile(ledger: Ledger, today: str, kinds: dict[str, str], groups: dict[str, str] | None = None) -> Habits:
    """What the verdict engine reads (design note 3.3). `kinds` maps every tracked Item id to its kind, `groups` optionally to a
    plugin or cluster key (a cold-start prior comes from the group, else the kind); the result is keyed by id. Pure and cheap."""
    now = date.fromisoformat(today)
    days = {d: r for d, r in ledger["days"].items() if d <= today}  # a future date (clock skew) is never evidence
    active = sorted(days)
    recent, before = set(active[-RECENT:]), set(active[-RECENT - BEFORE : -RECENT])
    sessions = sum(r["sessions"] for r in days.values())
    weighted = sum(r["sessions"] * _weight(d, now) for d, r in days.items())
    month_ago = (now - timedelta(days=30)).isoformat()
    names = {mac(ledger["salt"], id_, 12): id_ for id_ in kinds}
    used: dict[str, dict[str, Any]] = {id_: {} for id_ in kinds}  # id -> day -> cell
    seen: dict[str, str] = {}
    for h, record in ledger["items"].items():
        if h in names:
            used[names[h]] = {d: c for d, c in record["days"].items() if d <= today}
            seen[names[h]] = record["first_seen"]
    decayed = {id_: round(sum(c["s"] * _weight(d, now) for d, c in cells.items()), 6) for id_, cells in used.items()}
    own = {id_: sum(c["s"] for c in cells.values()) for id_, cells in used.items()}
    rates = {i: decayed[i] / weighted for i in kinds if weighted and sum(c["n"] for c in used[i].values())}
    out: dict[str, ItemHabits] = {}
    for id_, kind in kinds.items():
        cells = used[id_]
        per_project: dict[str, int] = {}
        for cell in cells.values():
            for project, n in cell["p"].items():
                per_project[project] = per_project.get(project, 0) + n
        same = [v for i, v in decayed.items() if kinds[i] == kind]
        uses = (
            sum(c["n"] for c in cells.values()),
            sum(c["n"] for d, c in cells.items() if d in recent),
            sum(c["n"] for d, c in cells.items() if d in before),
            len(recent),
            len(before),
        )
        prior, label = _prior(id_, rates, kinds, groups or {}) if not uses[0] else (0.5, None)
        mean, low, high = _beta(decayed[id_], weighted, prior)
        typical, idle = _gaps({d for d, c in cells.items() if c["n"] > 0}, active)
        total = sum(per_project.values())
        out[id_] = ItemHabits(
            decayed_use=decayed[id_],
            all_time=uses[0],
            trend=_trend(seen.get(id_), now, uses),
            percentile=100 * sum(v < decayed[id_] for v in same) // len(same),
            projects_used=sum(n > 0 for n in per_project.values()),
            top_project_share=max(per_project.values()) / total if total else 0.0,
            use_prob=mean,
            prob_low=low,
            prob_high=high,
            prior_prob=round(prior, 4) if label else None,
            prior_from="group" if label == "group" else "kind" if label == "kind" else None,
            typical_gap=typical,
            idle_active_days=idle,
            overdue=typical is not None and idle is not None and idle > OVERDUE_MULT * typical,
            project_shares=tuple(sorted(((p, round(n / total, 4)) for p, n in per_project.items() if n), key=lambda x: (-x[1], x[0]))),
        )
    partners: dict[str, list[tuple[str, float]]] = {}
    needs: dict[str, list[tuple[str, float]]] = {}
    for key, per in ledger["co"].items():
        a, b = (names.get(h) for h in key.split("|"))
        both = sum(per.values())
        if not (a and b):
            continue
        for x, y in ((a, b), (b, a)):  # x needs y when nearly every session of x also used y
            if own[x] and both >= MIN_SUPPORT and both >= NEEDS_SHARE * own[x]:
                needs.setdefault(x, []).append((y, round(both / own[x], 2)))
        if own[a] >= MIN_SUPPORT and own[b] >= MIN_SUPPORT and both * sessions >= 2 * own[a] * own[b]:
            lift = round(both * sessions / (own[a] * own[b]), 2)
            partners.setdefault(a, []).append((b, lift))
            partners.setdefault(b, []).append((a, lift))
    for id_ in {*partners, *needs}:
        out[id_] = replace(
            out[id_],
            co_used=tuple(sorted(partners.get(id_, []), key=lambda x: (-x[1], x[0]))),
            needs=tuple(sorted(needs.get(id_, []), key=lambda x: (-x[1], x[0]))),
        )
    return Habits(len(active), len({p for d, r in days.items() if d >= month_ago for p in r["projects"]}), out)


def update(path: Path, config_dir: Path, items: list[Item], relations: list[Relation], today: str | None = None) -> list[str]:
    """Read the transcripts once more (locally, free), merge them into this setup's record and save. Returns warnings."""
    today = today or history._today()
    setup = history.key(str(config_dir.resolve()))  # unsalted, like the scan history's key
    warnings: list[str] = []
    try:
        with _locked(path):
            records, warning = load(path)
            warnings += [warning] if warning else []
            ledger = records.get(setup) or new()
            fresh, window = usage.read_fresh(config_dir, items, relations, ledger["salt"])
            records[setup] = merge(ledger, fresh, window, [i.id for i in items if i.kind in TRACKED], today)
            save(path, records)
    except OSError as error:
        warnings.append(f"could not save habit ledger: {error.strerror}")
    return warnings
