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
        const box: Box = [x - w / 2 - 6, y - h / 2, x + w / 2 + 6, y + h / 2];
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
