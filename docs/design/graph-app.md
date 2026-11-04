# Graph app design note (ticket #8, design pass)

For the refiner: this records the design language, what was chosen and why, what was checked by eye, and what is left to polish. Screenshots in `screenshots/` use only the invented `demo.json`; never screenshot or commit the real scan.

## Stack

Vite + React + TypeScript + Tailwind v4 + shadcn/ui (radix base, `nova` preset re-themed) in `frontend/`, graph via `react-force-graph-2d` (d3-force on a canvas). `npm run build` writes to `src/constellation/static/` (gitignored); `constellation open` serves it and exits 2 with a build hint when it is missing. `base: "./"` and a relative `api/constellation` fetch keep the same build usable as a static Snapshot. All versions are pinned exactly and were at least two weeks old when added. The shadcn CLI generated components that import a brand-new `cn` package; they were repointed at the classic `@/lib/utils` (clsx + tailwind-merge).

| File | Role |
|---|---|
| `src/graph/model.ts` | API types, `buildModel` (degree, radius, clusters, the "Other" region), `search`, arrow-key `step` |
| `src/graph/layout.ts` | pure layout: packed cluster circles, slots inside them, the forces (`applyForces`); runs in Node |
| `src/graph/names.ts` | pure cluster-name placer (`chooseSpot`), shared by the painter and the metrics script |
| `scripts/layout-metrics.ts` | `npm run layout:check`: layout and name-placement metrics on the demos (`--legacy` replays the old layout) |
| `src/graph/paint.ts` | every canvas pixel: dust, halos, glows, edges, star shapes, reticle, labels; `FEEL` knobs |
| `src/components/StarMap.tsx` | ForceGraph2D wiring, fit, glide, eased wheel zoom, idle pause, keyboard stepping |
| `src/components/Atlas.tsx` | the screen once data is loaded (lazy chunk); `App.tsx` only fetches and shows states |
| `TopBar.tsx`, `Inspector.tsx`, `Legend.tsx`, `States.tsx` | DOM chrome on shadcn primitives (Command, Popover, Button, Kbd, Empty, Separator) |
| `src/index.css` | **all tokens** (`:root`), shadcn mapping, `.glyph` kind marks |

## Direction

A star atlas at night: Items are stars, clusters are constellations named the way old celestial atlases name them, in a spaced italic serif across the sky. That one move, the atlas lettering, is where the boldness goes. Everything else (chrome, panel, legend) stays quiet glass and small sans.

## Tokens (`frontend/src/index.css` `:root`)

- Surface: indigo night `--night #070a17`, radial lift `--night-lift #10173a` behind the centre, faint parallax dust. Not neutral black: blue night makes the warm stars glow.
- Text: `--text #e9ecf8`, `--text-2 #a7aecb` (secondary, about 8:1), `--text-3 #737c9e` (tertiary, non-essential only).
- Kind colour, validated with the dataviz validator (`--pairs all`, dark, on `--night`): skill `#6fa8ff`, hook `#ff9d4d`, agent `#2fd39a` pass CVD all-pairs (worst dE 10.3) and the normal-vision floor (22.1). They fail the chart "lightness band" on purpose: luminous points on a night sky, not chart fills. A fourth hue could not clear the all-pairs floors, so the rare structural kinds share starlight `#ece4cc` and are told apart by **shape**: plugin = ring (it contains things), MCP server = diamond, connector = square. The legend, search results and inspector repeat the same glyphs (`.glyph[data-kind]`), so colour never carries identity alone.
- Edges by Relation kind: contains = solid hairline, triggers = dashed, uses = dotted; all recessive (`--edge`, `--edge-alt`). Edges of the focused Item take a gradient between the two end colours.
- Clusters (27 in the real scan, far past what colour can encode): one neutral nebula halo per cluster of 3 or more (`--halo`), plus the atlas name (`--halo-name`). No per-cluster colour.
- Warning: `--warn #f3c46b`, always with icon and text.
- Radius 12px panels, 999px pills; 4px spacing rhythm via Tailwind.

## Type

- Instrument Serif (OFL, latin subset, two 15 KB woff2, vendored in `src/assets/fonts`, `font-display: swap`): wordmark, Item name in the inspector (30px), cluster names on the canvas and in the inspector (italic), empty/error titles.
- System sans for everything else (13 to 16px; 12px only for secondary labels); `tabular-nums` on counts and token costs. No all-caps labels, no mono labels.

## Encoding

Node radius comes from always-on cost, area-proportional: `r = clamp(2.6, 9, 9 * sqrt(always_on / cRef))`, cRef = the scan's 95th percentile, so one huge MCP server cannot shrink the rest. Unknown cost (null or no entry; in a real scan every hook) is **not zero**: a hollow, dashed outline (2px dashes, 1.3px line), no white core, glow x 0.4, radius 4.5. Zero is a filled star at the floor size. A plugin ring turns dashed and keeps its centre dot. Fill versus hollow carries it, so it survives colour-blindness. On zoom the drawn radius grows with k until 2.5 then sublinearly, so zooming reads names rather than giant discs.

Overlaps (`duplicate`, `wrapper`, `overlap`; `distinct` is dropped) are quadratic arcs in one colour (`PALETTE.overlap`, magenta, outside the d3 simulation so they never move the layout). Verdict is pattern and width: duplicate solid 2px, wrapper dashed 1.5px with an open arrowhead at the wrapped Item, overlap dotted 1.2px. At rest only duplicate and wrapper show (0.55 alpha; 0.28 across clusters); `overlap` shows only when an end is focused. Focus lights that Item's arcs (+0.5px, verdict text at the apex, partners stay named) and fades the rest. Not in the app yet: the Inspector cost/Overlap content and the Legend entries (phase 2, after the #24 restyle).

## Motion language

One curve family: `--ease-out cubic-bezier(.16,1,.3,1)` for entering, `--ease-in` for leaving; durations 140 / 240 / 420 ms. `prefers-reduced-motion` zeroes CSS durations, removes the intro and makes the camera jump instead of glide.

- Intro, the single orchestrated moment: 260 warm-up ticks before the first paint (no explosion), fit to view, then stars light up outward from the centre over about 0.9 s.
- Hover: the Item and its neighbours stay lit, everything else eases to alpha 0.1 (frame-rate independent, 110 ms time constant); the hovered star swells 1.3x; neighbour names appear.
- Drag: force-graph pins the node and reheats the sim, neighbours follow on their springs, release springs it home.
- Select: 750 ms cubic glide that keeps the Item left of the panel (above the sheet on phones), a fine double reticle in the Item's own colour, panel slides in 420 ms.
- Semantic zoom, relative to the fitted zoom: cluster names fade out between 1.2x and 1.8x; hubs are named at the fitted view, leaves from about 1.3x. Labels are placed greedily by priority (focus, its neighbours, cluster names, then by degree) and skipped on collision; the top bar band is reserved.
- Search: the highlighted result previews its neighbourhood on the map before Enter.

Tuning lives in `FEEL` (paint.ts) and the force setup in StarMap.tsx.

## Interaction and access

- `/` focuses search; arrows and Enter pick a result; Escape clears, then blurs.
- The map is a focusable `role="application"`; arrow keys step to the nearest Item in that direction (60 degree cone), starting at the centre. Escape closes the inspector. Selection is announced in a polite live region.
- Inspector: non-modal on purpose (the map stays live), so it is a custom aside rather than shadcn Sheet/Drawer. Relations are grouped ("Contains", "Contained in", "Used by", ...) and each row is a button that glides to the other Item; hovering a row previews it on the map.
- Phone (640px and below): search drops under the wordmark, inspector becomes a 58dvh bottom sheet with a grab bar, legend hides while it is open, edge legend and key hint hide.
- Empty state (no Items) and error state (with the server's reason and Try again) use shadcn Empty.

## Polish pass (ui-polish)

What changed, in the order the work was prioritised. Numbers come from `demo-250.json` (239 Items, 24 clusters after merging the small ones, 56% of Items without a Relation) unless stated.

**Layout (the main complaint on a real scan).** Half the Items have no Relations, so the old force layout let them drift between clusters. Every Item now has a fixed home (`layout.ts`): cluster circles are packed first (radius from member count, a clear rim between circles for the name), then members take phyllotaxis slots inside their circle, each claiming area (r + 3)^2 so large stars get room (K = 1.45), hubs in the middle. The circle radius comes from the sum of those areas. Clusters under 3 Items and unclustered Items share one region named "Other". Forces only tidy around the homes (slot pull, same-cluster links, collide, a contain force), the layout is settled before the first paint and is deterministic (seeded, no `Math.random`). A dragged Item springs back to its slot because slots never move; hubs are pulled 0.25 so they come home too. Cross-cluster links are long and weak and drawn at 45% alpha so they stay in the background. On wide screens the packing spreads sideways, on tall ones downwards.

| `npm run layout:check` | old force layout (replica) | new slot layout |
|---|---|---|
| cluster circles that overlap or leave under 20 units (250 demo, desktop / phone) | 44 / 48 | 0 / 0 |
| Items inside their own halo | 97.5% | 100% |
| two runs give the same picture | no | yes |
| Items closer than r+r+1 | 0 | 0 |
| clusters of 5+ that get a name at the fitted view, desktop / phone | 18 of 19 / 11 of 19 | 19 of 19 / 14 of 19 |
| names touching a star or another name | 0 | 0 |

The phone ratio is 74%, below the 80% asked for desktop, so the phone threshold in the script is 70%: 24 clusters on 390 px do not all fit a 13 px name at the fitted view; the rest come in as you zoom (from z = 1.15) or when you hover one of their Items.

**Cluster names.** Candidates sit on the rim of the cluster's circle (12 angles starting at the top, three rings out, then the same at 82% size). A name that finds no spot fades out; it never sits on a star, a hub name or another name. Names ease to a new spot, keep their last spot by preference, size 13 to 17 px by member count, and only clusters of 5 or more try at the fitted view. The cluster under the hovered or selected Item keeps its name at any zoom. Names fade out between z = 1.2 and 1.8 as Item names arrive.

**Zoom.** Wheel and trackpad pinch go through our own handler (capture phase, d3-zoom never sees them): the target zoom moves with each event and the real zoom closes `1 - e^(-dt/90ms)` of the gap each frame, anchored on the cursor, with limits of 0.6x to 10x the fitted zoom. Measured: about 30 frames of smooth easing for one big wheel flick. Touch pinch and drag-pan stay with d3-zoom so they track the fingers. Reduced motion jumps.

**Phone fit.** The map is fitted to the sky the chrome leaves free (top bar, legend and inspector are measured from the DOM), the layout is taller on tall screens, and the fit follows the circles, not just the stars.

**Search.** Every match stays lit while typing and carries a ring (so it never relies on brightness alone); the highlighted result is emphasised and named; the result count is announced politely.

**Idle.** The canvas stops painting when nothing moves (0 draws in 3 s at rest, was 60 per second), wakes on hover, drag, zoom, selection and search, and rests again once every fade settles. A drag runs the simulation while held and for 150 ticks after release (about 2 s).

**Bundle.** The first load is now the app shell (`index-*.js`) only; the map, search and inspector are lazy chunks that download in parallel with the data fetch.

| gzip | before | after |
|---|---|---|
| entry JS | 176.2 kB (everything) | 77.8 kB |
| Atlas chunk (force-graph, d3, cmdk, radix) | in entry | 103.4 kB |
| Inspector chunk (loaded when idle) | in entry | 2.0 kB |
| CSS | 10.5 kB | 10.4 kB |

**Accessibility.** `--text-3` is now `#8a93b6`: 5.7:1 or better on the sky and on the panels (it was 4.2:1 on the centre glow, below AA). Other pairs checked: text 14.8+, text-2 7.9+, warn 10.7+, cluster names 11.2+. Search input and warnings button are 44 px on phones, the search has a visible 2 px focus ring, results have a label, a keyboard-focused map rings the active star instead of the viewport, reduced motion makes fades and zoom instant.

**Offline scan.** A file from `constellation scan --offline` (`demo-offline.json`) has no labels, cluster names that are the first member's name (read as words), costs that are null: those show as "unknown" in italics, never 0. The top bar says "offline scan"; the warnings popover holds the "Offline: ..." message.

## Checked by eye (headless Chrome via DevTools, demo data only)

- [x] rest, hover, selected with inspector, search with several matches lit, zoomed in, mid-drag (`1-` to `6-`)
- [x] phone rest, search, bottom sheet (`7-` to `9-`); empty state (`10-`)
- [x] offline-style file: rest, inspector, phone (`11-` to `13-`)
- [x] 250 Items: before (old force layout), after, phone, zoomed (`14-` to `17-`)
- [x] hub dragged 130 px and released: back within 5 px after about 3 s
- [ ] real touch gestures (pinch, tap) on a device; only emulated
- [ ] Safari and Firefox (canvas `letterSpacing` is Chrome/Safari 17+; Firefox ignores it harmlessly)
- [ ] screen reader pass on the Relation hover preview

## What remains

1. Culling off-screen Items and links, a label grid for more than 300 candidates, and one sprite per halo (all in `docs/plans/graph-layout.md` section 4): not done, 250 Items paint fine; profile at 1000 before building.
2. Inspector and Legend cost/Overlap content is phase 2 of #10, after #24. The phone name count on demo-250 is fragile in K (14 of 19 names at K 1.45; 13 at 1.4 or 1.5), because the greedy placer is not monotonic.
3. No re-layout on resize (the fit follows the window while the view is still fitted; the packing shape is chosen at load).
4. Cluster names at 24+ clusters on a phone: a quarter wait for zoom.
5. `playwright`-style tests for drag spring-back and the idle pause are manual scripts, not in CI.
