// Hover intent: which star's tooltip stands, given the star the canvas reports under the pointer. Pure, screen px.
// Keeps the shown star until the pointer has left its (padded) hit radius, or another star is clearly closer.
export type Spot = { x: number; y: number; r: number };
export const HIT_MIN = 9; // tiny stars still get this hit radius
export const HIT_MARGIN = 8; // the pointer must be this far outside the radius before the tooltip lets go
export const CLOSER = 0.7; // a rival wins only when its distance is under this share of the shown star's
export function hoverTarget<T>(shown: T | null, cand: T | null, p: { x: number; y: number }, at: (n: T) => Spot): T | null {
  if (!shown || cand === shown) return cand ?? shown;
  const s = at(shown), ds = Math.hypot(p.x - s.x, p.y - s.y);
  const inside = ds <= Math.max(s.r, HIT_MIN) + HIT_MARGIN;
  if (!cand) return inside ? shown : null;
  if (!inside) return cand;
  const c = at(cand);
  return Math.hypot(p.x - c.x, p.y - c.y) < CLOSER * ds ? cand : shown;
}
