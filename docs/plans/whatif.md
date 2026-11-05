# Plan: budget meter (#42), what-if (#69), cluster health (#71), explain card (#68)

Status: plan only, 2026-11-04. Read first: `AGENTS.md`, `GLOSSARY.md`, `docs/plan-tracker.md`, `docs/design/DESIGN.md`, `docs/design/cluster-focus.md`, `docs/plans/explore-ux.md` E1/E2 and T12, `docs/design/ask-purpose.md` §3.2 and §3.4. #42 is not built (no branch, Brief has no meter), so it is ticket 0 here.

## Shared rules (every ticket)
- Stack: React 19 + TS + Tailwind v4 + shadcn tokens, react-force-graph-2d canvas (`paint.ts`), FastAPI + Python 3.13 via `uv`. No new dependency. Colours only from `index.css` tokens and `PALETTE` in `paint.ts`; read new canvas colours in `readInk()` (`--warn`, `--text-3`).
- Before UI code, load `/prototype` (only if the ghost look is unclear), `frontend-design:frontend-design`, `ui-ux-pro-max`, `dataviz`, `vercel-plugin:react-best-practices`, and `vercel-plugin:agent-browser` for screenshots. No `scroll-craft`.
- Nothing new leaves the machine: no provider call, no new file read, no new fetch except `GET api/explain` (#68). The app still never edits the setup; what-if is a preview only.
- Unknown cost is never 0: it is counted and said ("unknown"), never summed.
- TS logic is tested by assert blocks appended to `frontend/scripts/layout-metrics.ts` (run by `npm run layout:check`), on invented nodes plus one demo-250 total. Python through the HTTP API (`TestClient(create_app(scan_file))`) with invented data in `tmp_path`.
- Never read real scans, `~/.claude`, transcripts or `.env`. Screenshots use `docs/design/demo-250.json` only, kept out of the repo.
- Each ticket updates `docs/plan-tracker.md` in its commit. Gates: see Validation.

## File ownership and merge order
| Ticket | May edit | Must not edit |
|---|---|---|
| 0 #42 | `Brief.tsx`, `graph/model.ts` (append `budget`), `layout-metrics.ts` (append) | everything else |
| #69 | `Atlas.tsx`, `StarMap.tsx`, `graph/paint.ts` (`Focus`, `node()`, link/arc alpha, item names), `Brief.tsx`, `Inspector.tsx`, new `WhatIfChip.tsx`, `model.ts` (append `withContents`), `layout-metrics.ts` | `ClusterCard.tsx`, `TopBar.tsx` |
| #71 | `model.ts` (append `clusterHealth`), `paint.ts` (`readInk`, a badge pass after the cluster-name loop), `ClusterCard.tsx`, `layout-metrics.ts` | `Atlas.tsx`, `Brief.tsx` |
| #68a | new `src/constellation/explain.py`, `server.py` (one route), new `tests/test_explain.py`, `pyproject.toml` (`only_mutate`) | all of `frontend/` |
| #68b | new `ExplainCard.tsx`, `TopBar.tsx` (one prop + button), `Atlas.tsx` (mount, about 4 lines) | `Brief.tsx`, `paint.ts` |

Nobody touches `chat.py`, `answer.py`, `Chat.tsx` (Ask tickets #53-#58). Order: **#42 -> #69 -> #71 -> #68b** in one frontend chain (each branches from main after the previous merge). **#68a** is Python only and runs in parallel from the start. `Atlas.tsx`/`StarMap.tsx` are shared with Ask: keep each diff in its own hunks (new state next to `chatMatches`, new props appended at the end of each JSX prop list, never reformat lines), rebase on main right before merge, and on conflict keep both sides.

## Ticket 0 (#42): session-start budget meter in the Brief (size S, after #38/T9, which is merged)
Goal: the Brief opens with one number: what the setup costs before the first prompt, what it is made of, and what removing the top 5 saves.
- `model.ts`: `export type Budget = { measured: boolean; known: number; items: number; hooks: number; unknown: number; saved: number; removed: number; removedUnknown: number }` and `export function budget(nodes: GNode[], removed: ReadonlySet<GNode> = new Set()): Budget`. Per node: `cost.always_on` if not null (goes to `items`); else a hook with `weight.tokens != null` (goes to `hooks`); else unknown. Removed nodes go to `saved`/`removedUnknown` instead. `known = items + hooks`; `measured` = any node contributed.
- TDD (asserts in `layout-metrics.ts`, write first): (1) `budget([a100,b0,cNull])` gives known 100, unknown 1, a zero cost counts as known; (2) hook with `weight.tokens 40` and null cost adds to `hooks`; null tokens counts unknown; (3) a node with both uses `always_on` only; (4) removing a100 gives known 0, saved 100, and removing cNull gives removedUnknown 1; (5) all-null gives `measured false`; (6) demo-250: `known 20082`, `items 10448`, `hooks 9634`, `unknown 55`.
- UI (`Brief.tsx`, new `Meter` function in the same file, top of the body, above "Most expensive"):
  - Row: label "Session start" (`text-xs text-text-3`), right: `20,082` in `font-mono text-2xl tabular-nums`, then `tokens before your first prompt` (`text-xs text-text-3`).
  - Bar (`h-2 rounded-full bg-line-1`, `role="img"`, `aria-label="Items 10,448 tokens, hooks 9,634 tokens"`): Items segment `bg-indigo-bright/70`, hooks segment `bg-indigo-bright/35` separated by a 2 px gap; legend line under it: `Items 10,448 · Hooks 9,634` with matching swatches (shape not only colour: hooks swatch is hatched via `bg-[repeating-linear-gradient(...)]` from the same token).
  - Then `55 with unknown cost, not counted` and `Removing the top 5 saves ~853 (estimate)` (from `data.cost.frees`; omit when null).
  - States: not measured -> `Cost was not measured in this scan.` (italic text-3, no bar); empty scan -> existing empty text; offline demo -> hooks segment absent when 0.
  - Phone 390: same block inside the 46dvh sheet, number `text-xl`; legend wraps under the bar. Reduced motion: no animation (static). Keyboard: nothing focusable added.
- Screenshots (demo-250, 1440x900 and 390x844): Brief open shows `20,082`, both segments, `55 with unknown cost`, `~853`; `demo-offline.json` shows the not-measured line.
- Accept: asserts pass; numbers match; bar has an aria-label; no new fetch; tracker updated. Privacy: none (display of data already loaded). No Opus review.

## #69: what-if mode (size M, after #42)
Goal: tick Items to "remove" and watch the meter, the map and cluster totals change live. Nothing is written; ticks live only in page memory.
- `model.ts`: `export function withContents(model: Model, picked: ReadonlySet<GNode>): Set<GNode>`: picked plus everything reachable by `contains` links from them (a plugin takes its skills, hooks and servers). Assert (first): plugin P contains s1, s2 gives {P,s1,s2}; picking s1 gives {s1}; a cycle terminates.
- `Atlas.tsx`: `const [whatIf, setWhatIf] = useState<Set<GNode> | null>(null)` (null = off), `const removed = useMemo(() => whatIf && withContents(model, whatIf), [model, whatIf])`, `toggleRemove(n)` (new Set each time), `exitWhatIf()` (sets null, live "What-if ended, nothing changed"). Key `x` (same guard as `b`): when what-if is on and an Item is selected, toggle it. Pass `removed` to `StarMap`, `Brief`, `Inspector`, `WhatIfChip`.
- `paint.ts`: `Focus.removed: Set<GNode> | null`. A removed star draws as the unknown style (dashed outline, no fill, no core) at `globalAlpha * 0.35`; links and Overlap arcs with a removed end target alpha 0; removed stars get no canvas name unless selected. Uses the existing `ease`, so reduced motion keeps the 140 ms dim. `StarMap.tsx`: prop `removed`, effect sets `painter.focus.removed` and calls `wake()` (same as `matches`). No re-layout: stars never move.
- `Brief.tsx`: header button `What if…` (ghost, `aria-pressed`); on: each row gets a native `<input type="checkbox">` (`accent-[var(--indigo-bright)] size-4`, wrapped in a 40x40 label, `aria-label="Remove {name} in what-if"`); a pair row ticks `row.removes`, disabled with `title="Unknown which one to keep: tick it in the Inspector"` when null. Meter switches to `20,082 → 19,229`, a `−853 (4%)` line in `text-indigo-bright`, the removed share shown as an outlined (border only) segment at the bar's end, and `3 removed · 1 with unknown cost, not counted`. Buttons under the meter: `Reset` (clears ticks, stays on) and `Exit what-if`. Phone pill text while on: `What-if −853`.
- `Inspector.tsx`: when on, one outline button under the cost line: `Remove in what-if` / `Put back` (`aria-pressed`), with `Removes 4 Items` when it is a plugin.
- `WhatIfChip.tsx` (desktop >=640 only, `fixed bottom-6 left-1/2 -translate-x-1/2`, glass, h-10): `What-if: 3 removed · −853 tokens` + `Reset` + `Exit` (X, `aria-label="Exit what-if"`). Shown while on and the Brief is hidden (cluster focus, chat). `aria-live="polite"` announces each change: `Removed sort-gasket. Session start 19,984 tokens, saves 98.`
- Esc keeps its current order and does not end what-if. Chat answers and search highlights still work on top of ghosts.
- Screenshots (demo-250): tick top 5 -> meter `20,082 → 19,229`, five ghosted stars, their arcs gone; Inspector on a plugin -> `Removes N Items`, children ghosted; enter a cluster -> chip visible; 390: pill reads `What-if −853`, Inspector button reachable; reduced motion (emulated) -> ghosts appear without the flight.
- Accept: asserts pass; nothing fetched or written (Network tab shows no request on tick); `Exit` restores the exact map; tracker updated. Privacy: none (client-only, no write). No Opus review.

## #71: cluster health badge (size S-M, after #69)
Goal: every named cluster shows cost, usage share and overlap count, so the costliest stand out; it follows what-if.
- `model.ts`: `export type Health = { known: number | null; unknown: number; useShare: number | null; overlaps: number; rank: number | null }`, `export function clusterHealth(model: Pick<Model, "clusters" | "nodes" | "overlaps" | "usageWindow">, removed?: ReadonlySet<GNode> | null): Map<Cluster, Health>`. `known` = sum of non-removed members' `always_on` (null if none known); `useShare` = members' usage counts / all non-removed nodes' counts (null without `usageWindow` or a 0 total); `overlaps` = non-distinct Overlaps with both ends inside and neither removed; `rank` = 1-based by known desc, ties by name, null when unknown.
- Asserts (first): two invented clusters give the exact shares (e.g. 30/100 -> 0.3); unknown-only cluster -> known null, rank null; no usage window -> useShare null; removing a member drops its cost, uses and its overlaps; demo-250 ranks `Tidy the changelog` 1 (1,361), `Hook script execution` 2 (1,343), `Plan the quarterly review` 3 (860).
- `paint.ts`: after the cluster-name loop, for each cluster whose name was drawn (`c.hit`) and not focused, draw one line 6 px under the name box: `1,361 tok · 12% of uses · 4 overlaps` (`450 11px` sans, `text-3`, stroke like names). Unknown -> `cost unknown`; no usage -> part omitted; 0 -> `no overlaps`; `<1%` below 1%. Rank 1-3 draw the cost part in `--warn` (status, 10:1+ contrast). Use `fits()` so a badge never moves or hides a name (skipped on collision). Desktop only: skipped when `phone` or under cluster focus. Recompute the map only when `removed` changes (cache in the painter keyed on the set), not per frame.
- `ClusterCard.tsx`: under the cost box add `12% of all recorded uses` (omit when null) and `Costliest cluster: 1 of 30` (omit when rank null). Phone sees health here.
- Screenshots: fitted demo-250 1440x900 shows the three warn figures above; no badge overlaps a name; 390 shows no canvas badges and the card lines; with what-if removing a member of `Tidy the changelog` its badge drops live.
- Accept: asserts pass; `layout:check` columns unchanged; no name lost vs main at z=1 (compare `nameAll`); tracker updated. Privacy: none. No Opus review.

## #68a: explain summary backend (size S-M, parallel)
Goal: one local summary, with a public variant built from the Snapshot allowlist.
- `explain.py`: `def explain(data: dict[str, Any], public: bool = False) -> dict[str, Any]` and `def render_explain(summary: dict[str, Any]) -> str`. When `public`, start with `data = snapshot(data)` (no new Snapshot field; Snapshot already drops usage, ids, provenance, scrubs text). Output (names only, no ids): `{"public": bool, "items": int, "known": int | None, "unknown": int, "clusters": [{"name", "items", "always_on": int | None}] (3 largest by member count, ties by name), "costs": [{"name", "kind", "always_on"}] (top 5 via report `_ranked`), "unused": [{"name", "kind", "always_on": int | None}] | None (top 5 never seen via `report._never_used`, known cost desc then unknown, then name; None without `usage_window`), "window": {"files": int, "days": int} | None, "actions": [{"reason", "tokens_saved"}] (first 3 of `suggest(data)`)}`. `render_explain`: markdown, fixed headings `# My Claude Code setup`, `## Largest clusters`, `## Costliest always-on`, `## Not used lately`, `## Three suggested actions`; public text ends `Shared from Constellation (public summary: no dates, paths or ids).` and its unused section reads `Not included in public summaries.`
- `server.py`: `GET /api/explain?public=false` (`local_only`) returns `{**summary, "text": render_explain(summary)}`; loads via the existing `read_brief()` loader.
- Tests first (`tests/test_explain.py`, HTTP API, invented data): `test_explain_lists_three_largest_clusters_five_costs_unused_and_three_actions` (4 clusters/6 costs/4 suggestions in -> 3/5/3 out); `test_explain_never_counts_unknown_cost_as_zero`; `test_explain_unused_is_null_without_usage_window`; `test_explain_ties_are_ordered_by_name`; `test_public_explain_has_no_usage_ids_or_private_text` (markers `/Users/demo-person/x`, `a@b.example`, `local/1/srv`, original ids, `2026-10-` dates: none in the JSON body, `unused` and `window` null); `test_public_explain_has_no_remove_unused_action`; `test_explain_text_has_fixed_headings_and_public_footer`; `test_explain_404_when_scan_unreadable`.
- `pyproject.toml`: add `src/constellation/explain.py` to `only_mutate`; zero survivors.
- **Opus privacy review required** (shareable text): checks public mode always runs `snapshot()` first and reads nothing else, no id/usage/date/path in public JSON or text, `render_explain` adds only fixed strings, `actions` cannot carry `remove_unused` reasons, no provider import.
- Accept: the 8 tests pass; mutmut clean; `curl` checks in Validation; tracker updated.

## #68b: explain card UI (size S, after #71 and #68a)
- `ExplainCard.tsx`: shadcn `Dialog` (phone: full-height sheet, `max-h-dvh`, safe-area padding). Opens from a TopBar button (`BookOpenIcon`, desktop text `Explain my setup`, phone icon with that `aria-label`) and once automatically on the first visit (`localStorage` `constellation.explain` != `seen`, try/catch, and not when `navigator.webdriver`, so browser checks are not blocked). Only mounted when the Brief loaded (static Snapshots have no API).
- Content: title `Your setup at a glance` (serif italic 22 px), four sections in the headings' order; each cluster and Item row is a button that closes the dialog and enters the cluster / selects the Item (existing `onCluster` / `selectById`). Footer: `Copy summary` (local text; note `Includes usage dates. For sharing, copy the public version.`) and `Copy public version` (fetches `?public=1`). Copy success: button reads `Copied` for 2 s plus a polite live message; failure: `Could not copy. Select the text below instead.` and a read-only textarea.
- States: loading (`Spinner`, `Reading your scan…`), error (`Could not read the summary.` + `Try again`), no cost (`Cost was not measured in this scan.`), no usage (`Usage was not read in this scan.`). Focus goes to the title on open and back to the trigger on close; Esc closes; dialog animations are 0 under reduced motion (existing rule).
- Screenshots (demo-250): desktop dialog lists `Tidy the changelog (28)`, `Plan the quarterly review (26)`, `Hook script execution (22)`, top cost `quarterly-ledger-reconciliation-helper 410`, `59 never seen in 132 transcripts`; public copy pasted into a text field has no dates; 390 sheet scrolls, buttons 44 px.
- Accept: auto-open once only; nothing auto-opens under agent-browser; no new fetch besides `api/explain`; tracker updated. Privacy: covered by #68a review.

## Validation (run in each ticket worktree; the last one proves the batch)
```sh
uv sync --all-extras && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest -q
uv run mutmut run && test -z "$(uv run mutmut results)"
(cd frontend && npm ci && npm run lint && npm run build && npm run layout:check && npm run chat:check)
mkdir -p /tmp/cx-check && uv run constellation open docs/design/demo-250.json --no-browser --port 8765 --checklist /tmp/cx-check/cleanup.md &
sleep 3
curl -s http://127.0.0.1:8765/api/explain | python3 -c 'import json,sys; d=json.load(sys.stdin); assert [c["items"] for c in d["clusters"]]==[28,26,22] and len(d["costs"])==5 and len(d["unused"])==5 and len(d["actions"])==3'
curl -s 'http://127.0.0.1:8765/api/explain?public=1' | python3 -c 'import json,sys; t=sys.stdin.read(); d=json.loads(t); assert d["unused"] is None and d["window"] is None and "2026-" not in t and "usage" not in t'
git diff --name-only origin/main | grep -E 'chat\.py|answer\.py|Chat\.tsx' && echo "OWNERSHIP VIOLATION" || true
kill %1
```
Then the screenshot lists above with `vercel-plugin:agent-browser` on `http://127.0.0.1:8765` at 1440x900 and 390x844.
