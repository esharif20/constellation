# Graph layout and zoom (design note for the implementer)

Builds on `ui-polish` (dc36045), not over it: keep its drag wiring (`cooldownTicks` Infinity while held, 150 after), `wake()` idle loop, `fit()` with chrome insets, and the candidate-spot cluster-name placer in `paint.ts`. Only the invented demo data may be screenshotted.

## Why it looks messy now

About half the Items have no Relations. They feel only `clusterPull` (towards a centroid that itself moves), a global `forceX/Y`, and charge -55 out to 320 units. Charge wins, so loose Items are pushed into the gaps between clusters. Halos come from a member RMS that changes every frame, and the seed uses `Math.random`, so each load gives a different picture. The fix is to **give every Item a fixed home** and let forces only tidy up around it.

## 1. Layout: two passes, both in a pure `src/graph/layout.ts` (no DOM, runs in Node)

**Pass A, cluster circles.** Merge clusters with fewer than 3 members, and Items in no cluster, into one `misc` pseudo-cluster. Each cluster gets a radius `R = 11·√m + 12` (m = members; 11 is the sunflower spacing below, 12 is padding). Lay out the circles with a small d3 simulation of about 30 nodes: `forceCollide(R + 26)` (26 graph units leaves room for a rim name at the fitted zoom), `forceX(0).strength(0.05·tall)` and `forceY(0).strength(0.05/tall)` (with `tall` as in StarMap, so the block takes the viewport's shape), 400 ticks. Seed the circles on a sunflower spiral, largest first, ordered by (size desc, name). `misc` goes last, so it lands on the rim. I chose this over d3-hierarchy `pack`: it needs no new dependency, and `pack` always makes a round blob that leaves a 16:9 screen empty at the sides.

**Pass B, Items.** Inside each circle, give each member a slot on a phyllotaxis spiral: slot i sits at `(cx + 11·√(i+0.5)·cos(i·2.39996), cy + … sin …)`. Members are ordered by (degree desc, id), so hubs take the centre and leaves sit around them. Even spacing is what makes the map look more like a graph and better aligned. Forces:

| Force | Value | Why |
|---|---|---|
| `forceX/Y` to own slot | 0.35 for degree 0, 0.08 for degree > 0 | loose Items hold their place; connected ones can let edges shape them |
| link, same cluster | contains: distance 28, strength 0.6; triggers/uses: 44, 0.3 | containment reads as tight families |
| link, across clusters | distance 120, strength 0.02 | drawn, but cannot drag clusters together |
| charge | -14, `distanceMax(40)` | only loosens a hub's own neighbourhood |
| collide | `n.r + 2.5`, strength 0.8, 2 iterations | no touching stars |
| `contain` (custom) | if `dist > R − r`, push back by `(dist − R + r)·0.5·alpha` | the halo stays honest |

Delete `clusterPull`, the global `forceX/Y` and `center`.

**Settling and seeding.** Run pass B synchronously before the first paint: alpha 1, `alphaDecay 0.0228`, `velocityDecay 0.4`, 300 ticks (a few ms at 250 Items, under 100 ms at 1000). Then give force-graph the finished positions with `warmupTicks 0`. The run is deterministic because nodes start on their slots (so `jiggle` almost never fires) and the run uses `simulation.randomSource(lcg(0x5eed))`. The intro's `born` jitter switches from `Math.random` to a hash of the id. The live sim keeps the same forces (configure it with the same `applyForces(sim, layout)` helper), using `d3AlphaDecay 0.05` and `d3VelocityDecay 0.3`. A drag reheat then settles in about ln(0.001/0.3)/ln(0.95) ≈ 110 ticks, about 1.9 s. **Drag stays as it is**: force-graph raises alphaTarget while dragging, and on release the star springs back to its slot, because slots never move.

## 2. Cluster presentation

- Halo = the pass-A circle (centre and R are fixed, not recomputed per frame). Use the same `--halo` radial gradient and cache it as one offscreen sprite drawn with `drawImage`. `misc` has no halo and no name. Its Items keep their kind colour, so nothing is lost.
- Names: keep ui-polish's placer, but generate candidates **on the rim**. Try 12 angles starting at the top (−90°, then ±30°, ±60°, …), with the text centre at `R + 6 px + h/2` outside the circle. Keep the detach check and the sticky `pick` bias.
- Size by importance: `12 + 4·clamp01((m − 3)/20)` px, Instrument Serif italic, `--halo-name` with the existing night stroke. Placement order is by m desc. At the fitted view, try names only for clusters with m ≥ 5. The rest appear from z = 1.15 or when hovered or focused. A name that finds no free spot fades out (as now), never overlaps.
- Fades: keep the 1.2 to 1.8 z fade, which the user likes. The cluster under the hovered or selected Item keeps its name at any zoom.

## 3. Zoom

- **Wheel** (mouse and trackpad pinch, which arrives as wheel + ctrlKey). Add a capture-phase, `{ passive: false }` wheel listener on the wrapper that calls `preventDefault` and `stopPropagation`, so d3-zoom's instant step never runs. Update the target with `kT = clamp(kT · exp(−deltaY · s))`, where s = 0.0015 for pixel deltas, ×33 when `deltaMode` is 1, and 0.01 with ctrlKey. Each frame, ease: `k += (kT − k)·(1 − exp(−dt/90ms))`. Keep the graph point p under the cursor fixed: `c' = p − (p − c)·k/k'`, then `centerAt(c')` and `zoom(k')`, both with 0 ms. The 90 ms tail is the inertia: one constant, with no extra momentum model. Call `wake()` while |kT − k|/k > 0.002.
- **Touch pinch and drag-pan**: leave them to d3-zoom. Direct manipulation should track 1:1.
- Limits relative to the fitted zoom: `minZoom = fitK·0.6` and `maxZoom = fitK·10`. Set them after `fit()`.
- With reduced motion, τ is 0 (jump), as `glideTo` already does.
- Zoom-to-fit on load stays as `fit()`. Fit the circles' bounds (cx ± R), not the stars, so halos and rim names are not clipped.
- Semantic levels (z = k/fitK): **z < 1.2** shows halos, cluster names, stars and hub names. **1.2 to 1.8**: cluster names fade and Items with degree ≥ 2 are named. **z > 1.8**: every visible Item is named, subject to collision, and edges go to full recessive alpha.

## 4. Performance (60 fps at 250 to 1000 Items)

- Rendering only on change already exists (`wake`/`busy`). Keep it, and add the zoom tween to `busy`.
- Culling: in `pre()`, compute the visible graph rectangle plus the largest glow radius, then skip off-screen nodes, links (by bounding box) and label candidates.
- Sprites: glow is already one sprite per colour. Halos become one sprite per cluster (above).
- Labels: when there are more than 300 candidates, bucket placed boxes into a 64 px grid so collision checks are not O(n²).
- Only if a trace shows link cost: draw all links in `pre()` as one path per kind (one `setLineDash` each), and make `linkCanvasObject` a no-op.

## 5. Verification without a human

- `docs/design/make-demo.mjs` (seeded, invented names) writes `docs/design/demo-250.json`: 250 Items, 30 clusters with Zipf-like sizes (1 to 28, including 4 singletons), 4 plugin hubs that contain 8 to 20 Items each across 1 to 3 clusters, a few triggers/uses, and about 55% of Items with no Relation.
- `frontend/scripts/layout-metrics.ts`, run with `node --experimental-strip-types` and wired as `npm run layout:check`, runs `layout.ts` on demo.json and demo-250.json at 1440×900 and 390×844, then asserts:
  1. **star overlaps** = 0 (pairs with centre distance < r_a + r_b + 1);
  2. **inside own circle** ≥ 98% (only hubs may stray);
  3. **overlapping cluster circles** = 0 (distance < R_a + R_b + 20);
  4. **cluster-name overlaps** = 0 at the fitted view, with ≥ 80% of m ≥ 5 clusters named. This requires extracting the placer into a pure `placeClusterNames(clusters, view, measure)`. Node measures text as 0.5·size·chars.
  5. **determinism**: two runs give an identical position hash.
- Screenshots (agent-browser, `uv run constellation open docs/design/demo-250.json --no-browser`) go in `docs/design/screenshots/`: the rest view at both sizes, z = 2, hovering a hub, and mid-drag. Check them by eye for wasted sky and names touching halos.

## 6. Slices, in order

1. `make-demo.mjs`, demo-250.json and the metrics script against the current layout. It should fail, which gives a baseline.
2. `layout.ts`: passes A and B, seeding, `applyForces`. StarMap uses precomputed positions; halos use fixed circles. Metrics 1, 2, 3 and 5 pass.
3. Rim candidates, size tiers, m ≥ 5 gating, the pure placer. Metric 4 passes.
4. Eased wheel zoom, limits, fitting to circle bounds.
5. Culling, halo sprites, label grid. Profile at 1000 Items (demo generator `--n 1000`).
6. Screenshots and an update to `docs/design/graph-app.md`.

**Left out**: per-cluster colour (still no hue can encode 30), pan inertia, minimap, re-layout on resize (fit only), PixiJS (only if slice 5's profile misses 60 fps), and edge bundling.
