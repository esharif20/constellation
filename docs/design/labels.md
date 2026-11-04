# Labels and hover tooltip design note (ticket #37, T7)

Whole-map (non-focused) canvas labels and a DOM hover tooltip with cost. Read with `explore-ux.md` H, `DESIGN.md`, `graph-app.md`.
Focus-depth labels stay as `cluster-focus.md` section 5 says. Builds on #36 and #38 (both on main). Demo data only.

Deviations for the tracker (need the user's nod): (a) the hovered Item's canvas name is 12 px 550 (plan H), not 13 px 600
(DESIGN.md canvas line), and is hidden while its tooltip shows; (b) labels no longer sit at a zoom-scrubbed partial alpha: they
ease in and out over time on a zoom threshold (AA, section 3). The cluster-name band 1.2-1.8 becomes show below 1.45, hide above
1.55; (c) the canvas ellipsis is one `…` (U+2026), not `...`, in focus too (same width budget, one glyph).

## 1. What shows at each zoom (z = k / fitK)

| z | Cluster names (Newsreader italic) | Item names (Inter) | Why |
|---|---|---|---|
| < 1.15 (fitted) | clusters of 5+ members | hubs (degree >= 4) and heavy stars (`n.r >= 7`, about the top 10% of known always-on cost) | the map reads as regions, plus the few Items that matter for structure or cost |
| 1.15 - 1.45 | all clusters (3+) that find a spot | + degree 2-3 from z 1.0-1.15 | names of small regions arrive before leaves |
| 1.45 - 1.55 | hysteresis band: no change | + leaves from 1.3 | stops names flickering on a wheel tail |
| > 1.55 | hidden (the hovered or selected Item's cluster keeps its name, as now) | every Item that fits | at this depth the stars are the subject |

Start rule per Item, one line in `post()`: `start = 1.3 - min(0.9, max((degree - 1) * 0.15, n.r >= 7 ? 0.45 : 0))`.
Unknown cost gets no boost (unknown is not big). Lit Items (hover, selection, search, chat matches) are named at any zoom.

## 2. Hierarchy: size, weight, ink

| Role | Font | Size | Weight | Ink | Resting alpha |
|---|---|---|---|---|---|
| cluster name | Newsreader italic, `letterSpacing 0.03em` | 13-17 px by members (12-16 phone), x0.82 when crowded | 400 | `--halo-name` | 0.9 (0.63 crowded) |
| hovered / previewed Item (rank 0) | Inter | 12 px | 550 | `--text` | 1 |
| selected Item | Inter | 12 px | 550 | `--text` | 1 |
| search / chat match, lit neighbour | Inter | 12 px | 450 | `--text` | 1 |
| other Item | Inter | 11 px below z 1.6, 12 px from 1.6 | 450 | `--text-2` | 1 |
| Overlap verdict at an arc apex | Inter | 11 px | 450 | `--text-2` | arc alpha, >= 0.3 |

Cluster names stay the largest text and the only italic serif; Item names never exceed 12 px, so a region always out-ranks a
star at a glance. Weight, not size, marks the subject (550 vs 450). No canvas text uses `--text-3` on the whole map.

## 3. Alpha by time, not by zoom position

Partial alpha is motion, never a resting state. `GNode` gets `la` (label alpha, preallocated 0 in `buildModel`), eased with
`FEEL.labelMs` 140 toward 1 when `z >= start` and toward 0 when `z < start - 0.05`; drawn alpha = `la * n.a`. Cluster names keep
`c.la` and get the same treatment from `zoomAlpha` (target 1 below z 1.45, 0 above 1.55). Reduced motion: snap to the target.
A collision skip is instant (a name that lost its spot is not drawn half-faded over the winner).

## 4. Contrast (WCAG 2.x, computed; ground = what is under the glyph edge)

Worst ground: `--k-other` glow at 0.30 over two halos on `--night-lift`. The 4 px night stroke puts `--night` under every glyph edge.

| Ink | alpha 1, on stroke | 0.9 | 0.63 | without stroke, worst glow |
|---|---|---|---|---|
| `--text` #f7f8f8 | 18.5 | 14.2 | 6.4 | 6.5 |
| `--text-2` #d0d6e0 | 13.5 | 10.5 | 4.9 | 4.75 |
| `--halo-name` #c9cdf0 | 12.7 | 9.8 | 4.7 | 4.45 (fails) |
| `--text-3` #8a8f98 (focus cost line only) | 6.1 | 4.9 | 2.7 (fails) | 2.1 (fails) |

So: the stroke is mandatory; every resting label has drawn alpha >= 0.63 (cluster names) or 1 (Items); `--text-3` only at alpha 1.
The 0.4 context names in focus are decorative duplicates of the clusters popover (cluster-focus.md), exempt.

## 5. Halo stroke

Every canvas name, verdict and cost line: `strokeStyle = ink.night`, `lineWidth = 4` (was 3 for Items), `lineJoin = "round"`,
`miterLimit = 2`, stroke then fill at the same `globalAlpha`. No `shadowBlur` (costly per glyph, and it blurs the night edge).

## 6. Collision and priority (greedy, first come keeps the space)

1. Chrome boxes: top band, panels (`view.left/right/bottom`), and the open tooltip's box (`view.tip`, set once per hover).
2. Hovered/previewed Item, only when it has no tooltip (preview from the Inspector, search or Brief rows).
3. Selected Item (always named, even while another star is hovered: exempt from the "unlit names are skipped" rule).
4. Search/chat matches: active result, then by always-on cost desc (unknown last).
5. Lit neighbours and Overlap partners, by cost desc.
6. Overlap verdict text (up to 8, as now).
7. Cluster names, by member count desc (`chooseSpot`, unchanged).
8. Everything else: `start` asc, then degree desc, always-on desc, name (deterministic).

A name that does not fit is skipped, never shrunk or nudged. Item names keep out of star discs on the whole map too (today only
in focus): reuse `clearOfStars` for ranks 4-8, which is what keeps label-on-star at 0.

## 7. Truncation

One pure `cutName(s, max = 22)` in `names.ts`: `s.length <= 22` returns `s`; else the first 21 chars with trailing `-_ .:/`
trimmed, plus `…`. Used for every canvas Item name (whole map and focus). Cluster names are not cut (they scale to 0.82 or skip);
offline cluster names over 28 chars are cut with the same function at 28. The full name is always in the tooltip, card, Inspector.

## 8. Kind glyphs

None on the canvas: the star above each name is the glyph (shape + colour, as `cluster-focus.md` 5). The tooltip shows the DOM
`.glyph[data-kind]` before the name, the same mark as the Legend, search and Inspector.

## 9. Hover tooltip (`components/Hover.tsx`)

Panel: `.glass`, 1px `--line-1`, `--radius-lg`, `--shadow-float`, `px-3 py-2.5`, `w-max min-w-[200px] max-w-[300px]`,
`pointer-events-none`, `aria-hidden` (the Inspector and live region are the accessible path). Top to bottom:

1. `.glyph` + name: Inter 14/500 `--text`, wraps to at most 2 lines (`line-clamp-2`, `overflow-wrap:anywhere`), never cut to 22.
2. Kind line, `caption` `--text-3`: "Skill · " + cluster name in Newsreader italic 13 `--text-2` (omitted for "Other").
3. Cost grid `grid-cols-[auto_1fr] gap-x-3`, `ui` 12: "Always on" `--text-3` / `1,240 tokens` mono `--text` (tabular);
   "On use" / same. Null or no entry: "unknown" in Inter italic `--text-3`, never 0. A known 0 is "0 tokens".
4. Usage (only if `n.usage`): count > 0 "12 uses, last 3 Nov" (year added when not the window's year); count 0 with a window
   "never seen in 4 days" (days = last - first + 1; no dates: "never seen in 86 transcripts"); no files: "no transcripts scanned".
   `ui` 12 `--text-2`. No usage entry: no line (the Inspector says "not tracked").
5. Badges row (only if any), DESIGN.md Badge: "Disabled" (neutral); strongest Overlap verdict with count, duplicate > wrapper >
   overlap: "Duplicate", "Wraps 2", "Wrapped by", "Overlaps 3", with a 6 px `--overlap` dot so it matches the arc colour.
6. `n.label || n.description`, one line, `truncate`, `caption` `--text-2`. Offline with neither: omitted.
7. Touch only: "Tap again to open" `caption` `--text-3`.

Pure helpers in `model.ts` (Inspector reuses them, moved from `Inspector.tsx`): `day`, `noun`, `usageLine(n, window)`, `tipBadges(n, model)`.

**Placement**, pure `placeTip(anchor, size, bounds, touch) -> { x, y, side }` in `names.ts`. Anchor = star screen centre and drawn
screen radius R, read once at show (`graph2ScreenCoords`). Bounds = `view.left + 8 .. W - view.right - 8`, `view.top + 8 ..
H - view.bottom - 8`. Gap 12 px. Pointer order: right (x = sx + R + 12, centred on sy), left, above, below. Touch order: above,
below, right, left (the finger covers the star and below it). First that fits wins; else the side with most room, clamped.
The hovered star's canvas name is hidden while the tooltip shows (it would repeat the name and sit under the panel's edge).

**Timing**: show after 120 ms dwell; while a tooltip was visible in the last 300 ms, moving to another star switches at once.
Hide at once on hover-out. Enter: opacity 0 -> 1 and `translateY(2px) -> 0`, `--t-fast` 140 ms `--ease-out`; reduced motion:
opacity only, 0 ms. Hidden (not repositioned) on wheel, drag, pan and any `fly`; shown again, placed afresh, 150 ms after the
camera rests if the pointer is still on the star. No tooltip for the selected star (the Inspector shows it), cluster names,
or previews from panels.

**Touch**: `pointerdown` on the wrapper records `pointerType`. First tap on a star: `focus.hover = n` (lights neighbours),
tooltip shows; no selection. Second tap on the same star: select (Inspector opens, tooltip hides). Tap another star: move the
tooltip. Tap the background: hide, then the existing background rules. No auto-dismiss timer.

**Keyboard**: no tooltip. Arrows select, so the Inspector opens; the live region line gains the cost: "X, skill, 1,240 tokens
always on" or "cost unknown". Tooltip-free keeps one accessible path.

## 10. Coexisting with the chrome

- Inspector: tooltip stays left of it (bounds); hovering other stars still works while it is open.
- Brief, Chat, cluster card: the left slot is in `view.left`, so the tooltip and names stay right of it.
- Highlight chip: `measureInsets` takes `view.top = max(header bottom, chip bottom) + 8` when the chip is shown.
- Search popover and other Radix portals (z 50) sit above the tooltip; the tooltip is a `z-10` sibling of the canvas wrapper,
  under every panel.
- Cluster focus: same tooltip for members and lit neighbours; the canvas cost line stays (they agree, from the same `cost`).

## 11. Performance

Hover lives in refs: `tipRef = { n, timer, warmUntil }`; React state changes only when the shown Item changes (one render per
hover, none per frame). `Hover` measures itself once in `useLayoutEffect` (rendered at `visibility:hidden`), calls `placeTip`,
writes `transform: translate3d(x, y, 0)`, then shows; it writes `painter.view.tip` and calls `wake()` once. Painter: `cutName`
results are cached in a `Map<GNode, string>` built in `makePainter`; `n.la` is a field, not a Map. No new per-frame arrays.

## 12. Implementation checklist (Sonnet; screenshots drive the refinement)

1. `names.ts`: `cutName`, `placeTip` (pure).
2. `model.ts`: `GNode.la`; move `day`/`noun` from `Inspector.tsx`; add `usageLine`, `tipBadges`. Inspector imports them.
3. `paint.ts`: `view.tip`; `start` with the heavy-star boost; `n.la` / `c.la` time-eased with hysteresis (section 3); ranks and
   sort keys (section 6) incl. the selected exemption; sizes and inks (section 2); `lineWidth 4`, `miterLimit 2`; `cutName`
   everywhere; skip rank-0 name when `focus.tip === f`; `clearOfStars` for all Item names; `FEEL.tipDelay 120, tipWarm 300`.
4. `components/Hover.tsx` (new): content (section 9), measure once, `placeTip`, enter/exit classes.
5. `StarMap.tsx`: `onNodeHover` -> dwell timer and `tipRef`; `pointerdown` records `pointerType`; touch tap/second-tap in
   `onNodeClick`; hide on wheel/drag/`fly`, re-show 150 ms after rest; `measureInsets` adds the chip; render `<Hover>`.
6. `Atlas.tsx`: live-region line with cost; pass `model.usageWindow` through.
7. `docs/design/make-demo.mjs`: two invented Items over 22 chars and two `disabled: true` in `demo.json`, so the cut and the badge
   can be screenshotted; regenerate.
8. `scripts/layout-metrics.ts`: section 13; `npm run typecheck && npm run lint && npm run layout:check && npm run build`.
9. Update `graph-app.md` (Semantic zoom line, link here) and `docs/plan-tracker.md` (status, deviations a-c) in the same commit.

## 13. `layout:check` additions (every demo, 1440x900 and 390x844)

- `labelClash`/`labelOnStar` for Item names: run the section 6 order (half-em widths, `cutName`) at z = 1, 1.6 and 2.5; any
  name box over another name or a star disc fails. Column `itemOverlap`: share of placed names that touch anything, must be 0.
- `nameCoverage`: at z = 1, hubs and heavy stars named, fail under 80% desktop / 60% phone; at z = 2.5, all Items named, fail
  under 50% desktop / 30% phone. Report both shares.
- `aaMin`: parse `--text`, `--text-2`, `--text-3`, `--halo-name`, `--night`, `--night-lift`, `--halo`, `--k-other` from
  `src/index.css`; compute the section 4 table at each ink's resting alpha floor; fail any value under 4.5.
- Self-checks (assert-based): `cutName` (22 kept, 23 -> 22 chars ending `…`, trailing separators trimmed); `placeTip` on a grid
  of anchors never leaves bounds, flips left within 300 px of the right inset, goes above first on touch; `usageLine` for count
  > 0, count 0 with and without dates, no files, no entry.

## 14. Screenshot checklist (agent-browser; `demo.json`, `demo-250.json`, `demo-offline.json` only)

(1) 1440 fitted: cluster names + hubs + heavy stars only; (2) z 1.3 and z 2: leaves arrive, no name on a star or a name;
(3) a slow wheel across z 1.5: no flicker, no half-faded names at rest; (4) hover right of a star, then near the right edge with
the Inspector open: flips left, clear of the panel; (5) hover near the top under the chip: clamped below it; (6) offline demo:
"unknown" for both costs, no 0; (7) demo-250 usage: "N uses, last D" and "never seen in N days"; (8) long name cut on canvas,
full in tooltip; disabled and Overlap badges; (9) emulated touch at 390: tap shows above the star, second tap opens the sheet;
(10) reduced motion: no slide, instant names; (11) Chat open + hover; Brief open + hover; (12) in cluster focus: hover a member,
canvas cost line and tooltip agree; (13) zoom while hovered: tooltip hides, returns placed afresh; (14) keyboard arrows: no
tooltip, live region reads the cost.
