# Plan: actionable first screen (#25)

Goal: in ten seconds the user sees the 5 most expensive Items and the 5 clearest duplicate/wrapper pairs, can fly to each, and can add each to a private cleanup checklist. Nothing new leaves the machine; nothing in the setup is edited.

Decisions this touches (from `docs/plan-tracker.md`): D4 privacy (redact before anything is shown or written), D11 cost (`always_on` sizes stars; unknown is never 0), #12 Suggestions (`suggest()` ranking and content-derived ids), review's checklist line format and `write_private` (0600). D10 Snapshot (#13) is static, so every new API is optional for the frontend.

## 1. Where the list logic lives (decision)

In Python, new module `src/constellation/brief.py`, served by `GET /api/brief`. Reasons: it reuses `suggest()`, `_known_costs`, `_ranked`, `redact` and the Suggestion ids that `review` already writes, so the app and `constellation review` agree on order and ids; it is pytest-testable; and the POST endpoint can then accept only an id and look the row up server-side (no client text is ever written). The frontend does no ranking.

Not done in TS: there is no frontend test runner, and duplicating `suggest()` would drift.

## 2. `brief(data, top=5) -> dict` (pure, in `brief.py`)

```
{ "cost":  {"rows": [Row], "unknown": int, "measured": bool, "frees": int | null},
  "pairs": {"rows": [Row], "unknown": int, "frees": int | null},
  "checklist": {"path": str, "ids": [str], "frees": int | null} }   # added by the server, not by brief()
Row = {"id", "kind", "item_ids": [..], "removes": item_id | null, "reason", "tokens_saved": int | null}
```

Cost list:
- Rank Items with known `always_on` by `_ranked(data, known)`: tokens descending, then name, then id (deterministic ties; same order as `constellation report`).
- Rows are Suggestion-shaped with kind `review_cost` (add to the `Literal`, NOT to `GENERATORS`, so `review` is unchanged), id via `suggestions._make("review_cost", (item_id,), reason, tokens)`. Reason: `"{name (kind)}: {n:,} always-on tokens every session. Is it worth it?"` (the existing `render_cleanup` wording).
- Items with zero known tokens are kept (they rank last); unknown Items are never ranked and never 0: `unknown` = count of Items without a known cost.
- `measured` = any known cost. Offline scan: `rows=[]`, `measured=false`, `unknown=len(items)`.

Pairs list:
- `[s for s in suggest(data)][:top]`: already known savings descending, then unknown, ties by item ids. Only `duplicate` and `wrapper` verdicts (`overlap` is not actionable; it stays on the map).
- `removes`: `use_underlying` -> `a_id` (the wrapper); `remove_duplicate` -> the cheaper known Item (ties by id), `null` if either cost is unknown.
- Offline: whatever local wrapper checks found; otherwise empty.

`frees` (the counter), one helper `frees(rows, known)`: sum of `known[i]` over the **unique** `removes`/item ids of the rows, so an Item that is both top cost and in a pair counts once; rows with unknown saving are left out and counted in `unknown_rows`. `null` when nothing is known (UI shows "not measured", never "0"). Same helper computes the checklist total.

## 3. Endpoints (`server.py`)

`create_app(scan_file, checklist=DEFAULT_CHECKLIST)`; `DEFAULT_CHECKLIST = ~/.cache/constellation/checklist.md` (next to `review.sqlite`); `constellation open --checklist PATH` overrides. Separate from `review --out cleanup.md` so neither refuses or clobbers the other.

- `GET /api/brief`: read the scan file per request (as `/api/constellation`), return `brief(data)` plus `checklist {path, ids, frees}`, ids parsed from the file (`(id xxxxxxxxxxxx)` regex). 404 as `/api/constellation` when the scan is unreadable.
- `POST /api/checklist`, body `{"id": "<12 hex>"}`:
  1. Validate: JSON content type only (415 otherwise), id matches `^[0-9a-f]{12}$` (422), id is a row of the current `brief(data)` (404). The client never supplies text.
  2. Idempotent: if `(id {id})` is already in the file, return 200 with `added: false`.
  3. Otherwise new text = existing text (or the header `Constellation never edits your config. Every change below is yours to make by hand.\n\n# Constellation cleanup checklist\n\n`) + one line in review's format `- [ ] {reason} {_saving(s)} (id {id})`, written with `report.write_private` (0600, truncate and rewrite; the file is small). `mkdir(parents=True)` on the parent; an OSError returns 500 with the path, never a crash.
  4. Returns `{added, path, ids, frees}`.
- Guard: refuse a checklist path that resolves under `~/.claude` (or the scan's source roots, if cheaply known): the app must never write into the setup. Checked once in `create_app`, CLI exits 2.

Local-write safety (one dependency `local_only` on both `/api/*` routes):
- `Host` header must be `127.0.0.1:<port>` or `localhost:<port>` (any port): blocks DNS rebinding. 403 otherwise.
- For POST: if `Origin` is present it must equal `http://{Host}`; if `Sec-Fetch-Site` is present it must be `same-origin` or `none`. A cross-site page cannot send `application/json` without a CORS preflight, and there is no CORS middleware, so the preflight fails.
- Still bound to `127.0.0.1` only (unchanged). No cookies, no auth tokens to steal.
- Vite dev proxy: it rewrites Host to the target, so dev keeps working; note it in the endpoint comment.

## 4. Frontend

New `frontend/src/components/Brief.tsx` (the concurrent #10 agent owns Inspector.tsx and Legend.tsx; do not touch them).

Data: Atlas fetches `api/brief` once after mount (relative URL). Any failure (static Snapshot, old server) -> Brief is not rendered and the map works as now. `checklist` absent -> the add buttons are hidden.

Desktop (> 640px):
- A `<section aria-labelledby="brief-title">` (NOT `<aside>`: StarMap's `measureInsets` reads the first `aside` as the inspector), `.glass` panel per DESIGN.md "Panel": left 16, top 76, width 340, `max-h` stopping 8px above the legend, own scroll. Coexists with the inspector on the right.
- Title "Where your context goes" (`section` style). Two groups, each a heading with its counter line and up to 5 rows:
  - "Most expensive, always on": row = kind glyph, name (body, truncate), tokens in `mono` right-aligned; footnote `N Items with unknown cost are not ranked` when `unknown > 0`; offline: "Cost was not measured in this scan." in italic text-3.
  - "Duplicates and wrappers": row = `A and B` (duplicate) or `A wraps B`, verdict word in caption, saving `~415` or italic "unknown".
  - Counter under each heading: `Removing these 5 frees ~12,400 tokens per session (estimate)`; `+ 2 with unknown cost, not counted` when any. `frees == null` -> "Saving not measured".
- Each row: the main area is a ghost button (min-h 40) that flies to the star; a trailing 36px icon button `+` with `aria-label="Add {name} to cleanup checklist"`. After a 200 response it becomes a check icon, `aria-pressed`/disabled, label "On checklist". Rows already in `checklist.ids` start as added.
- Footer (once anything is on the list): `3 on your checklist · frees ~N tokens (estimate) · <path in mono, overflow-wrap:anywhere>` plus "Nothing in your setup was changed." Errors show inline in `--warn` with icon and text ("Could not write the checklist: ...").
- Clean setup (no pairs): the pairs group says "No duplicates or wrappers found." and the cost list still shows, since cost is always worth a look. Both lists empty because offline and no wrappers: "Nothing to rank yet. Run `constellation scan` with a key to measure cost." (the Brief still renders so the user knows why).

Phone (390px):
- A bottom sheet in the inspector's style (`max-h-[46dvh]`, grab bar, rounded top), open on first load; the legend hides while it is open (pass `hidden` the same way the inspector does).
- Picking a row closes the sheet (the inspector sheet takes its place); the add button does not close it.

Dismiss and return:
- Close button (X, 36px) collapses it to a pill "Cleanup brief" with the pair count: desktop at left 16 / top 76; phone bottom-right above the legend, hidden while the inspector is open. The pill re-opens it.
- `b` toggles it when focus is not in an input (same guard as Escape in Atlas). Escape inside the Brief collapses it and moves focus to the pill; Escape elsewhere keeps its current meaning (close the inspector).
- Dismissal is remembered per browser in `localStorage["constellation.brief"]` inside try/catch; with no storage it starts open.
- Keyboard order: TopBar search, Brief rows (Tab between row and its add button), then the canvas. On open, focus does not move (it is not a dialog; the map stays live). The sr-only live region announces "Added {name} to checklist".

Atlas hooks (small):
- `brief` state + fetch; `briefOpen` state; render `<Brief ... onItem={selectById} onPair={selectPair} />`.
- `selectById(id)`: find the node, `select(n)` (existing glide + inspector).
- `selectPair(row)`: select the `removes` Item if known else `item_ids[0]` (for a wrapper that is the wrapper), so the inspector shows it and the map draws its Overlap arc to the other; glide with the pair framed (below).

StarMap (the one change outside Brief/Atlas, about 10 lines):
- `glideTo(n, other?)`: with `other`, centre on the midpoint and zoom to `min(current target, fit of the two plus padding)`; offsets as now.
- `measureInsets`: `view.left = section[aria-labelledby="brief-title"]` right edge + 8 when visible on desktop; `fit` and the glide offset use `(right - left) / 2` instead of `right / 2`; the name placer's chrome check (paint.ts) treats `view.left` like `view.right`. Re-measure when the Brief opens or closes (the same hook as the panel slide).

## 5. Tests

`tests/test_brief.py` (pure, no server):
- cost order by tokens desc, ties by name then id; zero kept; unknown never in rows and counted in `unknown`; offline -> `measured false`, empty rows.
- pairs equal `suggest(data)[:5]` (order, ids); `overlap` and `distinct` never appear; `removes` for wrapper = a_id, duplicate = cheaper, unknown -> None.
- `frees`: unique ids (an Item in both lists counted once), unknown rows excluded, all unknown -> None never 0.
- `review_cost` ids stable across reordered input and absent from `suggest()` (review unchanged).
- reasons redacted (plant a secret in a description, as `test_suggestions.py` does).

`tests/test_server.py` (TestClient with `base_url="http://127.0.0.1:8765"`; existing tests switch to that base URL):
- GET brief shape; checklist ids from an existing file.
- POST adds one line, file mode 0600, line matches review's format; second POST same id -> `added false`, file bytes unchanged.
- unknown id 404, bad id 422, `text/plain` 415, `Host: evil.example` 403, `Origin: http://evil.example` 403, `Sec-Fetch-Site: cross-site` 403.
- a copied config dir and the scan file are byte- and mtime-identical after POSTs (reuse the snapshot helper from the review tests).
- checklist path under `~/.claude` (monkeypatched home) -> `open` exits 2.
- unwritable checklist dir -> 500 with a message, server keeps serving.

Frontend: `npm run lint`, `build`, `layout:check`; screenshots from `demo.json`, `demo-offline.json`, `demo-250.json` only (desktop rest with Brief, pair selected with both stars framed, item added, collapsed pill, phone sheet, phone after picking a row, offline Brief).

## 6. Steps (in order)

1. `suggestions.py`: add `"review_cost"` to the kind `Literal` (not to `GENERATORS`).
2. `src/constellation/brief.py`: `brief()`, `frees()`, `checklist_ids(text)`, `append_line(path, s)` using `report.write_private` and `report._saving`. Write `tests/test_brief.py` first (/tdd).
3. `server.py`: `local_only` dependency, `GET /api/brief`, `POST /api/checklist`, `checklist` param; `cli.py`: `open --checklist` and the `~/.claude` guard. Extend `tests/test_server.py`.
4. `frontend/src/graph/model.ts`: `Brief` and `BriefRow` types only.
5. `frontend/src/components/Brief.tsx`: panel, sheet, pill, rows, add flow, counters, empty and offline states.
6. `Atlas.tsx`: fetch, open state, `b` key, `selectById`, `selectPair`, live-region text, legend `hidden` on phone while the Brief sheet is open (Legend already takes `hidden`; only the value passed changes).
7. `StarMap.tsx` (+ paint.ts chrome check): `glideTo(n, other?)`, `view.left`.
8. Screenshots with demo data; update `docs/design/graph-app.md` (one section) and `docs/plan-tracker.md` (#25 status, the `review_cost` kind and `/api/brief` + `/api/checklist` as new decisions) in the same commit.

## Risks and open points

- `GET /api/constellation` gains the Host check too; this is a behaviour change (blocks DNS rebinding reads), flagged for the reviewer.
- Deviation candidate: the plan had no web write endpoint ("web endpoints (#10/#11)" were read-only). This adds one, limited to a private file outside the setup. Record in the tracker and confirm with the user before step 3.
- The removed Item for a duplicate with unknown cost is undecided (`removes: null`); the checklist line still says "remove one of these two".
