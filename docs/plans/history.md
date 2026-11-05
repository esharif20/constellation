# Scan history, setup diff, time travel (#62, #66, #70)

Status: plan, 2026-11-04. No app code. All three tickets are local, free and deterministic: no provider call, no network, nothing new leaves the machine. Tests use invented data through `scan()`/`cli.main`/the HTTP API only; never read real scans, `~/.claude`, transcripts or `.env`. Merge order: **#66, then #62, then #70** (#70 needs #62's endpoint; #66 is independent and smallest).

## Shared decisions (put these in every brief)

- **History file:** `~/.cache/constellation/history.json`, module constant `history.DEFAULT_CACHE`; file 0600, directory created 0700; rewritten whole via temp file + `os.replace` (no half file). An unwritable or corrupt file is a stderr warning, never a crash; a corrupt file reads as empty and is replaced on the next write.
- **Format:** `{"v": 1, "entries": [{"setup": "3f9a1c0b2e7d", "date": "2026-11-04", "items": 212, "always_on": 18400, "unknown": 9, "ids": ["a1b2c3d4e5f6", ...]}]}`. `setup` = `key(str(config_dir.resolve()))`; `ids` = sorted `key(item_id)`; `key(t) = sha256(t).hexdigest()[:12]`. `always_on` sums known always-on costs exactly as `report._known_costs` (unknown never 0; disabled Items still count, matching the report today); `unknown` = Items with no known always-on.
- **Retention:** one entry per (setup, UTC date): a re-scan the same day replaces that day's entry. Entries older than 400 days before the newest date are dropped on write.
- **NEVER stored in history:** Item names, descriptions, labels, cluster names, Overlap reasons, paths (the config dir only as its hash), origins, usage counts or dates, warnings, per-Item costs, file bodies. Hashed ids keep names out of a long-lived file; they are not a defence against someone guessing names (the file is private like the scan itself). Say exactly this in a code comment and README.
- **Scan JSON gains two fields** on `Constellation`: `scanned_at: str | None = None` (UTC date `YYYY-MM-DD`) and `setup: str | None = None`, set by the CLI `_write`, not by `scan()`. The Snapshot is an allowlist, so both are dropped already; a test proves it. Snapshots never include history or `/api/history`; the frontend hides history when the endpoint is missing (as it does for the Brief).
- **Known limit:** `local/<n>/<name>` MCP ids shift when the project set changes, so history shows them as removed + added. #66's name fallback handles this for diffs; history accepts it (comment `shortcut: ...`).
- **Ownership:** nobody touches `chat.py`, `answer.py`, `Chat.tsx` (Ask agents). Shared files are edited only at the lines named below; rebase on `origin/main` before merge and keep other agents' changes. `pyproject.toml` `only_mutate` gets `history.py` (#62) and `diff.py` (#66): trivial line conflict, resolve by keeping both.
- **Colour:** tokens from `index.css`/DESIGN.md only, read in SVG via `var(--...)`; no new hex literal anywhere (the only literal stays `PALETTE.overlap` in `paint.ts`). No new dependency (SVG by hand, native range input, lucide icons).
- Each ticket updates `docs/plan-tracker.md` in its commit (status, decisions, no deviation expected) and adds `history.py`/`diff.py` to `only_mutate`.

## #66 Setup diff between two scans (size S, Python only, no Opus review)

**Goal:** `constellation diff OLD.json NEW.json` lists added, removed and changed Items and the always-on cost change, between two dates or two machines.

**API** (`src/constellation/diff.py`, new):
- `diff_scans(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]` returns `{"added": [Row], "removed": [Row], "changed": [Row & {"fields": [str], "always_on": [old|None, new|None], "on_use": [old|None, new|None]}], "always_on": {"old": int, "new": int, "delta": int, "unknown_old": int, "unknown_new": int}, "dates": [old scanned_at|None, new scanned_at|None]}` with `Row = {"id", "kind", "name", "always_on": int|None}`.
- Matching: first by id; then the unmatched on each side by `(kind, name)` when that pair is unique on both sides (other machine, shifted `local/<n>/` scope). Changed `fields` in this fixed order, only those that differ: `always_on`, `on_use`, `description`, `disabled`. Descriptions are compared, never output. Lists sorted by `(kind, name, id)`.
- `render_diff(d: dict[str, Any], *, color: bool, width: int) -> str` (in `diff.py`, reusing `report._paint`/`_fit`). Copy: `Setup diff: 2026-10-01 -> 2026-11-04` (or `unknown date`), `Always-on: 18,400 -> 19,050 tokens (+650); unknown 9 -> 11`, sections `Added (3)` rows `+ skill  pdf-tools  420 tokens`, `Removed (1)` rows `- hook  mend-gasket  unknown`, `Changed (2)` rows `~ skill  release-notes  always-on 300 -> 520, description`. Empty: `No differences.`
- CLI in `cli.py` (new subparser block after `review`, plus `_diff(args)`; touches nothing else): `diff OLD NEW [--json]`, both through `_load_scan` (exit 2 on a bad file), `--json` prints `json.dumps(d, indent=2)`. Reads files only: skips `load_env`.

**TDD slices** (`tests/test_diff.py`, invented dicts):
1. `test_added_and_removed_by_id`: old {a,b}, new {b,c} -> added `[c]`, removed `[a]`, changed `[]`.
2. `test_changed_lists_only_differing_fields_in_order`: cost 300->520 and description edit -> `fields == ["always_on", "description"]`, `always_on == [300, 520]`.
3. `test_description_text_never_in_output`: plant `SECRET-DESC` in old and new descriptions; absent from `render_diff` and `--json` stdout.
4. `test_name_fallback_matches_other_machine`: id `local/1/git` vs `local/2/git`, same kind/name -> one change-free match, not add+remove; a duplicated `(kind, name)` on one side falls back to add+remove.
5. `test_totals_skip_unknown`: costs `{a: 100, b: None}` -> `old == 100`, `unknown_old == 1`; delta sign and `+650`/`-650` formatting.
6. `test_cli_diff_text_and_json` via `cli.main(["diff", old, new])` and `--json`; `test_cli_diff_bad_file_exits_2`.
7. Boundary tests until `mutmut results` is empty.

**Acceptance (5 min):** `uv run constellation diff docs/design/demo.json docs/design/demo-250.json` prints the four sections; `--json` parses; no description text in output; tracker updated; `diff.py` in `only_mutate`.

## #62 Scan history and the context time-lapse (size M; Opus privacy review required)

**Goal:** each real `scan` records one counts-only entry; the app shows always-on cost over time with install markers.

**Python** (`src/constellation/history.py`, new; `DEFAULT_CACHE`, `KEEP_DAYS = 400`):
- `_today() -> str` (UTC `date.isoformat()`, the one clock seam); `key(text: str) -> str`; `entry(data: dict, setup: str, day: str) -> dict`; `load(path: Path) -> list[dict]` (bad file or wrong `v` -> `[]`); `record(path: Path, e: dict) -> None` (replace same setup+date, drop > `KEEP_DAYS`, sort by date, write 0600/0700 atomically).
- `timeline(path: Path, data: dict) -> dict` for the API: entries with `setup == data["setup"]` and `date <= data["scanned_at"]`, returned as `{"entries": [{"date", "items", "always_on", "unknown", "added", "removed", "gone"}], "first_seen": {current Item id: date}}`. `added`/`removed` = id-set difference to the previous entry (0 for the first); `gone` = that entry's ids not in the current scan. `first_seen` = start of the latest unbroken run of entries containing the Item (re-added Items show when re-added); an Item in no entry gets the last date. No `setup`/`scanned_at` in data -> `{"entries": [], "first_seen": {}}`. Never returns hashes or the setup key.
- `cli.py`: `scan --no-history`; `_write(result, path, secrets, config_dir, history)` sets `scanned_at`/`setup` before serialising, then `history.record(...)` unless `--no-history`; `OSError` -> stderr `could not save scan history: <error>`. Dry runs return before `_write`, so they record nothing. `open --history FILE` (default `history.DEFAULT_CACHE` read at call time) passed to `create_app(..., history=path)`.
- `server.py`: `create_app(scan_file, checklist=None, embedder=None, history=None)`; `GET /api/history` with `Depends(local_only)`, reads the scan per request, returns `timeline(...)`; unreadable scan -> 404 like `/api/brief`.
- `models.py`: the two fields. `tests/conftest.py`: add `("history", "history")` to the cache-redirect loop.

**TDD slices** (`tests/test_history.py`; scans of a temp fixture config dir via `cli.main`, clock via `monkeypatch.setattr(history, "_today", lambda: "2026-11-04")`):
1. `test_scan_records_counts_only`: plant `NAME-MARKER` (skill name), `DESC-MARKER`, the tmp path; history bytes contain none of them; entry keys exactly `{"setup","date","items","always_on","unknown","ids"}`; file mode 0600, dir 0700.
2. `test_same_day_rescan_replaces` and `test_two_setups_kept_apart`; `test_entries_older_than_400_days_dropped` (399 kept, 401 dropped).
3. `test_dry_run_and_no_history_record_nothing`; `test_unwritable_history_warns_and_scan_still_written`; `test_corrupt_history_reads_empty`.
4. `test_timeline_added_removed_gone_first_seen` with three hand-written entries incl. a removed-then-re-added id.
5. `test_api_history_localhost_only` (403 for a foreign Host), `test_api_history_has_no_hashes_or_paths` (response bytes lack every id key and the tmp path), `test_api_history_empty_for_old_scan`.
6. In `tests/test_snapshot.py`: `test_snapshot_drops_scan_date_and_setup`.

**UI** (`components/History.tsx`, `graph/history.ts`, `scripts/history-check.ts` + `"history:check"` in `package.json`; `TopBar.tsx` gets one optional `extra?: ReactNode` prop rendered beside the warnings button; `Atlas.tsx` fetches `api/history` once like `api/brief` and passes `<History/>` as `extra`):
- Button: ghost, lucide `History` icon + `History` (ui 13px, text-2); hidden while loading, on fetch failure (Snapshot) and when `entries` is empty.
- Popover (shadcn `popover`, radius-xl, glass, 24 px padding, 360 px; full width minus 32 on phones): title `Always-on cost over time`; caption `Tokens paid every session, one point per scan day. Unknown costs are left out.`
- Chart (dataviz rules): one series, so one hue: line 1.5 px `var(--indigo-bright)`, points r 2.5; x proportional to date (not index), y from 0; gridlines at 0 and max in `var(--line-1)`, axis labels mono 11 px `var(--text-3)` (first/last date via `day()`, `0` and max tokens). Install markers: a 4 px tick under the axis in `var(--text-3)` on each entry with `added > 0`; `−N` removals share the tick. Hover or focus on a point (points are focusable, arrow keys move): one line `4 Nov 2026 · 19,050 tokens · 212 Items · +3 −1`. A `sr-only` table repeats the data. Last entry `unknown > 0`: caption `Plus 11 Items of unknown cost.`
- One entry: `One scan so far. Scan again on another day to see the trend.` Footer button `Time travel` appears with 2+ entries (wired in #70).
- `history-check.ts` asserts `chartPoints()` monotone x by date, y(0) at the baseline, marker count = entries with `added > 0`, on `docs/design/demo-250-history.json`.
- Demo: `make-demo.mjs` writes `demo-250.json` `setup: "demo"`, `scanned_at: "2026-11-04"` and a seeded `demo-250-history.json` (history file format, 12 weekly entries, ids hashed with node `crypto`, a few adds/removals). Deterministic: a rerun leaves `git diff` empty.

**Opus review must check:** history bytes hold only the six keys (grep fixtures for names/descriptions/paths); 0600/0700 and atomic write; `/api/history` is `local_only` and returns no hashes, setup key or path; dry run records nothing; Snapshot drops the new fields; README "Files Constellation reads/writes" lists the history file with retention and `--no-history`.

**Screenshots** (`agent-browser`, `uv run constellation open docs/design/demo-250.json --history docs/design/demo-250-history.json --no-browser --port 8799`, desktop 1440x900 and phone 390x844): button at rest; popover with chart; point hover line; focus ring on a point; one-entry state (a one-entry temp history); no button with `--history /tmp/none.json`. Store under `docs/design/screenshots/62-*.jpg`.

**Acceptance:** six-key entry; same-day replace; endpoint shape; chart matches the copy above; no new colour literal (`git diff | grep -E '#[0-9a-f]{3,6}'` empty outside demo JSON); gates pass.

## #70 Time-travel scrubber (size M, frontend only, no Opus review: reads `/api/history` from #62 only)

**Goal:** scrub across scan days; stars that did not exist yet fade out in place, so you see when each star appeared.

**Layout rule:** positions never change. The map keeps the current scan's settled layout; scrubbing only changes alpha targets. No re-simulation, no camera move, no `cooldownTicks` change.

**Code:** `graph/history.ts` `absentAt(nodes: GNode[], firstSeen: Record<string,string>, date: string): Set<GNode>` (absent when `firstSeen[id] > date`; missing id = present). `paint.ts`: `Focus.absent: Set<GNode> | null` and, in the star alpha target, `now < n.born || focus.absent?.has(n) ? 0 : ...` (links, Overlap arcs and names already follow member alpha). `StarMap.tsx`: prop `absent: Set<GNode> | null` copied to `painter.focus.absent` plus `wake()`; `onNodeClick`/hover ignore absent stars. `components/Scrubber.tsx` (new); `Atlas.tsx`: `scrub` state, opened from History's `Time travel`, hides `Legend` while open; `History.tsx` button wiring.
- Scrubber: `section aria-labelledby="scrub-title"`, glass, radius-lg, fixed bottom-centre (bottom 24, width `min(560px, 100vw - 32px)`; phone bottom 16 full width), 56 px tall. Left: title `Time travel` (sr-only) + mono date `4 Oct 2026`; middle: native range, one step per entry, `aria-valuetext="4 Oct 2026, 198 Items"`; right: `198 of 212 Items · 3 since removed` (text-2, ui) and a close button (`aria-label="Close time travel"`). Starts at the newest entry. Arrows/Home/End step; Esc closes and restores every star. Reduced motion: alphas snap (existing `reducedMotion`). Search and selection keep working; an absent selected star stays selected in the Inspector but dims on the map.
- Removed Items are not drawn (their names are not in history); only the count shows.

**Checks:** `history-check.ts` adds `absentAt` cases (first date: only Items first seen then; last date: empty set; unknown id present). Screenshots `70-*`: scrubber at newest, at oldest (sparse sky), mid with search active, phone, keyboard focus on the range. Acceptance: no star moves while scrubbing (compare two screenshots' positions); Esc restores all; Legend returns; `layout:check`, `chat:check`, `history:check` pass.

## Validation script (run from `~/dev/constellation-wt/plan-history` after all three merge)

```sh
uv sync --all-extras
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pytest -q tests/test_diff.py tests/test_history.py tests/test_snapshot.py && uv run pytest -q
uv run mutmut run && test -z "$(uv run mutmut results)"
uv run constellation diff docs/design/demo.json docs/design/demo-250.json && uv run constellation diff docs/design/demo.json docs/design/demo-250.json --json | python -m json.tool >/dev/null
node docs/design/make-demo.mjs && git diff --exit-code docs/design/
cd frontend && npm run lint && npm run build && npm run layout:check && npm run history:check && npm run chat:check && cd ..
grep -n 'history.py\|diff.py' pyproject.toml
uv run constellation open docs/design/demo-250.json --history docs/design/demo-250-history.json --no-browser --port 8799 &
curl -s -H 'Host: 127.0.0.1:8799' http://127.0.0.1:8799/api/history | python -m json.tool | head -20; kill %1
```
