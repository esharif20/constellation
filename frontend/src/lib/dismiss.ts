// The one dismiss layer stack (docs/design/dismiss.md). Plain data and functions, no React and no imports,
// so `npm run dismiss:check` can load it under node. lib/useLayer.ts is the React side.
// Why a window listener: react-force-graph's canvas (d3-zoom/d3-drag) swallows pointer events before they reach
// document, which is where Radix listens for an outside press. A capture-phase listener on window cannot be swallowed.

export type Why = "escape" | "press" | "background" | "replace";
export type Layer = {
  id: string;
  /** Closes first when high. Transient overlays (>= TRANSIENT) close before docked panels. */
  rank: number;
  /** Opening order; breaks rank ties (the later one closes first). */
  seq: number;
  close: (why: Why) => void;
  /** Elements that count as "inside" for an outside press (content and trigger). */
  inside?: () => (Element | null | undefined)[];
  /** false: a pointer press elsewhere does not close it (panels and modes that live beside the map). Default true. */
  press?: boolean;
  /** false: a click on empty canvas does not close it. Default true. */
  background?: boolean;
};

export const RANK = { dialog: 40, popover: 30, panel: 20, cluster: 12, inspector: 14, highlight: 8, brief: 5 } as const;
export const TRANSIENT = 20;
export const isTransient = (l: Layer) => l.rank >= TRANSIENT;

/** Pointer travel under which a press and release is a click, not the end of a pan or drag. */
export const SLOP = 6;
export const isTap = (down: { x: number; y: number }, up: { x: number; y: number }, slop = SLOP) => Math.hypot(up.x - down.x, up.y - down.y) <= slop;

/** Add a layer. Opening a transient replaces the other transients; they come back to be closed ("replace"). */
export function pushLayer(stack: Layer[], layer: Layer): { stack: Layer[]; replaced: Layer[] } {
  const rest = stack.filter((l) => l.id !== layer.id);
  const replaced = isTransient(layer) ? rest.filter(isTransient) : [];
  return { stack: [...rest.filter((l) => !replaced.includes(l)), layer], replaced };
}
export const removeLayer = (stack: Layer[], id: string) => stack.filter((l) => l.id !== id);

/** Escape closes this one: highest rank, then the most recently opened. */
export const escapeTarget = (stack: Layer[]) => stack.reduce<Layer | undefined>((top, l) => (!top || l.rank > top.rank || (l.rank === top.rank && l.seq > top.seq) ? l : top), undefined);

/** A completed click at a place that is outside these transients. `hit` says whether the press began inside a layer. */
export const pressTargets = (stack: Layer[], hit: (l: Layer) => boolean) => stack.filter((l) => isTransient(l) && l.press !== false && !hit(l));
/** A click on empty canvas closes every transient except the ones that opt out. */
export const backgroundTargets = (stack: Layer[]) => stack.filter((l) => isTransient(l) && l.background !== false);

// ---- the store ----
let stack: Layer[] = [];
let seq = 0;
let down: { x: number; y: number; id: number; target: EventTarget | null } | null = null;
let listening = false;

const hitOf = (target: EventTarget | null) => (l: Layer) => !!l.inside?.().some((el) => el && target instanceof Node && el.contains(target));
const onDown = (e: PointerEvent) => { down = { x: e.clientX, y: e.clientY, id: e.pointerId, target: e.target }; };
const onUp = (e: PointerEvent) => {
  const d = down;
  down = null;
  if (!d || d.id !== e.pointerId || !isTap(d, { x: e.clientX, y: e.clientY })) return; // the end of a pan or drag closes nothing
  pressTargets(stack, hitOf(d.target)).forEach((l) => l.close("press"));
};
const onCancel = () => { down = null; };
const sync = () => {
  const want = stack.length > 0;
  if (want === listening) return;
  listening = want;
  const act = want ? addEventListener : removeEventListener;
  act("pointerdown", onDown as EventListener, true);
  act("pointerup", onUp as EventListener, true);
  act("pointercancel", onCancel, true);
};

/** Register an open layer; returns the function that removes it. */
export function register(layer: Omit<Layer, "seq">): () => void {
  const r = pushLayer(stack, { ...layer, seq: ++seq });
  stack = r.stack;
  sync();
  r.replaced.forEach((l) => l.close("replace"));
  return () => { stack = removeLayer(stack, layer.id); sync(); };
}
/** Escape: close the top layer. True when one was closed (the caller then stops handling the key). */
export function escape(): boolean {
  const t = escapeTarget(stack);
  t?.close("escape");
  return !!t;
}
/** A click that reached empty canvas (called by the map's background-click, which never fires after a drag). */
export const background = () => backgroundTargets(stack).forEach((l) => l.close("background"));
