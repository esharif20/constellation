# Graph app design note (ticket #8, design pass)

For the refiner: this records the design language, what was chosen and why, what was checked by eye, and what is left to polish. Screenshots in `screenshots/` use only the invented `demo.json`; never screenshot or commit the real scan.

## Stack

Vite + React + TypeScript + Tailwind v4 + shadcn/ui (radix base, `nova` preset re-themed) in `frontend/`, graph via `react-force-graph-2d` (d3-force on a canvas). `npm run build` writes to `src/constellation/static/` (gitignored); `constellation open` serves it and exits 2 with a build hint when it is missing. `base: "./"` and a relative `api/constellation` fetch keep the same build usable as a static Snapshot. All versions are pinned exactly and were at least two weeks old when added. The shadcn CLI generated components that import a brand-new `cn` package; they were repointed at the classic `@/lib/utils` (clsx + tailwind-merge).

| File | Role |
|---|---|
| `src/graph/model.ts` | API types, `buildModel` (degree, radius, clusters, sunflower seeding), `search`, arrow-key `step` |
| `src/graph/paint.ts` | every canvas pixel: dust, halos, glows, edges, star shapes, reticle, labels; `FEEL` knobs |
| `src/components/StarMap.tsx` | ForceGraph2D wiring, forces, fit, glide, keyboard stepping |
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

Node radius = 3.2 + 1.9 sqrt(degree), capped. On zoom the drawn radius grows with k until 2.5 then sublinearly, so zooming reads names rather than giant discs. Context cost is shown in the inspector as two figures (always-on, on-use) when `costs` is present; it does not yet drive size (see rough edges).

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

## Checked by eye (headless Chrome via DevTools, demo data)

- [x] rest, fitted view with atlas names (`screenshots/1-rest.jpg`)
- [x] hover fade with neighbour names (`2-hover.jpg`)
- [x] keyboard selection, inspector with cost figures and grouped Relations (`3-selected.jpg`)
- [x] search popover with kind glyphs and labels (`4-search.jpg`), choose by Enter
- [x] zoomed in: capped radii, all names (`5b-zoomed-in.jpg`)
- [x] mid-drag, neighbours following (`6-drag.jpg`)
- [x] phone bottom sheet (`9-phone-sheet.jpg`), phone rest view
- [x] empty state (`10-empty.jpg`); error state checked, not saved (it prints a local path)
- [x] warnings popover opens
- [ ] real touch gestures (pinch, tap) on a device; only emulated
- [ ] Safari and Firefox (canvas `letterSpacing` is Chrome/Safari 17+; Firefox ignores it harmlessly)

## Rough edges to polish

1. Phone: the map fits the graph's bounds, leaving empty sky above and below; consider a phone-specific fit or a tighter layout. Cluster names at phone size can still crowd.
2. Cluster names sit at a fixed fraction above the centroid; a smarter spot (largest empty area near the cluster) would avoid overlapping stars in dense regions.
3. Search previews the highlighted result only; matching Items are not otherwise lit while typing (the `matches` focus set exists but `preview` wins).
4. The canvas repaints every frame (`autoPauseRedraw={false}`) for the eased fades; pause when every fade has settled to save battery.
5. Context cost does not yet encode on the map (size or a halo ring); the inspector has room and the model already carries `cost`.
6. Bundle is a single 530 KB chunk; fine locally, worth splitting for the public Snapshot.
7. The focus ring on the map is an inset ring around the whole viewport; a ring on the active star would read better.
8. Relation hover preview and the inspector's scroll position reset are not yet checked with a screen reader.
