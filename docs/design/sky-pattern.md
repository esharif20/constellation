# Sky pattern

The #60 sky (night radial, vignette, indigo nebula) reads as depth but is flat. Two candidate rounds led to this: the owner chose the deep field's Milky Way band (round 2, `?sky=b`) and asked for it to look much more like the Milky Way while staying quiet behind the graph. The result is a Milky Way background with five layers and a Sky popover to tune it.

## Round 5: a band, not clouds (owner: round 4 "doesn't really look like the Milky Way band")

Round 4's blurred domain-warped noise made shapeless violet clouds: no band, no rift, no star texture, and the dimming assumed the graph sat in the middle of the screen. A photo reads as the Milky Way because of its geometry, so round 5 rebuilds it in one galaxy frame (u along the plane, v across) shared by every layer:

1. **Shape:** brightness is a Gaussian across a tilted axis (sigma about 12% of the short side, varying a little along it), a brighter bulge at one end and a gentle fall-off toward the other. Along-axis values (width, wobble, rift centre and depth) are sampled once into a 1-D table.
2. **Great Rift:** a dark lane running lengthwise through the band, continuous, its centre wandering and its edges ragged (fBm offset), with patchy dust and faint ridged-noise filaments around it, all masked to the band. Structure is stretched along the plane (anisotropic noise coordinates), as in a photo.
3. **Stars:** about 600k candidates at 1440, rejection-sampled from the band density (so the band shows as stellar texture even where the glow is dim), u^5 magnitudes, warm in the bulge and cooler outside, dimmed behind dust.
4. **Haze:** per-pixel cubed grain weighted by density, not a blur.
5. **Colour:** near-black navy outside, salmon core (`--sky-core`), dusty rose, lavender-blue at the edges (`--sky-arm`).

**Placement follows the graph.** `StarMap` sends the graph's screen box (node bounds through `graph2ScreenCoords`) to `skyGraph()` at most every 120 ms while the camera moves and once when it rests. That only moves a CSS radial mask on the band (to 0.22) and star dust (to 0.45) layers. At the fitted view (load, resize, reset) `placeFor()` may also move the plane to the graph's far side and the bulge to the far end, in coarse steps, so a pan never re-renders.

The renderers are pure (numbers in, RGBA out). `node scripts/sky-render.ts out.png [w] [h] [subtle|rich] [x,y,w,h]` draws them to a PNG with the contrast behind a box. That loop (8 rounds, `milkyway-lab-rich.png`) replaced guessing.

**Measured:** headless Chrome at 1440, dev build: fields and stars 130–150 ms, band 75–115 ms, as separate idle tasks (a cold first run was once 570 ms, before the JIT warmed up). At 390 they take 35–45 ms. Behind the graph (prototype, Subtle): a centred graph p95 **1.09**, a corner graph 1.00. Outside the graph the band is clearly visible (p95 1.35–1.44). aaMin **5.44, unchanged**.

**Chart rings are on by default** (owner's pick). They stay at `--sky-ring` 0.1 and read over the band without touching node contrast.

**Honest assessment:** at first glance it reads as a Milky Way band: diagonal, warm core, a dark rift along it, dense fine stars. Compared with the photo it is dimmer and less saturated on purpose, and its dust has less fine filament detail. With the graph fitted to the screen, most of the band is masked, and it shows mainly in the corners and once the reader pans.

Screenshots: `screenshots/sky/milkyway-1440.png`, `milkyway-390.png`, `milkyway-corner.png` (graph panned to the bottom right), `milkyway-lab-rich.png`.

## Round 4: realism (owner: round 3 "looks weird")

On the owner's data, round 3's ridged-noise lanes read as sharp dark cracks, the band was flat grey-violet, the core had no glow and the stars were too sparse. The owner's reference is a Milky Way photo: a diagonal band, a warm salmon-pink core, soft feathered dust clouds, thousands of fine stars densest in the band, small magenta, violet and blue hue shifts, and near-black sky around it.

### What was taken from where

- **Dust as soft domain-warped fBm, not ridges.** Each dust value is fBm of fBm, following Inigo Quilez's domain warping ([darkly fbm.wgsl, after IQ "Domain warping"](https://docs.rs/crate/darkly/latest/source/shaders/lib/fbm.wgsl)). Research on dust rendering notes that filaments do not look like plain noise, and that soft noise alone looks like cloud ([MAVERICK](https://hal-cstb.archives-ouvertes.fr/LJK_GI_MAVERICK/hal-03762332v1), [planetside forum](https://planetside.co.uk/forums/index.php?msg=272132)). So the lanes here are low-frequency, blurred twice (separable box blur, 8px), and multiplied over the glow and the star density, the way real dust dims what is behind it.
- **Dust reddens light at its edges.** In ESA's Gaia colour map, the dust lanes are the darkest and reddest areas, because dust absorbs blue light more ([Gaia's sky in colour](https://www.esa.int/ESA_Multimedia/Images/2018/05/Gaia_s_sky_in_colour), [Gaia dust map](https://esa.int/ESA_Multimedia/Images/2022/06/Gaia_map_of_interstellar_dust_in_the_Milky_Way)). Partial dust here tints the glow toward `--sky-rose`.
- **Low saturation, brightness does the work.** Stellarium scales the Milky Way by an intensity with a separate, low saturation ([Stellarium MilkyWay](https://stellarium.org/doc/head/classMilkyWay.html)). Colour is strongest only in the core.
- **Band mask, warped noise clouds and a separate star layer** is the common structure of procedural skies ([procedural starfield](https://skills.sh/ck42bb/procedural-stars-threejs/procedural-starfield), [Godot volumetric cosmic dust](https://godotshaders.com/shader/volumetric-cosmic-dust/)). Canvas versions draw the band as a denser run of whiter stars ([mathling](https://mathling.com/art/20220207_space.html)).

### How it is drawn now (`graph/sky.ts`)

Four image layers, each rendered once per window size, at Rich strength, into its own blob image on its own fixed element under `#root`. Paint order from the back: band, star dust, bright stars, grain.

1. **Band:**
   - near-black navy outside the band (`--surface-0` at up to 0.3)
   - soft dust over the band, including a broken Great Rift along the plane (`--surface-0` at up to 0.5)
   - the glow: lavender blue-violet arms (`--sky-arm`), dusty rose (`--sky-rose`) shifting slowly along them, and a salmon-peach core bulge (`--sky-core`), placed in the lower left, away from the graph
   - an unresolved-star haze: per-pixel cubed noise at device resolution, weighted by the glow, which is what makes the core read milky

   Glow and dust are computed on a quarter-resolution grid and smoothed up.
2. **Star dust:** about 29,000 candidates at 1440. Brightness follows a power law (u^4.5), so most stars are faint and few are bright. Density follows the band and is thinned 75% by dust. About 10% of stars are warm and 18% cool.
3. **Bright stars:** twelve, with a soft halo and no diffraction spikes, kept out of the graph area.
4. **Grain:** a 128px tile of device-pixel specks.

The band dims by up to **65%** over the middle of the screen (stronger than round 3's 55%, to hold the ceiling). The haze thins twice there.

Chart rings stay on the canvas (a cached `Path2D`) and now fade in and out too (eased alpha, instant under reduced motion).

## No re-render on a setting change

- Strength and the layer switches only set each layer element's `opacity`. The layers are rendered at Rich, so Subtle is opacity 1/1.55 (0.645) and Off is 0. CSS fades the change with `transition: opacity var(--t) var(--ease-out)` (240ms, 0 under reduced motion).
- `apply()` is the only `onSky` handler for the image layers, and it never calls a renderer. `sky:check` asserts this in the source and asserts `layerOpacity`. The render key is the window size alone (`sizeKey`).
- Rendering is progressive. Grain renders on start, stars and bright stars at the first idle moment (`requestIdleCallback`), the band at the next one, each as its own task. All layers are pre-warmed, so turning one on later is instant.
- **Measured** at 1440, demo-250, headless Chrome:
  - a switch click handler takes **1.1 ms** in total (React update included); `apply()` reads 0 ms
  - during the 240ms fade, 38 frames with the longest at **16.7 ms**: no dropped frames
  - one-off renders: stars and fields about **100–125 ms**, band about **70 ms**, as separate idle tasks; at 390, 31 and 25 ms
- Sky state lives in `skySettings.ts`, outside React. A change re-renders only the memoised popover, never the Atlas or the map.

## Contrast budget (measured, all layers composited)

WCAG contrast against `--night-lift`. "Map" is the central ellipse where the graph sits. A resting Relation edge is 1.45.

| | All p50 | All p95 | All p99 | Map p95 | Map p99 |
| --- | --- | --- | --- | --- | --- |
| Subtle, 1440 | 1.01 | 1.20 | 1.39 | **1.16** | 1.36 |
| Subtle, 390 | 1.00 | 1.11 | 1.17 | **1.09** | 1.12 |
| Rich, 1440 | 1.02 | 1.35 | 1.73 | 1.28 | 1.67 |
| Rich, 390 | 1.01 | 1.18 | 1.30 | 1.14 | 1.21 |

Subtle holds the 1.18 ceiling behind the graph. The p99 values are single stars and haze grains. The darkening outside the band only lowers the ground, which raises node contrast. aaMin is **5.44, unchanged**, because every name is stroked in `--night`.

New hue tokens (in `index.css` and DESIGN.md): `--sky-core #f4a39a`, `--sky-rose #c47aa6`, `--sky-arm #8e93da`. They are used only by the sky, never as data colours.

## The Sky popover

`SkyControl.tsx` is a ghost telescope icon button (`aria-label` "Sky settings") in the top bar. The popover uses glass and a 16px collision gutter.
- **Strength** is now a segmented radio group (Off, Subtle, Rich) in the scope filter's look, replacing the slider. Arrow keys move and select, the selected stop takes the tab stop, and it is labelled "Strength".
- **Layers** are switches for Milky Way band, Star dust, Bright stars, Chart rings and Grain.
- **Reset** restores the defaults: Subtle, chart rings off, everything else on.

Settings persist in `localStorage` (`constellation.sky.v1`), wrapped in try/catch and validated. `?sky=none|a|b|c|rich` remains a dev override that is never saved. `?drift` is an opt-in slow wander, off under reduced motion.

## Honest assessment against the reference photo

It now reads as a Milky Way: a diagonal band, a warm rose core with soft dust cutting it, a milky grain in the core, and denser stars along the band. It is a quiet version of the photo, deliberately. The photo's core is far brighter and more saturated, and its dust has more fine structure. At Subtle on a phone the band is barely visible behind the graph, which fills the screen. The core sits in the lower left, so a wide Brief panel covers part of it.

## Screenshots

`docs/design/screenshots/sky/`, on demo-250 (invented data):
- `none-*` (before) and `subtle-*` (after, the default), at 1440 and 390
- `rich-*`
- `c-1440.png` and `c-1440-zoom.png` (chart rings on)
- `popover-1440.png` and `popover-390.png`
