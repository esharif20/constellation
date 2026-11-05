# Sky pattern: three candidates (round 2)

The #60 sky (night radial, vignette, indigo nebula, 260 dust specks) reads as depth but is flat. Round 1 (graticule, grain, dot field, all at 1.10–1.23:1) was too subtle. This round makes the patterns clearly perceptible and more designed. The graph stays the subject: the pattern's lines and fields stay under a resting edge, and only a few tiny anchor specks go brighter.

## Budget (round 2), measured

WCAG contrast against the sky centre `--night-lift`. Line values come from the tokens. Deep field values come from the rendered image in the browser (pixel percentiles, 1440 × 900 at dpr 1).

| Mark | Contrast |
| --- | --- |
| Resting Relation edge (`--edge`, alpha 0.2), the reference | 1.45 |
| Graticule lines and ticks (`--halo-name` at 0.10) | 1.24 (was 1.10) |
| Graticule labels (`--text-3` at 0.42, 10.5px) | 1.97, legible on purpose, far below any name |
| Deep field, median pixel | 1.03 |
| Deep field, nebula core (95th percentile) | 1.32 |
| Deep field specks (99th / 99.9th percentile) | 1.48 / 1.67 |
| Deep field anchor star cores (11 points, 1.1px) | 5.6 at most |

The rule: lines and fields stay at 1.35:1 or less (under the 1.45 edges). Specks smaller than 1.5px may reach 1.7:1. Only the eleven anchors go brighter, and they are 1px, white and glintless at a distance, so they never read as a coloured Item. `layout:check` aaMin stays **5.44** because every name is stroked in `--night`. Node colours are unchanged, so Item legibility only changes where the ground lifts. At the band core (1.32) the dimmest kind ink still clears 4.5:1.

No colour literals. New alpha tokens in `index.css` (also in DESIGN.md): `--sky-ring` 0.10, `--sky-ring-label` 0.42, `--sky-nebula` 0.09, `--sky-star` 0.34, `--sky-anchor` 0.45. They paint `--halo-name`, `--text-3`, `--indigo`, `--surface-0` and `--text`.

## A. Atlas graticule (`?sky=a`)

A polar star chart, centred on the map: the centre is the pole, with 5 declination rings labelled +72° to +18° along one meridian, 12 meridians labelled 0h to 22h outside the outer ring (counter-clockwise, as on a real chart), and ticks on the outer ring every 5°, longer every 15°.

- **Drawn:** canvas `pre()`. The path is a `Path2D` built once per model (`graticulePath`) and stroked once per repaint, plus 16 short `fillText` calls. Measured: **0.15 ms per frame** for the stroke and labels on a 2880 × 1800 backing store. The canvas still stops repainting at rest.
- **Zoom and pan:** world-anchored, `lineWidth` 1 screen px. Full strength up to 1.5× the fitted zoom, gone by 4×, so close-up reading has a clean ground (see `c-1440-zoom.png`).
- **Phone:** same structure. At 390px the labels sit at the edges and the rings frame the clusters.
- **Risk:** it is lines behind lines. Meridians cross clusters at 1.24 against 1.45 for edges. That reads in the screenshots, but it is the closest call of the three.

## B. Deep field (`?sky=b`, add `&drift` for motion)

A Milky Way band from the lower left to the upper right, through the #60 nebula lobes. It has two tones: wide `--indigo` clouds and a tighter `--halo-name` core, with a broken dark lane of `--surface-0` along it. Specks are dense in the band (62%, a gaussian across it) and sparse elsewhere. There are 11 anchor stars with a faint cross glint, kept out of the screen centre. The canvas dust is switched off, because the field brings its own.

- **Drawn:** `graph/sky.ts` renders it once per viewport size (on load and on resize, debounced 250ms) into a blob image. CSS shows it on a fixed `body::before` under `#root`. **Zero per-frame cost:** no JS or canvas work on pan, zoom or drag. It is seeded, so it looks the same on every load.
- **Zoom and pan:** screen-fixed, with no parallax. It is distant sky, so not moving is correct.
- **Drift:** `&drift` adds an 18px wander over 180s, run by the compositor. It is off by default and `prefers-reduced-motion` turns it off.
- **Phone:** the band is diagonal across the narrow screen, and the density scales with the area.
- **Weakness:** it is screen-fixed, so it says nothing about the map. It is atmosphere, not information.

## C. Atlas over deep field (`?sky=c`)

A and B together: the chart lines over the band. It is the richest of the three and still under the edges everywhere except the anchors and the brightest specks. Cost is A's 0.15 ms per frame. B adds nothing per frame.

## Recommendation

**C.** The deep field gives the depth and the varied density the owner asked for. The graticule makes it a star atlas rather than a wallpaper, and it fades away when you zoom in to read. If C feels busy on the real-sized setup, use **B**. It has no per-frame cost and no lines competing with edges. Keep drift off unless the owner likes it.

Constellation lines between anchor stars were considered and rejected: lines joining stars are exactly what Relations look like, so they would read as data.

## Viewing them

```
cd frontend && npm run build
uv run --all-extras constellation open docs/design/demo-250.json --port 8793
```

Add `?sky=a`, `?sky=b`, `?sky=c` or `?sky=none` (the #60 sky) to the URL, plus `&drift` with b or c. The switch ships in the build because `constellation open` serves the production bundle. It is a throwaway: once one is chosen, make it unconditional and delete the switch (`main.tsx`, `paint.ts`, `index.css`).

Screenshots in `docs/design/screenshots/sky/`: `none`, `a`, `b`, `c` at 1440 and 390, plus `a-1440-zoom.png` and `c-1440-zoom.png` (about 2.5× zoom). They are on demo-250 (246 Items, 24 clusters, with labels, badges and the Brief open).

## House rules note

taste-skill bans gradients and grid lines on page grounds. This is an app canvas with an approved #60 gradient. The graticule is the star atlas's own device, and the clouds sit under every data mark.
