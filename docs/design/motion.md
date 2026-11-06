# Motion: panels, modals, popovers

Owner feedback: Explain my setup, the Brief, the Inspector, Ask, What-if, History and the other panels "just pop". Cause found, not guessed:

1. The shadcn wrappers (`ui/popover.tsx`, `ui/dialog.tsx`) used `data-open:` / `data-closed:` variants. Those are base-ui attributes. Radix sets `data-state="open|closed"`, so every Radix enter and exit animation was dead code. Explain also forced `duration-0`.
2. The hand-built panels (Brief, Chat, Inspector, chips, Scrubber) had an enter keyframe but unmounted on the same frame on close, so there was no exit.

## One system

`frontend/src/lib/motion.ts` holds the numbers (ms, curves, distances, reduced-motion helper); `index.css` holds the same values as `--m-*` tokens and the `[data-pane]` keyframes; `components/Motion.tsx` has `Presence` and `Pane`. `npm run motion:check` fails if the CSS and the module drift apart.

| Role | Enter | Exit | Movement |
|---|---|---|---|
| Panel (left, right, chips) | 220 ms ease-out | 160 ms ease-in | left from -14px, right from +14px, chips 8px; phone sheets rise 24px |
| Modal (Explain) | 200 ms ease-out | 140 ms ease-in | scale 0.98 to 1; phone full-screen rises 24px |
| Popover (cluster picker, search results, warnings, History) | 160 ms ease-out | 120 ms ease-in | scale 0.98 from the Radix anchor origin, 8px slide from its side |

Curves: `--ease-out cubic-bezier(0.16,1,0.3,1)`, `--ease-in cubic-bezier(0.7,0,0.84,0)` (unchanged). Only `transform` and `opacity` animate: no layout, no scroll jump. Reduced motion: opacity only, 100 ms, no slide or scale (CSS vars zero the offsets; Radix `--tw-enter/exit-*` are forced to rest).

## Inventory and technique

| Surface | Radix? | Technique |
|---|---|---|
| Explain my setup dialog + overlay | yes | Radix `data-[state]` + tw-animate (fixed selectors, tokens) |
| Popovers: cluster picker, search results, scan warnings, History | yes | Radix `data-[state]` + tw-animate, shared `ui/popover.tsx` |
| Brief (and its collapsed pill) | no | `Presence` + `Pane from="left"`; pill fades in with `animate-fade-in` |
| Ask panel | no | `Presence` + `Pane from="left"` |
| Cluster card | no | `Presence` + `Pane from="left" delay={300}` (waits for the camera flight, as before); replaces the `card`/`leaving`/`onGone` state |
| Inspector (and its lazy Suspense) | no | `Presence` + `Pane from="right"` |
| What-if chip, highlight chip, time-travel scrubber | no | `Presence` + `Pane` (bottom, top, bottom) |
| Hover tip, Legend fade | no | unchanged (already a short CSS fade) |

`Pane` is inert and `data-leaving` while it exits, so no click or focus lands on a panel that is going away; focus handling in the components is untouched.

## Decision: no `motion` package (evidence)

`motion@14.5.0` (16 days old) was built in with `LazyMotion` + `m` + `AnimatePresence` and worked. Atlas chunk gzip: 134.87 KB to 166.99 KB with `domAnimation` (+32.1 KB, about 24%), 165.18 KB with `domMin`. The CSS `Presence` above is +0.47 KB (Atlas) and +0.17 KB (CSS), with the same visuals. Nothing here needs shared-layout transitions or springs, so per the brief the library is not adopted. If a later feature needs them, `Pane` is the single seam to swap.

## Cost check (`npm run motion:perf`, headless Chrome, demo-250, 1440x900)

StarMap is now `memo`, and the `onCluster` callback is stable. Open then close of each panel:

| | before | after |
|---|---|---|
| Frame time p50 / p95 / max during Brief, Ask, Explain open+close | 16.7 / 16.7-16.8 / 16.8 ms | 16.7 / 16.7-16.8 / 16.8 ms |
| Frames over 20 ms | 0 (Ask once at 33 ms in one run) | 0 |
| Long tasks | 0 | 0 |
| StarMap renders per Brief or Ask open+close | 4 | 4 (2 per toggle, none while the panel animates) |
| StarMap renders for Explain, History | 0 | 0 |

Headless frames are vsync-bound, so "no worse" is the honest reading; the gain is that exits now exist and the canvas is untouched during them.

## Checks

Exit animations delay the unmount, so DOM checks treat `[data-leaving]` as already gone (`chat-cluster-check.mjs`). That check was already failing at 700 px on main (the wrapped "24 clusters" button sits under the Brief); it passes at 1440 and 390.

Mid-transition frames (animations frozen at 80-110 ms): `docs/design/screenshots/motion/`.
