# Plan: Cost and Overlaps in the graph (ticket #10, canvas half)

Goal (issue #10): node size shows always-on Context cost, unknown cost is visibly distinct, Overlap Relations are drawn
as distinct links with their verdict, and the inspector shows both costs and each Overlap's reason.

Decisions that touch this ticket (`docs/plan-tracker.md`): **D11** node size = `always_on` (this ticket closes it);
**D13** `react-force-graph-2d`, d3-force on canvas, glow nodes, hover fade; **D14** Vite + React + TS; **D3** Overlap
verdicts come from the scan, this ticket only draws them. No deviation is needed.

Scope: **phase 1** (this plan) touches only `frontend/src/graph/model.ts`, `layout.ts`, `paint.ts`,
`frontend/src/components/StarMap.tsx`, `frontend/scripts/layout-metrics.ts` and the invented demo data
(`docs/design/make-demo.mjs`, `demo-250.json`, `demo.json`). It must not touch `index.css`, `TopBar`, `Inspector`,
`Legend`, `States` or `ui/*` (restyle ticket #24 is editing them). **Phase 2** (Inspector and Legend) runs after #24 merges.
New colours live only in the `PALETTE` object in `paint.ts`, each read from a CSS variable with a literal fallback, so
#24 can add the tokens later without touching the painter.

Privacy: no change. Costs and verdicts are already in the scan JSON; screenshots use the invented demos only.

## Data (what the API already serves)

`GET /api/constellation` returns `asdict(Constellation)` unchanged (`server.py` just serves the file):

- `costs: Record<id, { always_on: number | null; on_use: number | null }>`. `null` = unknown. In a real scan every
  Item has an entry; **hooks are always `null`** (`costs.py::_texts`: hook output exists only at runtime); offline
  scans have `null` wherever the count cache misses. A missing entry is treated exactly like `null`.
- `overlaps: { a_id, b_id, verdict, reason }[]`, verdict in `duplicate | wrapper | overlap | distinct`. For `wrapper`,
  `a_id` is the wrapper and `b_id` what it calls. The demos have **no** `overlaps` key today, so step 1 adds invented ones.

Demo-250 numbers today: 239 Items, 227 cost entries (12 plugins missing), 50 `null`, known `always_on` 20 to 98 tokens
(median 54, p95 96), no zeros.

## 1. Node radius from always-on cost

Area-proportional (dataviz: magnitude by area, never by radius):

```
cRef  = 95th percentile of known always_on in this scan (>= 1)   // one huge MCP server must not shrink everything
r     = clamp(RMIN, RMAX, RMAX * sqrt(always_on / cRef))         // known, including 0 -> RMIN
r     = RUNK                                                     // unknown (null or missing)
RMIN = 2.6, RMAX = 9, RUNK = 4.5   (graph units; today's degree radius spans 3.2 to 13.2)
```

- Only the floor bends proportionality (below 8% of cRef). Anything above cRef is capped at RMAX; the inspector gives the
  exact number. `degree` keeps its other jobs (slot order, label priority, search tie-break) but no longer sets `r`.
- The painter's zoom rule (`radius()`: linear to k = 2.5, then sublinear) and `FEEL.hoverScale` stay as they are.

**Layout must become cost-aware**, because a fixed `SPACING = 11` with r up to 9 would let neighbours touch. Replace the
equal-area sunflower with a weighted one (each slot claims area for its own radius):

```
a_i   = (r_i + GAP)^2,  GAP = 3                       // collide force pads r + 2.5, so GAP > 2.5
rad_i = K * sqrt(a_0 + ... + a_(i-1) + a_i / 2),  K = 1.4,  angle_i = i * 2.39996
circleRadius(rs) = K * sqrt(sum a_i) + PAD,  PAD = 12  // PAD >= RMAX, so the outermost star stays inside
```

With equal radii this is the old spiral (r = 2.6 gives 12.1 units between centres, close to today's 11). Prototyped on
demo-250 in Node: worst clear gap between two stars in the same cluster 3.1 units before any force runs, 0 pairs under 1;
uniform r = 2.6 / 4.5 / 9 give worst gaps 6.9 / 7.2 / 8.0. Circles grow about 13% in total radius, so the fitted zoom drops
a little; the name-placer thresholds must still pass (section 6). Hubs (highest degree) still take the middle.

## 2. Unknown cost, distinct from zero, not colour-only

| Cost | Fill | Outline | White core | Glow | Radius |
|---|---|---|---|---|---|
| known > 0 | kind colour | none | yes (dots) | normal | from cost |
| known 0 | kind colour | none | yes | normal | RMIN (smallest filled star) |
| unknown | **none** | kind colour, **dashed** `[2px, 2px]` screen px, 1.3 px wide | no | alpha x 0.4 | RUNK |

Fill versus hollow-dashed is the encoding, so it survives colour-blindness and greyscale; the kind hue still says the kind.
Shapes keep their outline: a hollow dot, a dashed diamond, a dashed square. A plugin is already a ring, so an unknown
plugin is a **dashed** ring that keeps its centre dot (solid ring = known). Zero is a filled star at the floor size,
never hollow. Search rings and the selection reticle are unchanged and sit outside the dashed outline. Note in the design
note: in a real scan every hook is hollow, which is true (hook cost is only known at runtime), not a bug.

## 3. Overlap Relations

Kinds drawn: `duplicate`, `wrapper`, `overlap`. `distinct` is dropped in `buildModel` (the report hides it too).

One colour for all Overlaps, so they read as a different family from the recessive Relation hairlines; verdict is carried
by pattern and width, never by hue. Colour `PALETTE.overlap = var(--overlap, #ff5fd2)` (hot magenta). Checked with the
dataviz validator against the kind colours on `--night` (`--pairs all`, dark): CVD worst dE 8.8 (vs skill blue, deutan),
normal-vision worst 18.4: passes the CVD target. (Lightness-band and chroma fails are the known, accepted ones for the
starlight kinds, see `graph-app.md`.)

| Verdict | Stroke (screen px) | Width | End mark | Rest alpha |
|---|---|---|---|---|
| duplicate | solid | 2.0 | none | 0.55 |
| wrapper | dashed `[6, 3]` | 1.5 | 5 px open arrowhead at `b` (the wrapped Item) | 0.55 |
| overlap | dotted `[1.5, 3]`, round caps | 1.2 | none | 0 (focus only) |

- **Geometry**: a quadratic arc, control point at the midpoint pushed perpendicular by 0.2 x length, bowing to the same
  side for a given (a, b) order. Relations stay straight, so an Overlap never hides under a Relation between the same pair.
- **Visibility**: at rest only the actionable verdicts (duplicate, wrapper) show, at 0.55 alpha (x 0.5 when the arc crosses
  clusters, like long Relations). `overlap` verdicts appear only when one end is focused. With an Item focused (hover,
  preview or selection), its own Overlaps go to alpha 1 and +0.5 px wider; all other Overlaps fade to 0. While a search is
  active and nothing is focused, Overlaps fade to 0. Every alpha is multiplied by `min(a.a, b.a)` so the intro still lights
  outward. No toggle in phase 1.
- **Verdict text**: for the focused Item only, each Overlap gets a 11 px label at the arc's apex ("duplicate", "wraps",
  "wrapped by", "overlaps") in `ink.text2` with the night stroke, placed through the same `fits()` boxes as Item names
  (skipped on collision, at most 8). Text wears text ink, never the magenta.
- **Clutter vs Relations**: Overlaps live outside the d3 simulation (not in `graphData.links`), so they add no link force
  and do not change `degree`, slots or the settled picture. They are painted at the end of `pre()` (below Relation lines and
  stars). Expected volume: dozens for 250 Items; at rest only duplicate and wrapper (usually under 20) show.
- **Lighting**: focusing an Item also lights its Overlap partners (added to `lit`, so they are named at rank 1), but they
  are not added to `neighbours`, so arrow-key stepping and the Relation list stay as they are.
- **Hit-testing**: none on the arcs. force-graph only hit-tests `graphData.links`, and adding Overlaps there would feed
  `forceLink`. The reason is read in the inspector by clicking either end (phase 2). Pointer areas of stars are unchanged
  (a hollow unknown star still has a full-disc hit area).

## 4. Hover and selection

- Hover / preview / select an Item: its Relations behave as today; its Overlap arcs go to full alpha with verdict text;
  partners stay lit and named; everything else fades to `--fade`.
- Selection keeps those arcs on while the pointer moves elsewhere (hover takes over, as for Relations, then returns).
- Hovering an unknown star swells it 1.3x like any star; the dashed outline stays 1.3 px (screen px, not scaled).
- Reduced motion: unchanged rules (fades snap).

## 5. Legend spec (phase 2, content only)

After #24 merges, `Legend.tsx` gains:

- **Size**: "Size = always-on tokens", three filled dots drawn at `costRadius(cRef/9)`, `costRadius(cRef/4)`,
  `costRadius(cRef)` with their token numbers (rounded) beneath, `tabular-nums`. `model.costRef` supplies cRef.
- **Unknown**: one hollow dashed dot, "cost unknown".
- **Overlaps**: three short line samples in the overlap token: solid "duplicate", dashed with arrowhead "wraps", dotted
  "overlaps (on hover)". Hidden when the scan has no Overlaps.

## 5b. Inspector spec (phase 2, content only)

- **Cost** section: "Always-on" and "On use" rows, values as `1,234 tokens` (`tabular-nums`), `null` as italic "unknown",
  never 0. For a hook, a secondary line: "Hook output is only known when it runs." For on-use unknown without
  `--count-bodies`: "Run `constellation scan --count-bodies` to measure."
- **Overlaps** section (after Relations, hidden when empty): grouped "Duplicate of", "Wraps", "Wrapped by", "Overlaps
  with". Each row: kind glyph + name as a button that glides to the other Item and previews it on hover (same as Relation
  rows), with the `reason` beneath in secondary text. Data: `model.overlapsOf.get(node)`.
- Tracker: phase 2 is a follow-up commit on #10 or its own small ticket; note it in `plan-tracker.md`.

## 6. Tests and metrics (`npm run layout:check`)

Extend `measure()` in `scripts/layout-metrics.ts`; keep every existing check and threshold.

| New check | Fails when |
|---|---|
| `inside` uses the star's edge: `dist(centre) + n.r <= cluster.r + 0.5` | below 100% |
| `starOverlaps` (existing, now with cost radii): `d < a.r + b.r + 1` | > 0 |
| `sizeRule`: known r in [RMIN, RMAX], unknown r === RUNK, and sorting known Items by cost never decreases r | any violation |
| `overlapLinks`: `model.overlaps.length` equals non-`distinct` file overlaps with both ids present | mismatch |
| `slotGap`: min clear gap between two slots (before forces) in one cluster | < GAP - 0.5 |

Run on `demo.json` and `demo-250.json` at 1440x900 and 390x844, plus once on `demo-offline.json` (all cost `null`: every
r is RUNK, layout still passes). Name-placer thresholds (desktop 80%, phone 70%) must still hold with the bigger circles;
if phone drops, tune K down to 1.3 before touching the thresholds. A small `node:assert` self-check in the script for
`costRadius` (0 -> RMIN, cRef -> RMAX, 4 x cost -> 2 x radius inside the range, null -> RUNK). UI feel (dash, arcs, verdict
labels) is checked by eye with `agent-browser` screenshots on demo data: rest, hover a duplicate end, select a wrapper,
offline file, phone.

## 7. Implementation steps (in order)

1. **Demo data** (`docs/design/make-demo.mjs`): give plugins a cost; make hooks `always_on: null` (as a real scan does);
   emit `overlaps` sorted by `(a_id, b_id)`: about 8 duplicate, 6 wrapper, 16 overlap, 6 distinct, three quarters inside a
   cluster, with invented one-line reasons. Regenerate `demo-250.json`. Hand-add 5 overlaps (one per verdict, one
   cross-cluster) to `demo.json`. Invented names only.
2. **`model.ts`**: add `Verdict`, `Overlap = { a_id; b_id; verdict; reason }` and `overlaps?: Overlap[]` to `Constellation`;
   `GOverlap = { a: GNode; b: GNode; verdict; reason; alpha: number }`; `GNode.unknown: boolean`. Export constants
   `RMIN, RMAX, RUNK` and pure `costRadius(alwaysOn: number | null | undefined, cRef: number)`. In `buildModel`: compute
   `cRef`, set `n.r` and `n.unknown` from cost (drop the degree formula), build `overlaps` (drop `distinct` and dangling
   ids) and `overlapsOf: Map<GNode, GOverlap[]>`; add `overlaps`, `overlapsOf`, `costRef` to `Model`.
3. **`layout.ts`**: `circleRadius(rs: number[])` with the weighted formula; Pass A takes `c.members.map(n => n.r)`; Pass B
   places by cumulative area (`K = 1.4`, `GAP = 3`); export `K`, `GAP`. `applyForces` is unchanged (collide and contain
   already use `n.r`). Drop the now-unused `SPACING` export, or keep it only if the metrics script still imports it.
4. **`layout-metrics.ts`**: the checks in section 6, then run `npm run layout:check` and record the new table in
   `graph-app.md`.
5. **`paint.ts`**: add `PALETTE = { overlap: t("--overlap") || "#ff5fd2" }` inside `readInk()`; in `node()` the hollow
   dashed branch for `n.unknown` (per shape) and glow alpha x 0.4 in `pre()`; in `update()` ease each `GOverlap.alpha`
   per section 3 and add focused partners to `lit`; new `overlapArc(o, ctx, k)` (quadratic arc, dash, width, wrapper
   arrowhead) called at the end of `pre()`; in `post()` verdict labels for `overlapsOf.get(f)` placed with `fits()`.
6. **`StarMap.tsx`**: nothing structural (Overlaps never enter `graphData`). Only check `fit()` still frames the bigger
   circles (it already uses `c.r`) and that `busy()` covers the Overlap fades (they set `moving` through `ease`).
7. **Look**: screenshots on demo data (list in section 6), compare against this spec, tune only `FEEL`/constants.
8. **Docs, same commit**: `graph-app.md` Encoding section (size rule, unknown, Overlap styles) and the layout table;
   `plan-tracker.md` D11 "node size from cost done (#10 phase 1)", phase 2 pending #24; closing comment on #10 says the
   Inspector/Legend half is still open.

Not in this plan: an Overlaps on/off toggle, clickable arcs, per-verdict colours, re-layout on resize.
