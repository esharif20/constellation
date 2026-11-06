// Where a cluster's name goes. Pure (no canvas), so the layout metrics script can run the same placer.
// Candidates sit on the rim of the cluster's circle, starting at the top; the first free one wins.
export type Box = [number, number, number, number]; // x0, y0, x1, y1 in screen px
export type Spot = { x: number; y: number; box: Box; crowded: number; i: number; scale: number };

export const hit = (a: Box, b: Box) => a[0] < b[2] && a[2] > b[0] && a[1] < b[3] && a[3] > b[1];
const ANGLES = [-90, -60, -120, -30, -150, 0, 180, 30, 150, 60, 120, 90].map((d) => (d * Math.PI) / 180);

type In = {
  cx: number; cy: number; r: number; // circle centre and radius on screen
  w: number; h: number; // text box
  pick: number; allowed: number; // last spot (a small bias keeps it), stars the name may touch
  W: number; H: number; top: number; bottom: number; right: number; // viewport and the chrome that covers it
  placed: Box[]; obstacles: Box[];
};

// Tries the rim at normal size first, then a second ring further out, then the same at 82% size, and takes the best.
const SCALES = [1, 0.82];
export function chooseSpot(o: In): Spot | null {
  let best: Spot | null = null, bestScore = Infinity;
  for (const [si, scale] of SCALES.entries()) {
    const w = o.w * scale, h = o.h * scale, cx = o.cx, cy = o.cy;
    const minX = 8 + w / 2, maxX = Math.max(minX, o.W - o.right - 8 - w / 2);
    const minY = o.top + h / 2 + 2, maxY = Math.max(minY, o.H - o.bottom - h / 2 - 2);
    for (const [ri, gap] of [6, 6 + h * 1.3, 6 + h * 2.6].entries()) {
      for (const [ai, a] of ANGLES.entries()) {
        const i = si * 36 + ri * 12 + ai;
        const dx = Math.cos(a) * (o.r + gap + w / 2), dy = Math.sin(a) * (o.r + gap + h / 2);
        const x = Math.min(maxX, Math.max(minX, cx + dx)), y = Math.min(maxY, Math.max(minY, cy + dy));
        if (Math.abs(x - cx - dx) + Math.abs(y - cy - dy) > Math.max(w * 0.5, 40)) continue; // not detached from its circle
        const box: Box = [x - w / 2 - 6, y - h / 2 - 3, x + w / 2 + 6, y + h / 2 + 3]; // padded 3 px above and below so stacked names never touch
        if (o.placed.some((p) => hit(box, p))) continue;
        let crowded = 0;
        for (const s of o.obstacles) if (hit(box, s)) crowded++;
        const score = crowded * 10 + ri * 3 + si * 5 + ai * 0.5 - (i === o.pick ? 2.5 : 0);
        if (crowded <= o.allowed && score < bestScore) { best = { x, y, box, crowded, i, scale }; bestScore = score; }
      }
    }
  }
  return best;
}

// Canvas Item names: at most `max` chars, one "…" (U+2026) when cut; trailing separators go so the mark sits on a word (labels.md 7).
export const cutName = (s: string, max = 22) => (s.length <= max ? s : `${s.slice(0, max - 1).replace(/[-_ .:/]+$/, "")}…`);

// Where the hover tooltip goes (labels.md 9). Anchor: the star's screen centre and radius. Pointer order right, left, above,
// below; touch order above, below, right, left (the finger covers the star and what is under it). The first side that fits
// wins, else the side with most room, clamped into bounds. Pure, so layout:check runs the same code.
export type Side = "right" | "left" | "above" | "below";
export type Bounds = { x0: number; y0: number; x1: number; y1: number };
export const TIP_GAP = 12;
export function placeTip(a: { x: number; y: number; r: number }, s: { w: number; h: number }, b: Bounds, touch: boolean): { x: number; y: number; side: Side } {
  const d = a.r + TIP_GAP, clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
  const cx = clamp(a.x - s.w / 2, b.x0, Math.max(b.x0, b.x1 - s.w)), cy = clamp(a.y - s.h / 2, b.y0, Math.max(b.y0, b.y1 - s.h));
  const at = {
    right: { x: a.x + d, y: cy, room: b.x1 - (a.x + d) - s.w },
    left: { x: a.x - d - s.w, y: cy, room: a.x - d - s.w - b.x0 },
    above: { x: cx, y: a.y - d - s.h, room: a.y - d - s.h - b.y0 },
    below: { x: cx, y: a.y + d, room: b.y1 - (a.y + d) - s.h },
  };
  const order: Side[] = touch ? ["above", "below", "right", "left"] : ["right", "left", "above", "below"];
  const side = order.find((k) => at[k].room >= 0) ?? order.reduce((p, q) => (at[q].room > at[p].room ? q : p));
  const t = at[side];
  return { x: clamp(t.x, b.x0, Math.max(b.x0, b.x1 - s.w)), y: clamp(t.y, b.y0, Math.max(b.y0, b.y1 - s.h)), side };
}

// The zoom (relative to the fitted view) at which an Item's name starts to show: hubs at the fitted view, leaves from 1.3x, and a
// heavy star (known cost at or above the scan's 90th percentile, `heavyR` in the model) rides with a degree-4 hub. Unknown cost gets no boost.
export const labelStart = (degree: number, r: number, unknown: boolean, heavyR: number) => 1.3 - Math.min(0.9, Math.max((degree - 1) * 0.15, !unknown && r >= heavyR ? 0.45 : 0));
