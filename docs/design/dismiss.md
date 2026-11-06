# Dismissing things

Status: built on `claude/dismiss`, 2026-11-06. Demo data only (`docs/design/demo-250.json`).

## Cause

The map is a react-force-graph canvas. d3-zoom and d3-drag swallow pointer events there before they bubble to `document`, which is where Radix listens for an outside press. So with a popover open, a click on the canvas never reached Radix and did nothing; the user had to press the trigger again.

## Fix

One stack, `src/lib/dismiss.ts` (pure, no React; `src/lib/useLayer.ts` is the hook). An open overlay registers a layer with a rank. The store listens on `window` in the capture phase, which nothing below can swallow, and only while a layer is open.

- A click closes when it begins outside the layer (content or trigger count as inside) and ends within 6 px of where it began. The end of a pan or drag closes nothing; a touch the browser takes over (`pointercancel`) closes nothing. Works the same for mouse, pen and touch (pointer events).
- Opening a transient closes the other transients ("one at a time").
- The trigger counts as inside, so pressing it while open is a plain toggle: no close-then-reopen loop.
- Escape closes the highest rank, then the most recently opened. Radix still handles Escape for its own popover and dialog (and returns focus to the trigger); the global handler in `Atlas.tsx` skips a key that was already handled.
- The map's empty-canvas click (`onBackgroundClick`, which force-graph never fires after a drag) calls `background()`, so one click both closes the overlay and still does its usual job (clear the selection, leave a cluster).
- A close caused by a click elsewhere does not pull focus back to the trigger; Escape does.
- `ui/popover.tsx` and `ui/dialog.tsx` register themselves, so every shadcn Popover and Dialog gets this with no per-use code, and `PopoverContent` has a labelled Close button (40 px on touch, 32 px with a mouse; `closeButton={false}` for the two list popovers that are menus). Exit animations are untouched: the layer only flips `open`, and Radix and `Presence` play the exit from `lib/motion.ts`.

## Rules

| Layer | Rank | Click or tap outside | Click on empty canvas | Escape | Close control |
| --- | --- | --- | --- | --- | --- |
| Explain my setup (dialog) | 40 | closes (overlay) | n/a, modal | closes, focus to trigger | X |
| Sky, History, Scan warnings (popovers) | 30 | closes | closes | closes, focus to trigger | X (new) |
| Clusters list (popover) | 30 | closes | closes | closes, focus to trigger | picking a row |
| Search results | derived from focus | closes (blur) | closes (blur) | clears the query, then blurs | none, it is a listbox |
| Ask panel | 20 | stays (clicking a star or the Inspector is the "ask about this" flow) | closes | closes, focus to Ask | X |
| Time travel scrubber | 20 | stays (a mode) | stays | closes | X |
| Inspector (docked) | 14 | stays | clears the selection | closes | X |
| Cluster card (docked) | 12 | stays | leaves the cluster outside its halo | leaves the cluster, focus to the map | Back |
| Highlight chip | 8 | stays | clears it with the selection | clears it | X on the chip |
| Brief (docked) | 5 | stays | stays | collapses, focus to its pill | X |
| What-if chip | n/a | stays | stays | stays | X (exit) |

Escape closes one layer per press, top first: popover or dialog, then Ask or the scrubber, then the Inspector, the cluster card, the highlight, and last the Brief. A click on empty canvas never collapses the Brief.

## Checks

- `npm run dismiss:check`: ordering, one-at-a-time, outside press, drag versus click, pointercancel, Escape order, listeners removed when empty.
- `npm run dismiss:browser <url>`: headless, on a built demo-250 server. Canvas click closes Sky; a drag does not; trigger toggles; History replaces Sky; Escape returns focus; X closes; a touch tap closes; a click beside Explain closes it; Ask closes on empty sky and survives a drag.
- Not covered by a real device: a real touch pan (the synthetic events do not drive force-graph; its click suppression is the same code path as the mouse drag).
