# Sky pattern

The #60 sky (night radial, vignette, indigo nebula) reads as depth but is flat. Two candidate rounds led to this: the owner chose the deep field's Milky Way band (round 2, `?sky=b`) and asked for it to look much more like the Milky Way while staying quiet behind the graph. The result is a Milky Way background with five layers and a Sky popover to tune it.

## Art direction (round 3 research)

- Stellarium draws the Milky Way as one texture, scaled by an intensity and a separate, low saturation. So the band should be nearly neutral, with brightness doing the work and a little colour only in the core. ([Stellarium MilkyWay class](https://stellarium.org/doc/head/classMilkyWay.html))
- Procedural space renderers use a band mask along a galactic plane, multi-octave noise for star clouds, and a separate star layer ([procedural starfield](https://skills.sh/ck42bb/procedural-stars-threejs/procedural-starfield), [Godot volumetric cosmic dust](https://godotshaders.com/shader/volumetric-cosmic-dust/)). Research on interstellar dust notes that dust filaments do not look like plain Perlin noise: they are ridged and thin, not soft blobs ([MAVERICK, sculpting procedural noise](https://hal-cstb.archives-ouvertes.fr/LJK_GI_MAVERICK/hal-03762332v1)).
- Canvas starfields put the Milky Way as a denser band of whiter stars along an arc ([mathling space](https://mathling.com/art/20220207_space.html)).

Taken from that: a diagonal band with a bulge in the core; star-cloud texture from 5-octave value noise; dust lanes from ridged noise (filaments) plus a broken central rift; stars whose density follows the band and drops in the lanes; a warm core (`--k-plugin` starlight), cool arms (`--halo-name`) and an indigo outer halo; ten bright stars with a soft glow and no diffraction spikes; and a fine grain.

Fitted to the app:
- The core bulge sits in the lower left, away from the map.
- The band dims by up to 55% over the middle of the screen, where stars, names and badges are densest. That fixed ellipse at (0.56, 0.48) of the screen is a shortcut: it does not follow the map's real bounding box when you pan.
- The bright stars are kept out of that middle area.
- Constellation lines are rejected, because lines joining stars read as Relations.

## Layers and defaults

| Layer | Popover name | Default | Drawn |
| --- | --- | --- | --- |
| Band (clouds, lanes, warm core) | Milky Way band | on | deep field image |
| Star dust | Star dust | on | deep field image |
| Bright stars | Bright stars | on | deep field image |
| Chart rings (graticule from round 2) | Chart rings | **off** | canvas, map-anchored |
| Grain | Grain | on | deep field image |
| Strength | Off / Subtle / Rich | **Subtle** | multiplies every alpha (0, 1, 1.55) |

Chart rings default to off because they are lines behind the Relation lines. Strength Off restores the #60 sky exactly, including its parallax dust.

## Cost

- The deep field (`graph/sky.ts`) is rendered once per viewport size and field setting into a blob image shown by CSS on a fixed `body::before` layer. The nebula is computed at a third of CSS px and smoothed up; stars and grain are drawn at full resolution. Measured render: **about 70 ms at 1440 × 900 and about 23 ms at 390 × 844**, once. Nothing runs per frame on pan, zoom or drag. A chart-ring toggle does not re-render it (`fieldKey`).
- Chart rings: a cached `Path2D`, stroked once per repaint, 0.15 ms per frame (measured in round 2).
- The seed is fixed, so the sky is the same on every load.
- `?drift` adds a slow compositor-only wander. It is off by default and off under `prefers-reduced-motion`.

## Contrast budget (measured)

WCAG contrast against `--night-lift`, from the rendered image in the browser. "Map area" is the central ellipse where the graph sits. A resting Relation edge is 1.45.

| | All p50 | All p95 | All p99 | Map area p95 | Map area p99 |
| --- | --- | --- | --- | --- | --- |
| Subtle, 1440 | 1.05 | 1.23 | 1.40 | **1.18** | 1.30 |
| Subtle, 390 | 1.05 | 1.26 | 1.43 | 1.23 | 1.43 |
| Rich, 1440 | 1.09 | 1.42 | 1.74 | 1.32 | 1.55 |
| Rich, 390 | 1.09 | 1.49 | 1.80 | 1.42 | 1.82 |

The p99 values are star specks of 1px or less. The ten bright-star cores peak at 3.0:1 (Subtle) and 5.8:1 (Rich). At Subtle, the fields and lanes stay under the edges everywhere. Rich goes up to the edge level in the map area on phones, which is why it is not the default. `layout:check` aaMin is **5.44, unchanged**, because every name is stroked in `--night`.

## The Sky popover

`SkyControl.tsx` is a ghost telescope icon button (`aria-label` "Sky settings") in the top bar, after Explain my setup. On phones it sits beside the book icon. The popover is built from shadcn `Popover`, `Slider` and `Switch`, using glass and existing tokens only.
- **Strength** is a three-stop slider (Off, Subtle, Rich) with `aria-valuetext`.
- **Layers** are five labelled switches, disabled when strength is Off.
- **Reset** restores the defaults.

It works from the keyboard: arrow keys on the slider, Space on the switches, Esc closes. At 390px the popover keeps a 16px gutter.

Settings persist in `localStorage` (`constellation.sky.v1`). Reads and writes are wrapped in try/catch, so blocked storage means the setting lasts one visit. Stored values are validated (`parse`). `?sky=none|a|b|c|rich` remains a dev override: it wins over storage and is never saved. `npm run sky:check` covers parsing, storage failure, the override, gain and `fieldKey`, the noise, and the band geometry at 1440 and 390.

## Screenshots

`docs/design/screenshots/sky/`, on demo-250 (246 invented Items, 24 clusters, labels, badges, the Brief open):
- `none-*` (#60, before) and `subtle-*` (the default, after), at 1440 and 390
- `rich-*`
- `c-1440.png` and `c-1440-zoom.png` (chart rings on)
- `popover-1440.png` and `popover-390.png`
