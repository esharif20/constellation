# Smarter verdict, habit-aware cleanup brief

Status: design note, 2026-11-05. No app code changed. Builds on `inspector.md` §2 (verdict banner), `ask-purpose.md` §3 and §6.3
(the open "Could go" threshold), `plans/usage.md`, `plans/usage-residuals.md`, `plans/per-project.md`, `plans/history.md`,
`plans/lenses.md` and issue #45 (project advisor). Examples use invented Items only (`release-notes`, `changelog-draft`,
`tune-spacing`, `pdf-tools`, `git-helper`, `repo-map`, plus `db-migrate`, `quarterly-report`, `lint-fix`, `scratch-notes`,
`search` (MCP)). Implementers and tests use `docs/design/demo*.json` and hand-built fixtures, never a real `~/.claude`.

## 0. Why the current verdict says "Could go" for everything

Three rules decide today, and they run in three places:

| Where | Rule for a tracked Item never seen, cost > 0 |
|---|---|
| `frontend/src/lib/verdict.ts:25` | `count === 0 && window.files` gives **Could go**, whatever the window length |
| `src/constellation/answer.py:verdict` | **Review** if the window is under `DORMANT_DAYS` (30), else **Could go** |
| `src/constellation/brief.py` | every costed Item is a `review_cost` row "Is it worth it?"; usage is not used at all |

The evidence behind them is thin, and it looks bigger than it is:

1. `UsageWindow.files` counts subagent transcripts as sessions. In the owner's setup (`usage-residuals.md`) there were 8 main
   transcripts and 83 subagent files, so "90 transcripts" was really **8 sessions**.
2. Claude Code deletes transcripts after `cleanupPeriodDays` (default 30). The window can never grow past about 30 days, so a
   30-day threshold equals the window, and every Item not used this month reads as dead.
3. Nothing distinguishes a skill made for a monthly job (release notes) from one that never triggers because its description is
   vague, from one shadowed by a duplicate the owner does use.
4. Inspector and Ask disagree on the same Item (Could go vs Review), and the Brief says neither.

The fix: (a) measure evidence honestly (sessions, active days, history beyond transcript retention), (b) decide with one engine
that knows how much evidence each tier needs, (c) say "not enough history yet" when that is the truth.

## 1. Decisions in this note

| # | Decision | Rejected alternatives |
|---|---|---|
| D1 | One pure Python engine, `src/constellation/verdict.py`: `assess(data, ledger, pins, today) -> dict[id, Assessment]`. Inspector, Ask, Brief and the CLI all read its output. | **Mirrored constants in TS and Python** (the current bug, kept in sync by one parity test). **Engine in TS only** (Ask and Brief run in Python; static Snapshot has no dates to compute from). |
| D2 | A rule table with explicit evidence thresholds and a confidence per verdict, not a weighted score. | **Weighted score or trained model**: cannot produce a plain "why", thresholds hide in weights, mutation tests cannot pin boundaries. **LLM judge**: paid per Item, sends more than metadata. |
| D3 | A local, private **habit ledger** that keeps per-day counts across scans, so history outlives transcript deletion. | **Re-read transcripts only**: capped at ~30 days forever. **Store raw sessions**: more than needed. |
| D4 | "How often could it trigger" is estimated from the description (purpose class) and project activity, never from prompt text. | **Match prompt text against descriptions**: reads conversation text for a new purpose; needs owner approval (§7e, opt-in only). |
| D5 | Brief groups by action safety (safe wins / worth a look / don't touch yet), ranked by tokens saved per unit of risk, with a token range. | Keep ranking by raw cost (today): the top rows are often the Items the owner uses most. |

## 2. Evidence (all local, all free)

Computed once per assess call by `evidence(data, ledger, today)` (pure). Names below are the fields of `Evidence`.

### 2.1 Setup-wide

| Field | Source | Notes |
|---|---|---|
| `sessions` | main transcripts (depth 1) in the window, plus ledger days outside it | Subagent files join their parent session (`<session>/subagents/`): new `UsageWindow.sessions` |
| `active_days` | distinct days with at least one session (window ∪ ledger) | The main exposure unit: idle calendar days are not evidence |
| `span_days` | first to last active day | For display only |
| `sessions_per_day` | median sessions per active day | Turns tokens per session into tokens per day |
| `projects` | stable project hash -> last active day, sessions | From the ledger (§3); a scan's `p1..pN` keys are not stable |
| `skipped_share` | `skipped / (files + skipped)` and malformed lines | Lowers confidence one step when > 5% |

### 2.2 Per Item

| Field | Source | Used for |
|---|---|---|
| `count`, `sessions_used`, `days_used` | `usage` + ledger | How much it is used |
| `last_used`, `idle_active_days` | ledger | Idle counted in **active** days, not calendar days |
| `mean_gap` | active days between uses (when used 3+ times) | Rate-aware staleness: "you used it about every 9 days" |
| `trend` | decayed rate last 30 days vs the 90 before: `rising` / `steady` / `fading` / `new` | Reasons only |
| `percentile` | rank of decayed `sessions_used` among tracked Items of the same kind | "in your bottom 10%" |
| `project_spread` | distinct projects used in, top project share, "used in 3 of 5 projects" | Move-to-project, keep-global |
| `co_used` | top partners by lift (§3.3) | Bundles, winner/loser |
| `purpose_class` | `everyday` / `occasional` / `rare` from the description (§2.3) | How much exposure "never seen" needs |
| `specificity` | words, trigger phrase ("use when"), quoted examples; `vague` = under 8 words (as `triggers.py`) | Vague + never seen = may never trigger |
| `always_on`, `on_use` | `costs` | Saving; on-use cost is never a reason to remove |
| `hook_bytes` | `hook_weights` | Hooks: cost per prompt or per session |
| `origin` | `origins.py`: pack, plugin, claude.ai, or none (hand-written) | Reversibility: a pack or plugin can be reinstalled |
| `plugin` | parent via `contains` | A plugin child cannot be removed alone |
| `referenced_by` | wrapper Overlaps (wrapped-by), `triggers` relations, other enabled Items' descriptions naming it (word match, local) | Blast radius floor (§4.3) |
| `overlaps`, `conflicts` | `overlaps`, `conflicts.py` (shadowed MCP names, shared trigger phrases) | Redundancy |
| `first_seen` | earliest ledger/history day its id hash appears | "Added 5 days ago" |
| `changed_on` | file mtime day, from `stat` only (new scan field, local, dropped by `snapshot()`) | "Changed 3 days ago" |
| `pinned` | pins file (§6.2) | Owner override |

### 2.3 Purpose class (how often it could even trigger)

`purpose_class(description, name)` is pure and deterministic.

- `rare`: whole-word match on a short list: `release`, `changelog`, `quarterly`, `annual`, `yearly`, `tax`, `invoice`,
  `incident`, `postmortem`, `onboarding`, `offboarding`, `migration`, `migrate`, `upgrade`, `audit`, `interview`, `retro`.
- `occasional`: `deploy`, `setup`, `install`, `scaffold`, `new project`, `init`, `benchmark`, `report`, `review`; or
  `specificity` names one narrow file type or tool (a quoted example plus under 20 words).
- `everyday`: otherwise.

The lists are one constant `PURPOSE_CUES` in `verdict.py`; the owner can extend it. An optional model refinement is in §9.

## 3. Learning your habits

### 3.1 What is stored

A new private file `~/.cache/constellation/habits.json` (0600 in a 0700 directory, atomic temp-file replace as `history.py`
does). One record per setup key (`history.key(config_dir)`):

```json
{
  "version": 1,
  "setup": "a1b2c3d4e5f6",
  "salt": "<32 random hex bytes, made once, local only>",
  "days": {
    "2026-10-02": { "sessions": 3, "projects": { "9f3e1c": 2, "07aa42": 1 } }
  },
  "items": {
    "<hmac(salt, item id)[:12]>": {
      "first_seen": "2026-09-14",
      "days": { "2026-10-02": { "n": 2, "s": 1, "p": { "9f3e1c": 2 } } }
    }
  },
  "co": { "<hashA>|<hashB>": { "2026-10": 4 } }
}
```

- `n` = invocations, `s` = sessions that used it, `p` = invocations per project hash.
- Project hash = `hmac(salt, folder name)[:6]`. Salted, so it is not guessable from a path, and stable across scans (unlike the
  `p1..pN` ordinals, which `usage.py` says must never be joined across scans). The display label is still made per scan and
  never stored.
- `co` = sessions in which both Items were used, bucketed by month; only pairs with at least 2 sessions are kept, at most 200
  pairs (largest first). Pair keys sort the two hashes.
- Never stored: names, descriptions, labels, paths, prompt text, tool inputs, timestamps finer than a day, costs.

### 3.2 How it is merged (re-scans must not double count)

Transcripts that still exist are re-read on every scan, so the ledger replaces rather than adds:

1. The scan produces fresh per-day records for every day in `[window.first, window.last]`.
2. `merge(ledger, fresh, window)`: days inside the window are **replaced** by fresh values; days outside are kept as they are
   (they come from transcripts Claude Code has since deleted). `co` months touching the window are recomputed the same way.
3. A partial day at the window edge (`window.first`) is kept as `max(old, fresh)` per field, since deletion may have cut it.
4. Days older than `KEEP_DAYS` (400, as `history.py`) are dropped. An item hash unseen for 400 days is dropped.
5. Unwritable or corrupt file: a warning, the scan continues with transcript-only evidence (the cost-rule pattern).

`usage.py` needs three additions, all inside the existing "only ids, counts and digit dates escape" boundary: a session key per
file (stem at depth 1, parent folder at depth 3), per-day session counts, and per-session Item sets (for `co`). The project
folder name already reaches `_projects`; it is hashed there with the salt passed in.

### 3.3 How it ages (the profile)

`profile(ledger, today) -> Habits` (pure) derives what the engine reads:

- **Decayed use**: `w = 0.5 ** (age_days / 60)` per day (half-life 60 days). "Current habit" = decayed sessions used; all-time
  counts are kept for the "used 41 times since September" line.
- **Trend**: rate per active day in the last 30 active days vs the 90 before; `fading` when below 1/3 of before and before had
  3+ uses; `rising` when above 3x; `new` when `first_seen` is within 30 days.
- **Percentile** among tracked Items of the same kind, by decayed use (ties share the lower rank).
- **Co-use lift**: `P(both) / (P(a) * P(b))` per session; a partner is reported when lift >= 2 and both >= 3 sessions.
  "Always together" = in 90%+ of `a`'s sessions, `b` is also used.
- **Project spread**: "used in 3 of 5 active projects"; "only ever used in one repo" when one project holds >= 80% (the
  existing `MOVE_MIN_SHARE`).

### 3.4 How it feeds confidence

Exposure is `active_days` from the ledger, not the transcript window. With zero uses in `E` active days the honest statement is
the rule of three: the use rate is probably under `3 / E` per active day ("likely under once every E/3 active days"). That
line is the reason text for "never seen" verdicts, and it explains why more history raises confidence. Habits also adjust:

- An Item in the owner's bottom 10% and `fading` gets Review even when it was used this month.
- A never-seen Item whose Overlap partner is in the top half gets "Likely redundant: you use `X` for this".
- An Item co-used with a top-quartile Item ("part of a workflow") is floored at Keep (rarely needed).

## 4. The verdict model

### 4.1 Output: `Assessment`

```python
@dataclass(frozen=True)
class Reason:
    code: str   # stable, e.g. "never_seen", "duplicate_loser", "rare_purpose"; tests and the Snapshot use codes
    text: str   # plain English, max 90 chars, redacted

@dataclass(frozen=True)
class Assessment:
    id: str
    tier: Literal["keep", "keep_rare", "review", "redundant", "could_go", "too_early", "off", "untracked"]
    label: str              # "Keep", "Keep (rarely needed)", "Review", "Likely redundant", "Could go",
                            # "Not enough history yet", "Switched off", "Not tracked"
    confidence: Literal["high", "medium", "low"] | None   # None for off / untracked
    reasons: tuple[Reason, ...]   # 1-3, most important first
    action: Literal["none", "remove", "disable_plugin", "remove_twin", "use_underlying", "move_to_project", "fix_description"]
    saves: int | None       # always-on tokens per session start if the action is taken; None = unknown, never 0
    risk: int               # 1 low, 2 medium, 4 high (§5.1)
    group: Literal["safe", "look", "wait"] | None
    recheck_after: int | None   # active days of extra history that would settle a too_early / keep_rare verdict
```

Tone mapping for the UI: keep, keep_rare -> `keep`; review, too_early -> `warn`; redundant, could_go -> `destructive`;
off -> `off`; untracked -> `none`. The banner shows the label, a confidence chip (`high` / `medium` / `low`), and the first
reason; the other reasons sit under it in text-3.

### 4.2 Thresholds (one table, `verdict.py`)

| Constant | Value | Meaning |
|---|---|---|
| `NEED[everyday]` | medium E >= 10 and S >= 15; high E >= 25 and S >= 40 | Exposure to call a never-seen Item unused |
| `NEED[occasional]` | medium E >= 30; high E >= 60 | |
| `NEED[rare]` | medium E >= 90; never high | Below medium a rare Item is `keep_rare`, not `too_early` |
| `COST_FLOOR` | 50 tokens always-on | Below it, removal is not worth the risk: Review, "costs little" |
| `GRACE_DAYS` | 14 calendar days | Added or changed this recently -> `too_early` |
| `STALE_MIN`, `STALE_MULT` | 30 active days, 3x `mean_gap` | A used Item is stale when idle >= max of the two |
| `BOTTOM_PCT` | 10 | Habit-based Review |
| `HALF_LIFE` | 60 days | Decay |

These replace `DORMANT_DAYS` in both languages.

### 4.3 Decision order (first match wins, then guards, then confidence)

1. `disabled` -> **off** "Switched off; the scan still counts its cost."
2. `pinned` -> **keep**, high, "You pinned it."
3. **Redundancy** (most decisive, needs no usage history):
   - Duplicate pair: the **loser** is the one with less decayed use; tie -> the more expensive (saves more); tie -> id.
     Loser: **redundant**, action `remove_twin`, reasons "Does the same job as `X`", plus "You used `X` 12 times, this one
     never" when history says so. Confidence high if the loser was never used and E meets `NEED.medium`, else medium.
     Winner: **keep**, "Its twin `Y` could go." (Today both get "Keep one"; the brief's `removes()` picks the cheaper one,
     which saves less. Owner decision O3.)
   - Wrapper `a` of `b`: `a` **redundant**, `use_underlying`, unless `a` is used and `b` never directly (then **keep**,
     "You reach `b` through it"). `b` **keep**, "`a` calls it."
   - Shadowed MCP name (`conflicts.py` kind `mcp_name`, lower scope): **redundant**, high, "Never loaded: a server with the
     same name in `local` scope wins."
4. **Too new**: `first_seen` or `changed_on` within `GRACE_DAYS` -> **too_early**, "Added 5 days ago."
5. **Used** (count > 0):
   - Stale (`idle_active_days >= max(STALE_MIN, STALE_MULT * mean_gap)`) and E >= 30 -> **review**, medium, "Used 6 times,
     none in 74 active days (you used it about every 9)."
   - One-repo (MOVE rule, >= 3 uses, >= 80% in one project) and global -> **review**, `move_to_project`, "Used 9 times, all in
     one repo; moving it there saves 520 tokens in every other session."
   - Bottom 10% and `fading` -> **review**, low.
   - Otherwise **keep**: "Used 41 times in 5 of 5 projects; in your top 10%." Confidence high when S >= 15.
6. **Never seen** (tracked, count 0): let `need = NEED[purpose_class]`.
   - E below `need.medium`: rare -> **keep_rare**, low, "Made for occasional work (release); 34 active days can't tell yet.";
     otherwise **too_early**, "Only 8 sessions over 6 active days; check back after ~4 more." `recheck_after = need.medium - E`.
   - `vague` -> **review**, `fix_description`, "Its description is 3 words, so Claude may never pick it; sharpen or remove."
   - Overlap partner used (top half) -> **redundant**, medium, "You use `X` for this."
   - Plugin child -> no own action; reasons feed the plugin roll-up (step 8). Tier **review**, "Part of `pdf-tools`."
   - `always_on` unknown or below `COST_FLOOR` -> **review**, low, "Not used, but costs little; no rush."
   - Else **could_go**, `remove`, confidence from `need` (high / medium), reasons "0 uses in 34 active days (52 sessions):
     likely under once every 11 days", "Costs 610 tokens every session".
7. **Untracked kinds** (hooks, plugins without tracked children, commands): **untracked**, reasons from cost and lenses
   ("Adds 1.2 KB before every prompt"; "Can block tool calls"). Never could_go from usage.
8. **Plugin roll-up**: could_go only if every tracked child is could_go or redundant; confidence = lowest child; saves = sum
   of children always-on; action `disable_plugin`. Any child kept -> **keep**, "You use 1 of its 3 skills (`x`)."; then
   "the other two cost 1,300 tokens; the plugin can't be split" as a second reason.

Guards, applied after the match:

- **Blast radius**: `referenced_by` non-empty, or co-used "always together" with a kept Item -> tier capped at **review**
  (never could_go / redundant), reason "`deploy-flow` calls it" / "Always used together with `git-helper`".
- **Trigger-phrase conflict** (`conflicts.py` kind `trigger`): adds a reason; caps keep at review only when the Item is also
  never seen.
- **Confidence penalties**, one step each: `skipped_share > 5%`; hand-written (no origin) and no twin (removal is not
  reversible); S < 15.

Every verdict has 1 to 3 reasons; a test asserts this for every fixture Item.

### 4.4 Where it runs, and how the three surfaces stop disagreeing

- `assess()` lives in `src/constellation/verdict.py`, pure; `habits.py` holds `merge()` and `profile()`.
- Server: new `GET /api/assess` (localhost-only, like `/api/lenses`) returns `{ "items": {id: Assessment}, "evidence":
  {sessions, active_days, span_days, ledger: bool} }`. `/api/brief` and `/api/chat` call the same function in-process.
- Frontend: `lib/verdict.ts` becomes a reader: `verdictOf(item, assessments)` maps tier to tone and label; no thresholds, no
  dates. Missing entry (old server, demo JSON without assessments) -> "Not enough data".
- Ask: `answer.verdict()` becomes a call to `assess()` that returns the old `{label, tone, why}` shape (why = first reason),
  so `card()` and `handoff()` keep working. `handoff()` reads `action` instead of `tone`.
- Static Snapshot (#13): carries `tier`, `confidence`, and reasons regenerated from `code` with numbers rounded to weeks and
  no dates (no `last_used` day leaves in public export).
- CLI: `constellation assess [--json]` prints the same table; `make-demo.mjs` runs it to add `assessments` to demo JSON.

## 5. The cleanup Brief

### 5.1 Ranking

`risk = CONF[confidence] * REV`, with `CONF = {high: 1, medium: 2, low: 4}` and `REV = 1` when the Item came from a pack,
plugin or claude.ai or has a twin that stays, else 2 (hand-written, gone for good). Rank key: `(-saves / risk, -saves, name,
id)`; unknown saves sort last within a group and never count as 0.

### 5.2 Groups

| Group | Contains | Shown as |
|---|---|---|
| **Safe wins** | redundant or could_go, high confidence, saves known >= `COST_FLOOR`, no guard hit | Rows with a check, "Copy instruction for all safe wins" (joined per-Item `handoff` text, each line its own `Show me... wait for my OK`), "Add all to checklist" |
| **Worth a look** | redundant / could_go at medium; review with an action (`move_to_project`, `fix_description`, `use_underlying`, `disable_plugin`); stale used Items | Rows with the first reason; per-row copy and checklist as today |
| **Don't touch yet** | too_early, keep_rare, low confidence, untracked heavy hooks | One summary line per reason ("6 skills: not enough history; check back after ~12 more active days"), expandable; no copy buttons |

Keep tiers are not listed. Moves (`move_to_project`) stay in "worth a look" with the existing scope caveat.

### 5.3 Totals

- **Session-start tokens reclaimable**: `low = sum(safe saves)`, `high = low + sum(look saves)`; every removed Item counted
  once (duplicate loser only, plugin children once through the plugin). Shown as "Reclaim **990 to 3,700** tokens per session
  start (estimate)", plus "about 3,000 to 11,000 a day at your pace" using `sessions_per_day`, plus "+3 with unknown cost".
- **What you pay for what you use** (§7f): "You pay 6,200 tokens per session for skills; 31% of that is for skills you used
  in the last 30 active days."
- **History honesty line**: "Based on 52 sessions over 34 active days (habit ledger since 14 Sep)." When transcripts are the
  only source and the window is under 30 days, add: "Claude Code keeps transcripts for 30 days by default (`cleanupPeriodDays`);
  Constellation keeps counts across scans, so verdicts sharpen as you rescan." (Owner decision O6 on also suggesting a higher
  `cleanupPeriodDays`.)

### 5.4 Brief response shape (replaces `cost` / `pairs`)

```json
{ "evidence": {...}, "safe": {"rows": [...], "saves": 990},
  "look": {"rows": [...], "saves": 2710, "unknown": 1},
  "wait": {"summary": [{"code": "too_early", "count": 6, "recheck_after": 12}], "rows": [...]},
  "range": {"low": 990, "high": 3700, "per_day": [3000, 11000], "unknown": 3},
  "scope": {...}, "checklist": {...} }
```

Each row is a Suggestion (`_make(kind, ids, reason, saves)` with kinds `remove_unused`, `remove_duplicate`, `use_underlying`,
`move_to_project`, plus new `disable_plugin`, `fix_description`) with `tier`, `confidence`, `reasons`, `removes`. Ids stay
content-derived, so existing checklist lines still match when the kind is unchanged. `checklist_state` and `POST
/api/checklist` look rows up in `safe` and `look` instead of `cost` and `pairs`. `review_cost` rows disappear (a cost alone is
not a reason); a costly Item that is used and kept appears in the "What you pay" line instead.

## 6. Free by default, privacy

### 6.1 Cost rule

Everything in §2 to §5 and §7 (except items marked opt-in) is local arithmetic over the saved scan, the ledger and file stats.
No new provider call. A rescan of an unchanged setup makes zero paid calls (the ledger merge is local). Offline mode still gets
the full verdict: usage, Overlaps-from-cache and costs-from-cache are what it already had; without costs, could_go becomes
review "cost unknown".

### 6.2 New local files and endpoints (each needs owner approval, see §11)

| What | Where | Holds | Why private is enough |
|---|---|---|---|
| Habit ledger | `~/.cache/constellation/habits.json`, 0600 | §3.1 | Salted hashes, counts, days; same class as `history.json` |
| Pins | `~/.cache/constellation/pins.json`, 0600 | Item ids the owner pinned, with the day | Ids only; written by new `POST /api/pin` (localhost-only, id-only input, like `/api/checklist`) |
| `changed_on` | the scan JSON | file mtime day per file-backed Item | `stat` only, no read; dropped by `snapshot()` |

### 6.3 Privacy invariant

Unchanged. Nothing new leaves the machine. Transcripts are still read only for tool names, command names, record days and now
session keys; prompt text is not read for any purpose in the default build. Descriptions are matched locally (purpose cues,
references); they leave only through the existing redacted label path.

## 7. Only the graph can say this

Claude Code inside a session sees its own context: no other sessions, no other projects, no measured token cost, no pairwise
comparison of the whole setup. These insights need the whole graph plus history. Ranked by usefulness, then effort.

| Rank | Insight | Data needed | Privacy check | Effort | Slice |
|---|---|---|---|---|---|
| 1 | **(b) Winner and loser among twins**: for each duplicate, wrapper or shadowed name, which one actually got used; the unused twin is the removal candidate, with "you used `X` 12 times, this one never". | Overlaps, `conflicts`, ledger counts | Local counts only | S | S2 |
| 2 | **(f) Whole-setup budget**: session-start cost of every Item at once; share of it spent on Items used in the last 30 active days; "you pay N tokens/session for skills you use M% of the time"; tokens per used invocation. | `receipt()`, costs, ledger | Local | S | S3 |
| 3 | **(a) Cross-session use and trends**: counts, sessions, active days, percentile, rising/fading, since the ledger began, beyond transcript deletion. | Ledger (§3) | Salted hashes, counts, days; 0600 | M | S1 |
| 4 | **(g) Plugin and placement decisions**: disable a whole plugin when none of its parts is used; "you use 1 of its 3 skills"; global vs project placement ("used only in one repo: move it", "used in 4 of 5 projects: keep global"). | `contains`, ledger per project | Project hashes local; labels per scan only | S | S2 |
| 5 | **(c) Blast radius**: what loses coverage if `X` goes: wrapped-by, `triggers` relations (hooks calling an MCP tool), other Items' descriptions naming it, its cluster's remaining members ("the only skill in cluster *PDF work*"). Shown in the Inspector as "If removed" and used as a guard. | Relations, Overlaps, clusters, descriptions | Local word match | M | S2 (guard), S5 (UI) |
| 6 | **(d) Co-use and sequences**: bundles ("`changelog-draft` is used in 90% of `release-notes` sessions"); "never used without `X`" (remove only together); sequence order within a session is **not** kept (day granularity), so "A then B" is out of scope for v1. | Ledger `co` pairs | Pair hashes and month counts only | M | S1 (store), S2 (use) |
| 7 | **(e) Trigger misses**: skills that look relevant to the owner's work but never fire. v1, metadata only: embed descriptions locally (fastembed, ADR 0003) and compare each never-seen skill to the **used** skills' descriptions; close to a frequently used skill but never fired = "likely trigger miss: sharpen its description" (or a duplicate). No prompt text. v2 (needs explicit owner approval): embed the owner's prompts locally to measure how often a task like this came up. Prompt text would still never leave the machine, but it is a new kind of reading, so it is off until approved. | Local embeddings of descriptions; v2 local prompt embeddings | v1 local, descriptions only; v2 flagged | M (v1), L (v2) | S6 |

Project-aware advice (#45) sits on top of (g) and (e), see §8.

## 8. Project-aware recommendations (#45 follow-on)

Given `--project PATH` (current project), Constellation reads locally, never sends: the project's `CLAUDE.md`, `AGENTS.md`,
`architecture.md` / `README` (first 4 KB each), and manifest dependency names (`package.json`, `pyproject.toml`,
`Cargo.toml`, `go.mod`). Reading project files is new for the scanner (a deviation to approve, O7); bodies stay local.

1. Make a project profile locally: the manifest names plus the embedded text chunks (fastembed).
2. For each global Item: `relevance` = max cosine between its description embedding and the project chunks; `used_here` from
   the ledger's project hash.
3. Quadrants, shown as a "This repo" tab in the Brief:
   - relevant and used here: keep (maybe move into the repo if used nowhere else);
   - relevant, not used here: "might help here" (possible trigger miss);
   - not relevant, not used here, used elsewhere: noise for this repo, a candidate to move out of global;
   - not relevant anywhere, never used: already covered by the global verdict.
4. **Local skills to add**: only from what is already on the machine and known to the scan: Items scoped to other projects,
   Items inside disabled plugins, and the install preview catalogue (#12). Ranked by relevance; never fetched.
5. Draft a tiny CLAUDE.md section ("for this repo use skill X for Y"), with its own token cost shown, written to a chosen path
   or the checklist; the app never edits the repo.

Optional model use (opt-in, §9): summarising the project text needs that text sent, which the privacy invariant forbids
today; it is listed for completeness and needs the owner's explicit approval before any design.

## 9. Optional model use (opt-in only, listed separately)

None of these is needed for any verdict; each is off by default, behind a flag, printed in the call-count estimate, and cached
by the content hash of the redacted text in a 0600 file (the cost rule).

| Flag | Sends | Gets | Privacy |
|---|---|---|---|
| `--purpose-model` | redacted description (already allowed) | `everyday` / `occasional` / `rare` class, replacing the cue list for that Item | Within the invariant |
| `--project-summary` | redacted project text | a stack and domain summary for §8 | **Outside** the invariant: needs owner approval first |

## 10. Worked example (invented setup)

Evidence: ledger since 14 Sep, 52 sessions over 34 active days, 5 projects, `skipped_share` 0, 1.6 sessions per active day.

| Item | Facts | Tier, confidence | Reasons (first two) | Group, saves |
|---|---|---|---|---|
| `git-helper` (agent, 300) | 41 uses, 5 of 5 projects, top 10%, steady | Keep, high | Used 41 times in 5 of 5 projects; in your top 10% | none |
| `release-notes` (skill, 420) | 3 uses, last 20 active days ago, rare class | Keep, medium | Used 3 times; made for release work | none |
| `changelog-draft` (skill, 380) | duplicate of `release-notes`, 0 uses, pack origin | Likely redundant, high | Does the same job as `release-notes`; you used that 3 times, this one never | Safe, 380 |
| `tune-spacing` (skill, 610) | 0 uses, everyday class, specific description, pack origin | Could go, high | 0 uses in 34 active days (52 sessions); costs 610 tokens every session | Safe, 610 |
| `pdf-tools` (plugin, 3 skills, 1,900) | no child used; one child occasional (medium) | Could go, medium | None of its 3 skills used in 34 active days; turning it off saves 1,900 | Look, 1,900 |
| `repo-map` (skill, 520) | 9 uses, all in one project | Review, medium | Used 9 times, all in one repo; move it there to save 520 elsewhere | Look, 520 |
| `lint-fix` (skill, 200) | 6 uses, idle 74 active days, mean gap 8, fading | Review, medium | Not used in 74 active days; you used it about every 8 before | Look, 200 |
| `scratch-notes` (skill, 90) | 0 uses, description "notes helper" | Review, low | Its description is 2 words, so Claude may never pick it | Look, 90 |
| `search` (MCP, cost unknown) | same name in user and local scope, user copy | Likely redundant, high | Never loaded: the `local` server with this name wins | Look, unknown |
| `db-migrate` (skill, 450) | added 6 days ago | Not enough history yet | Added 6 days ago | Wait |
| `quarterly-report` (skill, 700) | 0 uses, rare class, E 34 < 90 | Keep (rarely needed), low | Made for quarterly work; 34 active days can't tell yet | Wait, recheck after 56 |
| `UserPromptSubmit:*` hook | 1.2 KB per prompt | Not tracked | Adds 1.2 KB before every prompt | Wait |

Brief: "Reclaim **990 to 3,700** tokens per session start (estimate) +1 with unknown cost." The same owner with today's 8
sessions over 6 active days would see `tune-spacing` as "Not enough history yet: only 8 sessions over 6 active days; check
back after ~4 more", not "Could go"; `changelog-draft` would still be Likely redundant (medium: twin evidence needs no long
history).

## 11. Edge cases

| Case | Behaviour |
|---|---|
| No transcripts, no ledger | Every tracked Item `too_early` with "No session history yet"; redundancy verdicts still work |
| Ledger corrupt or unwritable | Warning; transcript-only evidence; history line says so |
| Item renamed (new id) | New hash, `first_seen` today, `too_early` for 14 days; the old hash ages out. Accepted. |
| Same name in a plugin and locally | `usage._index` already credits the local one; plugin copy gets twin logic via Overlap if found |
| Ambiguous invocation credited to several Items | Each credited (existing); confidence for each drops one step |
| Both twins never used | Loser by cost (more expensive goes), confidence medium, reasons say neither was used |
| Both twins used a lot | Both keep; a review reason "`X` does the same job and you use both" |
| Project-scoped Item, project not active in the window | `keep_rare` "Its project hasn't been opened since 2 Sep"; never could_go |
| Plugin with untracked parts only (commands, hooks) | untracked; cost shown; no verdict from usage |
| Disabled Item | off; excluded from totals (its cost is not paid) |
| Clock skew, future dates in transcripts | Days after `today` ignored for exposure |
| Huge counts (greedy, `triggers.py`) | keep with reason "Fires in 80% of sessions; check it isn't triggering by mistake" |
| Pinned and duplicate | Pinned wins; the twin becomes the loser if it is not pinned too; both pinned: both keep |
| Static Snapshot | Tier and confidence only, reasons from codes, no dates, no project data |

## 12. Test plan

All pure functions, table-driven, invented fixtures; no real `~/.claude`, `~/constellation-real.json` or `.env`.

- `habits.merge`: replace inside window, keep outside, `max` on the edge day, prune at 400 days, rescan of the same transcripts
  is idempotent (merge twice == merge once), file mode 0600, corrupt file warns.
- `habits.profile`: decay at 0, 60, 120 days; trend boundaries (exactly 1/3, exactly 3x); percentile ties; lift >= 2 boundary;
  "always together" at 89% vs 90%.
- `usage` additions: subagent file joins the parent session; per-day session counts; per-session sets; the existing "only ids,
  counts and digit dates escape" test extended to the new outputs; project hash is salted (two salts, two hashes).
- `verdict.purpose_class`, `specificity`, `referenced_by`: word-boundary cases (`released` vs `release`), quoted phrases.
- `verdict.assess`: one fixture row per §10 line and per §11 line, asserting tier, confidence, reason codes and group. For
  every threshold in §4.2 a pair of tests at `n - 1` and `n` (kills off-by-one and comparison mutants). Invariants checked over
  all fixtures: 1 to 3 reasons, each <= 90 chars; `saves is None` never rendered as 0; more active days never makes a
  never-seen Item *less* removable (monotonicity, small hand-built sweep, not a property library).
- `brief`: grouping, rank key with unknown saves last, range dedupe (duplicate counted once, plugin children once), ids
  unchanged for unchanged kinds.
- **Agreement test** (replaces the parity test): for each fixture Item, `/api/assess` tier label == Ask card verdict label ==
  Brief row tier; the TS reader maps every tier (`inspector-check.mjs`).
- Mutation gate: add `verdict.py`, `habits.py` and the new `brief.py` code to mutmut `only_mutate`; constants are named and
  each boundary has its pair test, so zero survivors is reachable without exclusions.

### Migrating existing tests

- `tests/test_chat_ask.py:54` (DORMANT_DAYS parity with `verdict.ts`): delete; replace with the agreement test and a check that
  `verdict.ts` defines no numeric day threshold.
- `tests/test_chat_ask.py:147, :756`, `tests/test_chat_answers.py:141`, `tests/test_chat_compare.py:257` expect "Could go" on
  short invented windows: give those fixtures a ledger meeting `NEED.high` (keeps "Could go"), and add a sibling test asserting
  the short-window case now says "Not enough history yet".
- `frontend/scripts/inspector-check.mjs`: drop `DORMANT_DAYS`; feed assessments in; assert tier-to-tone/label/icon mapping
  and the "Not enough data" fallback; `instructionFor` keys on `action`.
- `tests/test_suggestions.py`, brief tests in `tests/test_server.py`: new group keys; `review_cost` expectations removed.
- Golden scan fixtures (`tests/fixtures/golden/*.json`) gain `usage_window.sessions` and `changed_on`; regenerate once.

## 13. Ticket breakdown

A contract commit comes first (orchestrator, about 40 lines, no logic): `Reason`, `Assessment`, `Evidence`, `Habits` types,
`UsageWindow.sessions`, `Item.changed_on`, the Brief response shape, and one fixture file `tests/fixtures/assess/setup.json`
(the §10 setup). Then these slices run in parallel, each owning its files:

| Slice | Owns | Delivers | Depends on |
|---|---|---|---|
| **S1 Habit ledger** | `usage.py` (sessions, sets, salted project hash), new `habits.py` (`merge`, `profile`, file IO), CLI write after scan, `claude_code.py` mtime `stat` | §3, §7a, §7d storage | contract |
| **S2 Verdict engine** | new `verdict.py` (`evidence`, `purpose_class`, `specificity`, `referenced_by`, `assess`), its tests | §2, §4, §7b, §7c guard, §7g | contract (reads `Habits` from the fixture, not from S1 code) |
| **S3 Brief** | `brief.py`, `suggestions.py` kinds, `server.py` checklist lookups | §5, §7f | contract (stubs `assess` with fixture output) |
| **S4 Integration** | `server.py` `/api/assess` and `POST /api/pin`, `answer.py` delegation, `snapshot.py` coarsening, `cli.py assess`, `make-demo.mjs`, test migration (§12) | §4.4, §6.2 | S2 merged; S3 for brief endpoint |
| **S5 Frontend** | `lib/verdict.ts`, `inspector/Verdict.tsx` (confidence chip, reasons, "If removed"), `Brief.tsx` (three groups, range, copy-all), `inspector-check.mjs` | §4.1 tones, §5.2 UI | contract (works on demo JSON with assessments) |
| **S6 Later: graph extras** | trigger misses v1 (§7e, local embeddings), project tab (§8) | §7e, §8 | S2, #45 decisions |

S1 to S3 and S5 are independent after the contract; S4 is the one integration owner for shared files (`server.py`, `cli.py`,
`answer.py`), per the tracker's coordination rule. Opus reviews S1 and S4 (privacy-sensitive: transcript reader, new files,
endpoints). UI slices follow the CLAUDE.md UI skill set and screenshot checks.

## 14. Owner decisions needed

1. **O1** Approve the habit ledger (`habits.json`: salted hashed ids and project folders, per-day counts, co-use pairs, 400-day
   retention). This changes the plan's "usage is not kept across scans" stance: a recorded deviation.
2. **O2** Thresholds in §4.2 (exposure table, `COST_FLOOR` 50, `GRACE_DAYS` 14, stale 30 / 3x, half-life 60). This also closes
   `ask-purpose.md` §6.3.
3. **O3** Duplicate loser rule: less-used goes (tie: more expensive), replacing "remove the cheaper one".
4. **O4** Pins: new `pins.json` and `POST /api/pin` (a second write endpoint after `/api/checklist`).
5. **O5** `stat` of Item files for `changed_on`.
6. **O6** Whether the Brief should suggest raising `cleanupPeriodDays` (advice only; the app never edits settings).
7. **O7** Project advisor reads a project's CLAUDE.md / README / architecture / manifests locally (#45).
8. **O8** Trigger misses v2: local embedding of prompt text (stays on the machine, but a new kind of transcript reading).
9. **O9** Public Snapshot: include tiers at all, or drop verdicts from public export.
