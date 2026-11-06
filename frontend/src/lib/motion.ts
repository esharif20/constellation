// The one motion system for panels, modals, popovers and drawers (docs/design/motion.md).
// Pure data, no React and no imports, so `npm run motion:check` can load it under node.
// CSS owns the animation (index.css: `--m-*` durations, `--ease-*` curves, `[data-pane]` keyframes, Radix data-[state]);
// this file holds the same numbers for the code that must wait for an exit, and motion:check fails if the two drift apart.

/** Milliseconds. Enter 160-240, exit 120-180; an exit is always shorter than its enter. */
export const MS = {
  panel: { in: 220, out: 160 }, // left/right panels, phone sheets, chips (Pane)
  modal: { in: 200, out: 140 }, // centred dialogs (Radix Dialog)
  popover: { in: 160, out: 120 }, // anchored popovers (Radix Popover)
} as const;
/** Reduced motion: opacity only, a short fade, no movement. */
export const REDUCED_MS = 100;

/** Same curves as `--ease-out` / `--ease-in`. */
export const EASE = { out: "cubic-bezier(0.16, 1, 0.3, 1)", in: "cubic-bezier(0.7, 0, 0.84, 0)" } as const;

/** Slide distance in px by origin: side panels, phone sheets rising from the bottom, small chips. A centred modal scales instead. */
export const DISTANCE = { side: 14, sheet: 24, chip: 8 } as const;
export const MODAL_SCALE = 0.98;

export const reducedMotion = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

/** How long a panel stays mounted after it is told to leave: its exit plus a frame of slack. */
export const exitMs = (role: keyof typeof MS, reduced = reducedMotion()) => (reduced ? REDUCED_MS : MS[role].out) + 20;
