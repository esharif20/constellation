# Sky pattern: three quiet candidates

The #60 sky (night radial, vignette, indigo nebula, 260 dust specks in `paint.ts`) reads as depth but is flat. This note proposes one very quiet pattern on top. The graph stays the subject: no pattern pixel may outshine the faintest resting data mark.

## The budget, in numbers

Contrast of a pattern pixel against its own ground, WCAG ratio, computed from the tokens:

| Mark | on `--night-lift` (sky centre) | on `--night` |
| --- | --- | --- |
| Resting Relation edge (`--edge`, alpha 0.2) | 1.45 | 1.39 |
| **Pattern ceiling (all candidates)** | **≤ 1.25** | **≤ 1.25** |
| A graticule (`--halo-name` at 0.05) | 1.10 | 1.08 |
| B grain (`--text` at 0.05 × noise, peak about 0.04) | 1.10 | 1.07 |
| C dot centre (`--text` at 0.08, before anti-aliasing) | 1.23 | 1.20 |

Names are stroked in `--night` (labels.md 4), so their contrast does not depend on the ground: `layout:check` aaMin stays 5.44 with every candidate. Faded edges under focus (alpha about 0.01, 1.01:1) do sink below the pattern, which is the intent: dimmed things become background.

No candidate adds a colour. Each paints an existing ink token through a new alpha token (`--sky-ring`, `--sky-grain-opacity`, `--sky-dots-opacity` in `index.css`, listed in DESIGN.md "Sky background").

## A. Graticule (recommended)

A star chart's coordinate grid: 5 concentric rings at `far / 4` steps around the map origin and 12 meridians from the first ring out, so the centre stays clear.

- **Drawn:** canvas, in `paint.ts` `pre()`, after the dust and before the halos. One path, one `stroke()` per repaint (5 arcs, 12 lines), `lineWidth = 1 / k` so it is 1 screen px at any zoom. Cost is a single stroke next to about 250 sprite blits per frame, and the canvas stops repainting at rest. Not frame-timed here.
- **Zoom and pan:** world-anchored, so it moves with the map and shows its scale (rings are a quarter of the map's radius). Full strength up to 1.5× the fitted zoom, fading to nothing by 4×, where names take the screen.
- **Motion:** none. Nothing for reduced motion to turn off.
- **Phone:** the same rings, scaled with the fit; at 390px they read as a faint bullseye behind the clusters.
- **Legibility:** at 1.10:1 it sits well under the resting edges (1.45). It is the only candidate that shares the edges' form (thin lines). That is the risk, and the reason its alpha is the lowest of the three.
- **Why it wins:** it comes from the subject. The app is a star atlas, and atlases carry a graticule. It also adds information: distance from the centre becomes readable.

## B. Grain

Film grain: an SVG `feTurbulence` tile (180px, fractal noise) used as a CSS mask over a `--text` layer at opacity 0.05.

- **Drawn:** `body::before`, fixed, `z-index: -1` (above the sky gradient, under `#root`). The browser rasterises it once. Zero canvas cost.
- **Zoom and pan:** screen-fixed. It is texture, not space, so not moving is correct.
- **Motion:** static. An animated grain would cost per frame and is not proposed.
- **Phone:** identical. The tile is in CSS px, so the grain keeps its size on high-DPR screens.
- **Legibility:** peak 1.10:1, spread evenly, so it lowers no local contrast. It also breaks up the banding of the navy radial gradient on 8-bit displays, which is its practical gain.
- **Weakness:** the quietest of the three, almost invisible at 1440. It adds tooth, not interest.

## C. Dot field

A 22px lattice of 0.7px `--text` dots at opacity 0.08, masked by an ellipse so it is strongest near the centre and gone before the edges.

- **Drawn:** the same `body::before` layer. Two CSS mask layers (the dots, then the ellipse) with `mask-composite: intersect`. Zero canvas cost.
- **Zoom and pan:** screen-fixed. When the map pans, the stars slide over a still lattice. That reads as a frame, not as sky.
- **Motion:** static.
- **Phone:** the same 22px pitch, which is a tighter field on a narrow screen. Acceptable at this alpha.
- **Legibility:** peak 1.23:1, the closest to the ceiling. It was cut from 0.14, where the dots matched the edges (1.49:1). Dots at a star's scale compete with the small dashed "cost unknown" stars more than A or B do.
- **Weakness:** graph paper is a UI device, not a sky. The fade follows the screen centre, not the cluster centre.

## Recommendation

**A, the graticule.** It is the only candidate that belongs to this subject and tells you something (scale, distance from centre). It stays below the edges by a clear margin and vanishes when you zoom in to read. B is the safe fallback, or a second layer under A if the gradient banding bothers the owner.

## Viewing them

```
cd frontend && npm run build
uv run --all-extras constellation open docs/design/demo-250.json --port 8793
```

Then add `?sky=a`, `?sky=b`, `?sky=c` or `?sky=none` (the current sky) to the URL. The switch is in the shipped build, because `constellation open` serves the production bundle. It is a throwaway (`main.tsx` sets `data-sky`, `paint.ts` and `index.css` read it): once a candidate is chosen, make it unconditional and delete the switch.

Screenshots at 1440 and 390 are in `docs/design/screenshots/sky/` (`none`, `a`, `b`, `c`), on the default fitted view.

## Note on house rules

taste-skill bans gradients and grid lines on page grounds. The #60 gradient was already approved for this canvas. A is a grid by construction, and is justified here only because it is the star atlas's own device and stays at 1.10:1.
