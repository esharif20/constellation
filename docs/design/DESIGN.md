# Constellation design system (dark only)

Ticket #24. Applies to the panels, top bar, search, inspector, legend, warnings and the empty, loading and failed states. The star-atlas canvas (night sky, glow, dataviz node colours, cluster halos, edge styles) is unchanged and stays as `docs/design/graph-app.md` describes it.

## Sources (inspiration only, MIT)

- **Structure: Linear** (`~/.claude/skill-library/awesome-design-md/design-md/linear.app/DESIGN.md`). We take its surface ladder, hairlines, four-step text scale, single restrained accent, flat depth (surfaces and hairlines, almost no shadow), 4 px spacing grid and small radii.
- **Type voice: Claude** (`.../design-md/claude/DESIGN.md`). We take a serif display at weight 400 with slight negative tracking for headings, and a humanist sans for UI and body text. Its licensed faces are replaced with free ones.
- No logos, brand names or trademarks from either source appear in the app.

## Fonts (all OFL, self-hosted via Vite, so the app works offline)

| Role | Family | Package | Import (latin only) | Approx. woff2 |
|---|---|---|---|---|
| Display, cluster names, wordmark | **Newsreader** | `@fontsource/newsreader` | `latin-400.css`, `latin-400-italic.css` | ~2 x 25 KB |
| UI and body | **Inter** (variable wght) | `@fontsource-variable/inter` | `wght.css` (unicode-range, so the browser fetches only latin) | ~48 KB |
| Ids, paths, token counts, kbd | **JetBrains Mono** | `@fontsource/jetbrains-mono` | `latin-400.css` | ~21 KB |

Budget: at most 130 KB of fonts on first view, none of it in JS. Fonts load as CSS assets, so first-load JS stays at about 77.8 kB gzip. Pin exact versions that are at least two weeks old (`npm view <pkg> time`). Use `font-display: swap`, which fontsource sets by default. Do not import other weights or the static Inter files.

**Why Newsreader rather than Fraunces.** Newsreader is an editorial text and display serif in the Tiempos and Copernicus family of voices that the Claude reference uses. Its upright and italic stay calm and legible at the 12-17 px sizes the canvas draws cluster names at, and two static latin files keep it small. Fraunces has soft, wonky display axes: its italic turns curly at small sizes and competes with the atlas lettering, and the files are larger. Newsreader is wider than the current Instrument Serif, so cluster-name fitting must be checked again (see the checklist).

Stacks:
```
--font-serif-stack: "Newsreader", "Iowan Old Style", Charter, Georgia, serif;
--font-sans-stack:  "Inter Variable", -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
--font-mono-stack:  "JetBrains Mono", ui-monospace, "SF Mono", Menlo, monospace;
```
Set `font-feature-settings: "cv11", "ss01"` on `body`, and use `tabular-nums` on every number.

## Colour roles

### New raw tokens (`:root` in `frontend/src/index.css`)

| Variable | Hex | Use |
|---|---|---|
| `--surface-0` | `#010102` | deepest well (inset code, the sheet handle track) |
| `--surface-1` | `#0f1011` | panel, popover, inspector (as glass: `rgb(15 16 17 / 0.94)`) |
| `--surface-2` | `#141516` | input, stat card, outline button rest |
| `--surface-3` | `#18191a` | row and button hover, kbd, inline code |
| `--surface-4` | `#191a1b` | pressed/active row |
| `--line-1` | `#23252a` | panel border, separators, stat border |
| `--line-2` | `#34343a` | input and outline button border, kbd border, legend divider |
| `--line-3` | `#3e3e44` | hovered input/button border |
| `--text` | `#f7f8f8` | primary text, headings, values (**changed** from #e9ecf8) |
| `--text-2` | `#d0d6e0` | secondary: body copy, descriptions, legend (**changed** from #a7aecb) |
| `--text-3` | `#8a8f98` | tertiary: labels, captions, placeholders, hints (**changed** from #8a93b6) |
| `--text-4` | `#62666d` | disabled text and decorative only; **never** for readable text (3.0-3.6:1) |
| `--indigo` | `#5e6ad2` | primary button background, selected-row tint base |
| `--indigo-press` | `#5560cc` | primary button hover/pressed (see deviation) |
| `--indigo-bright` | `#828fff` | focus ring, accent text and links, active search border |
| `--indigo-tint` | `rgb(94 106 210 / 0.16)` | highlighted command item, selected row (composited on surface-1: `#1c1e30`) |
| `--warn` | `#f3c46b` | unchanged (dataviz status) |
| `--destructive` | `#ff7b7b` | unchanged |

Deviation from Linear: Linear brightens its primary button to `#828fff` on hover, but white text on `#828fff` is 2.87:1, which fails AA. We darken it to `#5560cc` instead (5.34:1). `#828fff` is used only where it is the foreground or a ring.

`#5e6ad2` is **never** used as text: it is 4.05:1 on surface-1, which fails AA for small text. Accent text uses `--indigo-bright`.

### shadcn tokens, remapped

| shadcn variable | Value |
|---|---|
| `--background` | `var(--night)` (canvas sky, unchanged) |
| `--foreground` / `--card-foreground` / `--popover-foreground` / `--secondary-foreground` / `--accent-foreground` | `var(--text)` |
| `--card` / `--popover` | `rgb(15 16 17 / 0.94)` |
| `--primary` | `var(--indigo)` |
| `--primary-foreground` | `#ffffff` |
| `--secondary` | `var(--surface-3)` |
| `--muted` | `var(--surface-2)` |
| `--muted-foreground` | `var(--text-2)` |
| `--accent` (shadcn hover surface, not the brand accent) | `var(--surface-3)` |
| `--border` | `var(--line-1)` |
| `--input` | `var(--line-2)` |
| `--ring` | `var(--indigo-bright)` |
| `--destructive` | `#ff7b7b` |

Add to `@theme inline`: `--color-surface-0..4`, `--color-line-1..3`, `--color-text-2`, `--color-text-4`, `--color-indigo`, `--color-indigo-press`, `--color-indigo-bright`, `--color-indigo-tint`, and `--font-mono: var(--font-mono-stack)`.

### Contrast (WCAG 2.x, computed; small text needs 4.5:1, UI and non-text 3:1)

Backgrounds: night `#070a17`, sky centre `#10173a`, surface-1 `#0f1011`, worst-case glass (surface-1 at 0.94 over a white star) `#1d1e1f`, surface-2 `#141516`, surface-3 `#18191a`, indigo-tint on surface-1 `#1c1e30`.

| Text | night | sky centre | s1 | glass worst | s2 | s3 | indigo-tint | Used for |
|---|---|---|---|---|---|---|---|---|
| `--text` #f7f8f8 | 18.54 | 16.37 | 17.90 | 15.69 | 17.18 | 16.55 | 15.45 | headings, values, rows |
| `--text-2` #d0d6e0 | 13.50 | 11.92 | 13.04 | 11.43 | 12.52 | 12.05 | 11.25 | body, legend, counts |
| `--text-3` #8a8f98 | 6.07 | 5.36 | 5.86 | 5.14 | 5.63 | 5.42 | 5.06 | labels, hints, placeholders |
| `--text-4` #62666d | 3.42 | 3.02 | 3.30 | 2.89 | 3.17 | 3.05 | 2.85 | disabled only (exempt) |
| `--indigo-bright` #828fff | 6.88 | 6.07 | 6.64 | 5.82 | 6.37 | 6.14 | 5.73 | accent text, focus ring |
| `--warn` #f3c46b | 12.13 | 10.72 | 11.72 | 10.27 | 11.25 | 10.83 | - | warnings (9.74 on its 10% tint `#26221a`) |
| `--destructive` #ff7b7b | 7.86 | 6.94 | 7.59 | 6.66 | 7.29 | 7.02 | - | errors |
| `--halo-name` #c9cdf0 | 12.65 | 11.18 | - | - | - | - | - | canvas cluster names |

Buttons: white on `--indigo` is 4.70, and white on `--indigo-press` is 5.34. The focus ring `#828fff` is at least 5.7:1 against every surface (3:1 needed). Kind glyph colours on surface-1 are skill 7.91, hook 9.24 and agent 9.89.

Hairlines `#23252a`/`#34343a`/`#3e3e44` reach only 1.2-1.8:1. That is fine for decorative borders, but the search input must also be identifiable without its border: the search icon (text-3, 5.4:1) and placeholder (text-3) do that, and on focus the border becomes `#828fff` (6.6:1).

## Type scale

| Token | Family | Size / line height | Weight | Tracking | Use |
|---|---|---|---|---|---|
| `wordmark` | Newsreader italic | 24px / 1 (22 on phones) | 400 | 0.01em | "Constellation" in the top bar; keep its existing glow text-shadow |
| `display` | Newsreader | 30px / 1.1 (26 on phones) | 400 | -0.01em | Item name in the inspector |
| `display-sm` | Newsreader | 26px / 1.15 | 400 | -0.005em | empty and failed titles (upright, no longer italic) |
| `cluster` | Newsreader italic | 17px / 1.25 | 400 | 0.01em | cluster name in the inspector |
| `title` | Inter | 15px / 1.3 | 600 | -0.01em | popover titles ("Scan warnings") |
| `body-lg` | Inter | 15px / 1.45 | 400 | -0.005em | Item label under the name |
| `body` | Inter | 14px / 1.55 | 400 | 0 | description, result names, relation rows, buttons (500) |
| `ui` | Inter | 13px / 1.4 | 400 / 500 | 0 | legend, top-bar counts, dl rows, warning list |
| `caption` | Inter | 12px / 1.4 | 400 | 0 | result sublabel, map hint, stat unit |
| `section` | Inter | 12px / 1.3 | 500 | 0.02em | inspector section headings and the kind line (sentence case, text-3) |
| `mono-stat` | JetBrains Mono | 20px / 1.2 | 400 | -0.01em | token counts in stat cards |
| `mono` | JetBrains Mono | 12px / 1.45 | 400 | 0 | source paths, ids, inline code, kbd (11px), counts in the legend and section headings |

Canvas (`paint.ts`, sizes unchanged): star labels use Inter at 600 (rank 0, 13px) and 450 (12px), and cluster names use Newsreader italic 400 at 12-17px with `letterSpacing 0.03em`. Both come from `--font-sans-stack` and `--font-serif-stack`, so the canvas and the DOM always share families. Inter Variable renders weight 450 exactly, where the old system stack rounded it.

## Spacing, radius, border, shadow

- **Spacing:** a 4 px grid using 4, 8, 12, 16, 24 and 32 (Tailwind 1, 2, 3, 4, 6 and 8). Panels are padded 24 on desktop and 16 on phones. Gaps are 8 between inline items, 12 between a glyph and its text in rows, and 24 between inspector sections. Top-bar insets stay at 16/24.
- **Radius:** explicit values in `@theme`, replacing the `calc(var(--radius) * n)` ladder. `--radius-sm: 4px` for kbd and inline code, `--radius-md: 6px` for buttons and rows, `--radius-lg: 8px` for inputs, the search, the warning button and stat cards, `--radius-xl: 12px` for popovers, the command palette and the inspector panel, `--radius-2xl: 16px` for the phone sheet's top corners, and `9999px` for badges only. Set `--radius: 8px`. The search and the warning button stop being pills.
- **Border:** always 1px. Panels use `--line-1`. Interactive controls use `--line-2` at rest and `--line-3` on hover.
- **Shadow:** only floating layers over the map get one, defined as `--shadow-float: 0 16px 48px rgb(0 0 0 / 0.55), inset 0 1px 0 rgb(255 255 255 / 0.04)`, for the inspector and popovers. Nothing else has a shadow; depth comes from the surface ladder.
- **Glass:** `.glass` becomes `background: var(--card); backdrop-filter: blur(16px) saturate(1.1)`. The opacity rises from 0.88 to 0.94 so text contrast holds over bright stars (the worst case is in the table).
- **Focus:** the global `:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px }` stays. Inputs use an inset style instead (below). The canvas keyboard reticle uses `ink.ring`, which becomes `#828fff`.

## Components

Every interactive component has hover, focus-visible (the 2px `--ring` outline unless stated otherwise) and disabled (`opacity: 0.5; pointer-events: none`, with text at `--text-4` where it is not inherited). Colour changes take `--t-fast`.

**Panel (inspector, popover, command list):** `.glass`, 1px `--line-1`, `--radius-xl`, `--shadow-float`. The inspector is 380px wide at `top 76 / right 16 / bottom 16`, and a bottom sheet on phones (radius 16 on the top corners, handle `h-1 w-9 bg-line-2`).

**Inspector sections:**
- Kind line: `section` style in text-3, with the glyph at a gap of 8.
- Name: `display` in text. Label: `body-lg` in text-2.
- Key/value `dl`: a `border-t` in `--line-1` with `pt-4 mt-6`. Keys are `ui` in text-3. The cluster value is `cluster` in text.
- Stat card: `bg-surface-2`, 1px `--line-1`, `--radius-lg`, `px-4 py-3`. The value is `mono-stat` in text, and the unit is `caption` in text-3. When the value is unknown, the word "unknown" is Inter italic 16px in text-3.
- Description: `body` in text-2, max 65ch. Source path: `mono` in text-3, `overflow-wrap:anywhere`.
- Relation group: a heading in `section` text-3 with its count in `mono` text-3. Each row is a ghost button: min-h 40, `--radius-md`, `px-2`, `body` in text. Hover is `bg-surface-3`, active is `bg-surface-4`, and focus-visible gets the ring. Hovering or focusing a row also previews it on the map, as now.
- Close button: ghost icon button, 36px, `--radius-md`, text-3. Hover is `bg-surface-3` with text.

**Kbd:** JetBrains Mono 11px in text-3, `bg-surface-3`, 1px `--line-2`, `--radius-sm`, `h-5 min-w-5 px-1`. It has no states (not interactive).

**Badge** (for #10, for example cost or overlap): `h-5 px-2`, `rounded-full`, `bg-surface-3`, 1px `--line-1`, Inter 12/500 in text-2. The warn tone is `text-warn bg-warn/10 border-warn/30`. Badges are not interactive; if one ever becomes a link, give it hover `border-line-3` and the ring.

**Input / search:**
- Size: h-10 (h-11 on phones, which keeps a 44px touch target), `--radius-lg`.
- Rest: `bg-surface-2` at 0.94 (glass), 1px `--line-2`. Text is `body` in text. Placeholder and the leading search icon are text-3.
- Hover: border `--line-3`.
- Focus-visible: border `--indigo-bright` plus `box-shadow: 0 0 0 3px rgb(130 143 255 / 0.25)`, with no outline offset.
- Disabled: text-4, `bg-surface-1`.
- The `/` kbd hint stays at the right.

**Button:**
- `default` (primary): `bg-indigo`, white `body` at 500, h-10, `--radius-md`, `px-4`. Hover and pressed are `bg-indigo-press`.
- `outline`: `bg-surface-2`, 1px `--line-2`, text. Hover is `bg-surface-3` with a `--line-3` border.
- `ghost`: transparent, with `bg-surface-3` on hover.
- All variants get the 2px ring on focus-visible. Disabled is 0.5 opacity.
- "Try again" in the failed state uses `outline` with `--radius-lg`, no longer a pill.

**Command palette (search results):**
- Popover as Panel above, `p-1`, matching the anchor's width.
- Item: min-h 44, `--radius-md`, `px-3`, with the glyph 12px from the text. The name is `body` 500 in text, and the sublabel is `caption` in text-3, truncated.
- Highlighted (`data-[selected=true]`, which covers both keyboard and hover): `bg-indigo-tint` with text. Replace shadcn's `bg-muted` there.
- Empty: `ui` in text-3, centred, `py-4`. Show at most 8 results, as now.
- Search keeps its "/" focus shortcut, Escape behaviour and live count.

**Legend:** this has no panel; it sits directly on the sky.
- Text is `ui` in text-2 (11.9:1 at the sky centre). Counts are `mono` 12 in text. The divider between kinds and relations is `w-px h-3.5 bg-line-2`.
- Glyph and edge-key styles are unchanged.
- It hides on phones while the inspector is open, as now. It is not interactive.

**Toast / warning:**
- Trigger: an outline-style button, h-10 (h-11 on phones), `--radius-lg`, glass, border `warn/30`, text-warn, with the triangle icon. Hover and `aria-expanded` get `bg-warn/10`, and focus-visible gets the ring (indigo, not warn).
- Popover: a Panel `w-[min(420px,100vw-2rem)]`. The title uses `title`, and the list is `ui` at 1.6 line height in text-2, capped at `max-h-[50vh]` with scrolling.
- Any future transient toast uses the same Panel at bottom centre, `ui` text, auto-dismissed after 5 s and paused on hover or focus, with a `role="status"` live region.

**Top bar:** wordmark (`wordmark`), then the count line (`ui` in text-2 with tabular numbers), then warnings and search. The map hint at bottom right is `caption` in text-3 (5.36:1 at the sky centre).

**Empty / loading / failed:**
- Loading: the pulse-star stays, with `ui` text in text-2.
- Empty and failed: titles use `display-sm`, descriptions are `body` in text-2 at max 44ch, and inline code is `mono` 12 in text on `bg-surface-3` with 1px `--line-1`, `--radius-sm` and `px-1.5`.
- Failed keeps `role="alert"` and the autofocused retry button.

## Motion

- One easing family, unchanged: `--ease-out cubic-bezier(0.16,1,0.3,1)`, `--ease-in cubic-bezier(0.7,0,0.84,0)`.
- Panels, modals and popovers have their own enter/exit pairs (`--m-panel-in/out` 220/160, `--m-modal-in/out` 200/140, `--m-pop-in/out` 160/120; ease-out in, ease-in out) and every one plays its exit. See `docs/design/motion.md`. `--t-fast 140ms` still covers colour, border and hover changes; `--t 240ms` the legend fade. Canvas motion (750 ms glide, fades) is unchanged.
- Only opacity, transform, colour, border-color and box-shadow are animated; layout properties never are.
- `prefers-reduced-motion: reduce`: hover and colour durations are 0; panels, modals and popovers fade in 100 ms with no movement. The canvas already reads `reducedMotion`.

## Implementation checklist (`frontend/`)

1. **Packages**: add `@fontsource/newsreader`, `@fontsource-variable/inter` and `@fontsource/jetbrains-mono` to `dependencies` in `package.json`, each pinned exactly to a version at least two weeks old.
2. **`src/main.tsx`**: add the imports before `./index.css`: `@fontsource-variable/inter/wght.css`, `@fontsource/newsreader/latin-400.css`, `@fontsource/newsreader/latin-400-italic.css`, `@fontsource/jetbrains-mono/latin-400.css`.
3. **`src/index.css`**:
   - Delete both Instrument Serif `@font-face` rules.
   - Set the three font stacks.
   - Add the raw tokens and remap the shadcn tokens exactly as in the tables above.
   - Add the `@theme inline` colour and font entries and the explicit radius scale.
   - Add `--shadow-float` and the new `.glass` value.
   - Set `body { font-feature-settings: "cv11","ss01" }`.
   - Keep `--night`, `--night-lift`, `--k-*`, `--edge`, `--edge-alt`, `--halo`, `--halo-name`, `--dust`, `--fade`, `--warn`, the `.glyph`/`.edge-key`/`.pulse-star` rules and the reduced-motion block exactly as they are.
4. **Delete `src/assets/fonts/`** (the two Instrument Serif woff2 files and `OFL.txt`) after grepping that nothing else references them. The fontsource packages ship their own OFL licences.
5. **`src/components/ui/`**:
   - `button.tsx`: variants as above; the default hover becomes `bg-indigo-press`, not `/80`.
   - `command.tsx`: item selected state becomes `bg-indigo-tint`, with radius md.
   - `popover.tsx`: radius xl, `shadow-[var(--shadow-float)]`, the 0.98 zoom.
   - `kbd.tsx`, `input.tsx`, `badge.tsx`: as specified.
   - `empty.tsx`: description colour text-2.
6. **`src/components/TopBar.tsx`**:
   - Wordmark size 24 (22 on phones). Search becomes `rounded-lg`, with the hover and focus styles above, keeping h-11 on phones.
   - The warnings button becomes `rounded-lg`, and the warnings list becomes text-2.
   - Result rows get name 500 and a text-3 sublabel.
7. **`src/components/Inspector.tsx`**:
   - Panel `rounded-xl` with `shadow-[var(--shadow-float)]`; keep `sm:w-[380px]`, since `PANEL` in `Atlas.tsx` must match.
   - Use the section styles above, with stats in `font-mono` and the source in `font-mono` text-3.
8. **`src/components/Legend.tsx`**: counts in `font-mono`, divider `bg-line-2`. **`States.tsx`**: upright `display-sm` titles, mono `Code`, a `rounded-lg` retry button. **`Atlas.tsx`**: hint stays text-3 (now `#8a8f98`).
9. **`src/graph/paint.ts`**:
   - **No colour literals change.** These must stay: the `--night`/`--k-*`/`--edge*`/`--halo*`/`--dust`/`--fade` reads, the star core `#fff` (line 185), the glow gradient stops 0.5/0.16/0.04/0 (line 69), and the label outline in `ink.night` (line 237).
   - `ink.text`, `ink.text2` and `ink.ring` pick up the new `--text`, `--text-2` and `--ring` automatically. That is accepted: #f7f8f8 is 18.5:1 and #d0d6e0 is 13.5:1 on the night sky, and the reticle ring is #828fff.
   - Fonts come from the CSS stacks. Two code fixes are needed. First, the cluster-name `widths` cache (line 278) and any label measurements must be cleared once `document.fonts.ready` resolves, or the canvas keeps the fallback-font widths. Second, request a repaint at that point, and call `document.fonts.load('italic 400 13px Newsreader')` early, because a font used only on the canvas is never fetched on its own.
10. **Check**:
    - `npm run lint`, `npm run build` and the tests all pass.
    - `npm run layout:check`: Newsreader is wider than Instrument Serif, so check that cluster names still fit their halos.
    - First-load JS is still about 77.8 kB gzip. List the font files in `src/constellation/static/assets` and confirm only latin files load on first view (DevTools Network) and that the total is at most 130 KB.
    - Offline: block the network and reload; every face still renders.
    - Screenshots at 1440 and 390 px of the top bar, a search with results, the inspector, warnings, empty, failed and loading, plus keyboard focus on each control.
11. **Docs**:
    - In `docs/design/graph-app.md`, replace the "Type" section's Instrument Serif lines with a pointer to this file, and update its contrast line.
    - Update `docs/plan-tracker.md` for #24 (status; the deviation: primary hover `#5560cc` instead of `#828fff`, for AA).

## Sky background (#60)

The sky stays the `--night` / `--night-lift` radial gradient, with two static layers on `body` in `index.css` (`--vignette`, `--nebula`), both derived from tokens by `color-mix` (no new colour literals):

- **Vignette:** `--surface-0` at 55% at the corners, fading to nothing by 55% of the radius. It only darkens, so name contrast on the `--night` stroke is unchanged.
- **Nebula:** removed in sky round 6. Its indigo tint sat under the Milky Way band and read as a purple cast around the graph.
- **Dust:** unchanged. The canvas already draws 260 faint dust specks with a 0.06 pan parallax (`paint.ts`), so no second dust layer was added.
- **Cost and motion:** pure CSS under the transparent canvas, painted once, nothing per frame. No new motion, so `prefers-reduced-motion` has nothing to turn off (the existing dust parallax is a pan response, not an animation).

Variants shot on demo-250 at 1440 and 390 in `docs/design/screenshots/bg/`: `o` (original), `a` (vignette only), `b` (vignette + nebula, chosen), `c` (vignette + a stronger two-lobe nebula, indigo 14% and indigo-bright 7%). `a` is nearly indistinguishable from `o`. `c` lifts the lower-left ground enough to flatten the halos. `b` reads as depth without being noticed. `layout:check` aaMin is 5.44, unchanged.

### Sky pattern (Milky Way, Sky popover)

Four image layers under the canvas (band, star dust, bright stars, grain), each rendered once per window size by `graph/sky.ts` at Rich strength. A setting change only fades a layer's opacity (`--t`, `--ease-out`; 0 under reduced motion). See `docs/design/sky-pattern.md`.

Sky-only hues, never data colours:
- `--sky-core: #f4a39a`: salmon-peach core bulge
- `--sky-rose: #c47aa6`: dusty rose, and the dust edges
- `--sky-arm: #8e93da`: lavender blue-violet arms and cool stars

Alphas at Rich:
- band glow: `--sky-band: 0.32`
- dust and the outside: `--sky-lane: 0.5`, `--sky-outside: 0.3` (`--surface-0`)
- `--sky-haze: 0.18`
- behind the graph's live screen box: `--sky-hole: 0` (band), `--sky-hole-stars: 0.6` (star dust), a CSS mask moved when the camera rests
- stars: `--sky-star: 0.5`, `--sky-anchor: 0.7`
- `--sky-grain: 0.03`
- chart rings: `--sky-ring: 0.1`, `--sky-ring-label: 0.42`; on by default (owner's pick)

Strength: Off 0, Subtle 1/1.55 opacity (the default), Rich 1. Budget at Subtle: map-area p95 1.16:1 at 1440 on `--night-lift`, under the 1.18 ceiling and the 1.45 resting edge.

**Sky popover:** a ghost icon button (telescope, 44px on phones, 40px on desktop, text-2) in the top bar after Explain. `PopoverContent` is glass, 272px wide, `p-3`, with a 16px collision gutter. Title `Sky` 13/500 with a ghost `Reset` at sm. Strength is a segmented radio group in the scope filter's style: `rounded-lg border bg-surface-2 p-0.5`, three `min-h-9` stops, selected `bg-indigo-bright/20 text-foreground`, others text-2 with `hover:bg-surface-3`, arrow keys to move. The five layers are rows (min-h 40) with a 13px text-2 label and a shadcn `Switch`, disabled and text-3 when strength is Off.
