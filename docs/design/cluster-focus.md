# Cluster focus design note (ticket #38, T8 + the card half of T9)

Click a cluster name: the camera flies in, the rest of the sky dims, members get names, costs and Overlaps, and a left card says
what the cluster costs. Read with `explore-ux.md` D and H, `DESIGN.md` and `graph-app.md`. Approved: a custom rAF flight on d3
`interpolateZoom`. **Build only after #36 (halo follows drag) merges**: both edit `paint.ts`, and framing uses its `haloOf(c)`.

Deviations for the tracker: card shows the **top 3** by cost (plan D said 5; user asked 3); the T9 card is specified here too.

## 1. Camera flight

**One camera owner.** `StarMap` gets one `fly(to: View, onLand?)` and one `stopCamera()`; `View = { x, y, k }` (x, y = graph point at
the screen centre, like `centerAt`). Everything that moves the camera programmatically goes through `fly`: cluster enter, exit,
hop to another cluster, and `glideTo` (search pick, Inspector rows, Brief pairs). Reason: force-graph's `zoom(k, ms)` and
`centerAt(x, y, ms)` are two uncoupled tween.js tweens; a `g.zoom(k, 0)` from our flight does not cancel a running tween, so the
two would fight. Converting `glideTo` to compute a `View` and call `fly` removes that and its sideways drift (same targets as now).

**Path.** Once at start: `const i = interpolateZoom.rho(1.2)([c.x, c.y, W / k0], [to.x, to.y, W / to.k])` (from `d3-interpolate`;
rho 1.2 is a slightly flatter arc than d3's sqrt 2, so a hop between neighbouring clusters does not balloon out to the whole map).
Each frame: `t = min(1, (now - t0) / ms)`, `p = i(easeCubicInOut(t))` (`d3-ease`), `g.zoom(W / p[2], 0); g.centerAt(p[0], p[1], 0)`,
exactly the pair of calls the wheel handler already makes. Add `d3-interpolate@3.0.2`, `d3-ease@3.0.2` (already in the lock via
d3-zoom; pin exactly) and their `@types` at versions at least two weeks old.

**Duration by distance.** `ms = clamp(i.duration * 0.8, 700, 1300)`. d3's `duration` is `S * 1000 * rho / sqrt2`, S being path length in
log-zoom units, so it already grows with distance and zoom ratio. Reference points (demo-250, 1440x900):

| Move | zoom ratio | ms |
|---|---|---|
| enter a cluster already near the centre | ~3x | 700 (floor) |
| enter a small cluster at the rim | ~6x + pan | ~1000 |
| hop to a neighbouring cluster at focus depth | ~1x, pan 2-3 views | ~1100 |
| exit to the fitted view / hop across the map | 4-6x | 1000-1300 (cap) |
| `glideTo` an Item (was 750 fixed) | any | same rule, floor 700 |

Easing: in-out cubic, no overshoot, no bounce (scroll-craft consulted for easing only). **Reduced motion**: `ms = 0`, one frame jump;
the dimming still eases with a 140 ms time constant (`FEEL.focusFadeMs` is used even when `reducedMotion`, unlike `fadeMs`), labels
appear without stagger.

**Coexisting with the eased wheel zoom (reuse, do not fight).** The wheel handler owns `zoomTo`; the flight owns `cam`. `onWheel` and
`pointerdown` call `stopCamera()`; `fly` cancels `zoomTo.raf`; any canvas keydown but Escape cancels. A cancelled flight keeps the
focus state (dims, card) and counts as landed (`focus.landAt = now`). On landing set `zoomTo.kT = to.k` so a wheel flick starts from
there. Zoom limits are untouched: `fitK * 0.6 .. fitK * 10`.

**No per-frame allocation in our code**: interpolator, `t0`, `ms`, target and tick closure are made once per flight; d3's `i(t)`
returning a 3-element array is the one accepted allocation; `g.centerAt()` (allocates) is read only at flight start.

## 2. Target framing

Pure functions in `layout.ts` so `layout:check` runs them in Node:

- `fitView(nodes, clusters, insets, W, H) -> View`: today's `fit()` maths moved out of `StarMap`, shared with the metrics script.
- `focusView(halo, insets, W, H, fitK) -> View` with `halo = { x, y, r }`:
  free box `L = left + pad, R = W - right - pad, T = top + pad, B = H - bottom - pad` (pad 36 desktop, 14 phone);
  `Rs = 0.86 * min(R - L, B - T) / 2` (0.14 keeps room for rim names and the halo's soft edge);
  `k = clamp(Rs / halo.r, fitK, fitK * 10)`; `x = halo.x - ((L + R) / 2 - W / 2) / k`, `y = halo.y - ((T + B) / 2 - H / 2) / k`.
  The same rule serves the big "Other" region: when its circle already fills the free box at `fitK` the flight is mostly a pan.
- Insets at focus time: `top` = header bottom + 8 (as `measureInsets`); desktop `left` = card right + 8 (16 + 340 + 8 = 364), `right` =
  Inspector width + 24 only if the Inspector is open; phone `bottom` = the 40dvh sheet + 8, `left = right = 0`.
- **Halo source**: frame on `haloOf(c)` from #36 (live centre = home + mean member offset, radius up to 1.4 c.r), read once at flight
  start. At rest it equals `(c.x, c.y, c.r)`. The target is frozen for the flight; if the reader drags inside a focused cluster the
  camera does not chase (the reader is driving). Dimming is by membership (`n.cluster === focus.cluster`), never geometry, so a
  dragged member stays lit.

The card mounts in the same commit, so StarMap measures insets in a rAF after it; `measureInsets` learns the card selector
`section[aria-labelledby="cluster-title"]` (same branch as the Brief).

## 3. Timeline of an enter (desktop)

t=0: `focus.cluster = c`, hash pushed, flight starts, Brief collapses, dims start (240 ms tau). At 30% of the flight the card slides
in (opacity 0 -> 1, translateX(-8px) -> 0, `--t` 240 ms `--ease-out`). On landing `focus.landAt = now`; member names stagger in 25 ms
apart by cost rank (cap 400 ms) with their cost lines; then the canvas idles (`busy()` false). Exit reverses it: card leaves at t=0
with `--ease-in` 140 ms, dims lift over the flight, which ends at `fitView`.

## 4. Dimming levels (`paint.ts update()`, new `FEEL` knobs)

| Element | in focused cluster | touching it (one end in) | elsewhere |
|---|---|---|---|
| stars `n.a` | 1 | (n/a) | `FEEL.focusDim` 0.12 (above `--fade` 0.1 so the map stays legible as context) |
| halos `c.a` | 1 | (n/a) | `FEEL.focusHalo` 0.2 |
| Relation links `l.a` | 1 (hot rules unchanged) | 0.35, still x0.45 as a cross-cluster link | 0.06 |
| Overlap arcs `o.alpha` | 0.7, **all verdicts** incl. `overlap` | 0.15 | 0 |
| cluster names | focused name not drawn (it is in the card and breadcrumb) | (n/a) | hidden while flying; 0.4 after landing if it fits, clickable to hop |

Hover and selection keep today's rules; a lit neighbour outside the cluster rises to 0.6, not 1, so the cluster stays the subject.
Search matches override the dim (lit and ringed as now); typing does not exit focus. The focus change fades with `focusFadeMs` 240,
hover with `fadeMs` 110 as before. Overlap verdict text at arc apexes stays hover/selection only.

## 5. Labels at focus depth (`post()`)

- **Who is named.** In focus the z gate is replaced for members: every member is a candidate whatever the zoom; non-members get no
  name (except lit hover neighbours, rank 1 as now). Order: the focused Item, its lit neighbours, then members by focus rank =
  always-on cost desc (unknown after known), then degree, then name. The rank is computed once on enter into a `Map<GNode, number>`.
- **Stagger.** A member's name alpha is `clamp01((now - landAt - 25 * min(rank, 16)) / 140)`, so at most 400 ms of stagger even for
  "Other"; reduced motion: alpha 1 at landing.
- **Collision.** Keep the greedy placer and the reserved chrome boxes (card on the left now counts through `view.left`). Names over
  22 chars are cut to 21 + "..." on the canvas only (full name in hover, card and Inspector). A name that does not fit is skipped,
  never shrunk; wheeling in frees space and more names come, which is the progressive reveal. The card list is the complete,
  accessible equivalent, so nothing is lost when a name is skipped.
- **Second line (cost).** Under a placed name, JetBrains Mono 10 px `--text-3`: `1,240` (always-on tokens) or `unknown` in Inter
  italic 10 px; it is drawn only if its own box fits too. Shown when the on-screen radius `halo.r * k >= 160` or the cluster has <= 12
  members, so tiny demo clusters still show it at landing.
- **Unused.** If `model.usageWindow` exists and `n.usage?.count === 0`, the cost line becomes `1,240 · not seen` (same ink). No usage
  entry means not tracked: no tag. Text, not a new glyph: the star already carries kind (colour + shape) and unknown (hollow).
- **Kind glyphs.** None in canvas labels: the star directly above each name is the glyph. Glyphs appear in the card rows (`.glyph`).

## 6. Hit-testing cluster names and entry points

- `post()` records each drawn name's screen box on its cluster in a preallocated `c.box: [x0, y0, x1, y1]` plus `c.hit: boolean`
  (true only when drawn at alpha > 0.3). Hit box = text box padded 6 px (10 px on `pointer: coarse`) and at least 44 px tall.
- `painter.clusterAt(x, y)` scans the <= 30 clusters. `onBackgroundClick(e)` first asks it: a hit enters (or hops). Names never sit
  on stars, and force-graph only calls `onBackgroundClick` when no node is under the pointer, so there is no clash with node clicks.
- `pointermove` on the wrapper (rAF-throttled) sets `focus.nameHover`; the hovered name draws in `--text` at alpha 1 and the cursor
  is `pointer`. Check whether force-graph writes `cursor` on its canvas; if it does, set ours on the same element and only while
  `focus.hover` is null.
- Other entries: the TopBar "24 clusters" becomes a Popover list (name, count, by size; search's Command styling), also the
  keyboard path; and the `#cluster=<slug>` deep link after the first fit. A Clusters group in search is T11.

## 7. Cluster card (`ClusterCard.tsx`, data from pure `clusterSummary(c)` in `model.ts`)

Panel tokens as the Brief: `.glass`, 1px `--line-1`, `--radius-xl`, `--shadow-float`, desktop 340 px at `top 76 / left 16`,
`max-h calc(100dvh - 92px)`, body scrolls with `overscroll-contain`. `<section aria-labelledby="cluster-title">`. Top to bottom:

1. Header row: ghost icon button `ArrowLeft` 40 px, `aria-label="Back to the whole map"`; caption "Cluster" in `--text-3`.
2. Name `h2#cluster-title` Newsreader italic 22 px (`display-sm`), `tabIndex={-1}`; under it "18 Items" (`ui`, `--text-2`).
3. Kinds mix: Badge chips, glyph + count + kind name ("9 skills", "2 MCP servers"), by count desc, wrap.
4. Always-on stat card (`bg-surface-2`): `mono-stat` "12,340" + caption "tokens always on (known)"; under it in `--text-3`
   "7 of 18 have unknown cost, not counted". All unknown: the word "unknown" (Inter italic 16 `--text-3`), never 0. A known sum of 0
   is shown as 0. Unknown is never added in.
5. "Most expensive" - top 3 members with known cost, reusing the Brief row (glyph, name, indigo bar relative to the cluster's top
   cost, mono value); click = select (Inspector), hover = `onPreview`. Fewer than 3 known: show what exists; none: hide the section.
6. "Overlaps inside" (only if any): count per verdict ("2 duplicates, 1 wrapper, 3 overlaps"), then up to 4 pair rows "a / b"
   with the verdict caption; click frames both and selects the removable one (the Brief's `selectPair` rule, taking a `GOverlap`).
7. "Unused" (only if `model.usageWindow` and >= 1 tracked member): "6 of 11 tracked Items not seen in 86 transcripts over 4 days",
   caveat in `--text-3`: "Claude Code deletes older transcripts". Untracked kinds are left out of the denominator.
8. `<details>` "All 18 Items" (open by default when <= 12 members): rows glyph, name (wraps), mono cost or italic "unknown". This is
   the accessible equivalent of the canvas and the Tab target inside the cluster.

**Phone (<= 640 px)**: a Brief-style bottom sheet (top radius 16, grab bar) at `max-h 40dvh`, rows 1-4 above the fold, framed above
it; picking a member swaps to the 58dvh Inspector sheet with "Back to Documents", which restores the card.

## 8. Panels, slot rule, entering and leaving

- **Left slot, one occupant**: card, Brief or Chat. Entering focus collapses the Brief (its pill hides too, the card sits where the
  pill was) and remembers whether it was open; exiting restores it. Opening the Brief (`b` or pill) while focused exits focus.
- **Inspector**: >= 960 px card left + Inspector right. 641-959 they alternate (existing rule): selecting a member hides the card
  (breadcrumb stays) and the Inspector shows "Back to Documents"; phone as above.
- **Breadcrumb**: in `TopBar` the count line becomes `<nav aria-label="Breadcrumb"><ol>` "All clusters" (button, returns) /
  "Documents" (`aria-current="page"`, truncates at 24ch). Phone: same line under the wordmark.
- **Exit** by: card Back button, breadcrumb root, Escape, browser Back, a background click outside the focused halo
  (`hypot(screen - haloCentre) > halo.r * k`) with nothing selected, or pinching/wheeling out below `0.5 * kFocus` after landing
  (state change only, no flight: the reader is already pulling back). A background click inside the halo only deselects.
- **Escape order**: search popover (input handles it) -> Brief (own handler) -> chat -> Inspector -> cluster focus -> the highlight (search or chat chip). Escape on the map (`close()`) and a click on empty sky both clear the highlight, so one of them always returns the whole map to normal (#49).
- **History**: enter = `pushState({cluster: slug}, "", "#cluster=" + slug)`; hop = `replaceState` (no history spam); exit by UI =
  `history.back()` when our entry is on top, else `replaceState` without hash; `popstate` sets state without pushing. Slug =
  lowercased name, non-alphanumerics to `-`, collisions get `-2`. Works in a static Snapshot (hash only).
- **Search fly-to**: choosing a member keeps focus and `fly`s to it; choosing an Item outside exits focus (`replaceState`) and
  glides to it in one flight. Same for Inspector relation rows that lead outside.

## 9. Keyboard and focus management

Entered by keyboard (clusters popover, Enter): focus moves to the card `h2` so it is read out; by pointer: focus stays on the canvas
so arrows work at once. Live region (Atlas): "Documents, 18 Items, 12,340 tokens known, 7 unknown"; on exit "Whole map". In focus,
arrows step among members only (`step(members, ...)`, starting at the member nearest the halo centre). Tab order: search -> card
(Back, rows, list) -> canvas. On exit, focus returns to what entered it (popover trigger) or the canvas.

## 10. Performance (250 Items)

A flight is 42-78 frames of one full paint, the same load as a wheel flick today. While `focus.flying`, skip `clusterLabel` for other
clusters, `itemLabel` for non-members, and the glow sprite for stars dimmed below 0.15. Membership is `n.cluster === focus.cluster`
(no Set), focus rank is one Map built on enter, `c.box` arrays are allocated once in `buildModel`; add no per-frame arrays or
closures (the existing `lit`/`placed` allocations stay). Budget < 8 ms per frame at 250 Items via dev-only `performance.mark` around
`pre`..`post`; record median and p95 of one enter flight in `graph-app.md`.

## 11. Motion library: decided, not added

CSS suffices: the card is one opacity + translate enter/exit (`animate-card-in`/`-out`, `--t` and the two curves), the slot swap is
unmount/mount (no layout animation), the phone sheet reuses `animate-sheet-in`. Motion would pay only for a drag-to-dismiss sheet
spring, which nobody asked for. Revisit only if the Brief/card swap visibly jumps in screenshots.

## 12. `layout:check` and metrics additions (`scripts/layout-metrics.ts`)

For every demo at 1440x900 and 390x844 (insets as the script's fitted view, plus the card: left 364 desktop, bottom 0.4H + 8 phone):

- use `fitView` instead of the script's copy of the fit maths (same numbers; assert equal to the old copy once, then delete it);
- for every cluster `focusView(haloOf(c), ...)`: `k` in `[fitK, fitK * 10]`; the circle inside the free box; on-screen radius
  `r * k >= 120` desktop / `>= 90` phone (report clusters capped by `fitK * 10` separately, they pass);
- flight check: `interpolateZoom.rho(1.2)` from `fitView` to each target: `i(0)` and `i(1)` equal the endpoints within 0.5 px, and the
  clamped duration is in `[700, 1300]`;
- `clusterSummary` self-check (assert-based, like `costRadius`): known sum excludes unknown, all-unknown gives `null` not 0, top 3
  sorted by cost desc with name tie-break, unused counts only tracked members;
- focus label share: member names (half-em widths as the script already does, 22-char cut) placed greedily at `focusView` k with
  zero star/name overlaps; table column `focusNamed`, fail under 60% desktop / 40% phone.

## 13. Manual screenshot checklist (agent-browser, `demo-250.json`, `demo.json`, `demo-offline.json` only; never the real scan)

(1) pointer over a name: pointer cursor, name in `--text`; (2) mid-flight frame: no sideways drift; (3) landed 1440: card, named
members, costs, in-cluster arcs; (4) member selected: card + Inspector, stars clear of both; (5) 700 px alternation with "Back to
Documents"; (6) 390 px 40dvh sheet, cluster framed above, member -> sheet swap; (7) "Other" focus; (8) offline demo: "unknown", no 0;
(9) usage present vs absent; (10) hop to a neighbour name; (11) Esc sequence, Back, breadcrumb, browser Back, deep-link reload;
(12) reduced motion: jump + 140 ms dim; (13) keyboard: clusters popover -> Enter -> heading focused, Tab rows, arrows; (14) wheel
mid-flight stops cleanly, no snap-back.

## 14. Implementation checklist (Sonnet; start after #36 merges; `/prototype` the flight first if the feel is in doubt)

1. `package.json`: add `d3-interpolate@3.0.2`, `d3-ease@3.0.2` + matching `@types`, pinned exactly.
2. `layout.ts`: `type View`, `fitView`, `focusView` (pure); keep `haloOf` from #36.
3. `model.ts`: `Cluster.box`/`hit` (preallocated in `buildModel`), `slug`; `clusterSummary(c, model)`; tracker note on top 3.
4. `scripts/layout-metrics.ts`: section 12 checks; run `npm run layout:check`.
5. `paint.ts`: `Focus.cluster/flying/landAt/nameHover`, focus rank Map, `FEEL` knobs (`focusDim 0.12, focusHalo 0.2,
   focusFadeMs 240, flightRho 1.2, flightMin 700, flightMax 1300, labelStagger 25, focusFill 0.86`); `update()` levels (section 4);
   `post()` member labels, cut, cost line, unused tag, other-name 0.4, `c.box`; `clusterAt(x, y)`; skips while flying.
6. `StarMap.tsx`: `fly`/`stopCamera` (section 1), wheel/pointerdown/keydown cancel, `fitView`-based `fit`, `glideTo` via `fly`,
   prop `cluster` + effect (rAF, measure insets, fly to `focusView` or `fitView`), `onBackgroundClick` hit-test and exit rules,
   `pointermove` hover, member-only arrows, zoom-out exit in `onZoom`, card selector in `measureInsets`.
7. `Atlas.tsx`: `cluster` state, left-slot rule with Brief, Escape order, history push/replace/popstate + deep link, search and
   Inspector exits, live region, 641-959/phone alternation with "Back to <cluster>".
8. `TopBar.tsx`: breadcrumb nav; "N clusters" Popover list (Command styling) with `onCluster`.
9. `ClusterCard.tsx` (new) + `index.css` `animate-card-in/out`; `Inspector.tsx`: optional `backTo` button.
10. `npm run typecheck && npm run lint && npm run layout:check && npm run build`; section 13 screenshots; update `graph-app.md`
    (frame-time numbers) and `docs/plan-tracker.md` (status, the top-3 deviation, `glideTo` now on `fly`) in the same commit.
