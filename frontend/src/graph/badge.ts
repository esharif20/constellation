// Where a cluster's health badge (#71) sits: clear of every member star, screen px, pure so badge:check can assert it.
export type Disc = { x: number; y: number; r: number };
const GAP = 4;
const clear = (cx: number, cy: number, hw: number, hh: number, ds: Disc[]) =>
  ds.every((d) => { const dx = Math.max(Math.abs(d.x - cx) - hw, 0), dy = Math.max(Math.abs(d.y - cy) - hh, 0); return dx * dx + dy * dy >= (d.r + GAP) ** 2; });
// Tries under the name, then above it, then above the topmost star; the name itself never moves.
// shortcut: the last resort ignores sideways clashes, fine because it sits above every disc's top edge.
export function badgeY(name: { x: number; y: number; h: number }, w: number, h: number, discs: Disc[]): number {
  const hw = w / 2 + 2, hh = h / 2;
  const below = name.y + name.h / 2 + 12, above = name.y - name.h / 2 - 12;
  if (clear(name.x, below, hw, hh, discs)) return below;
  if (clear(name.x, above, hw, hh, discs)) return above;
  return Math.min(above, ...discs.map((d) => d.y - d.r - GAP - hh));
}

// Progressive disclosure: zoomed out only names; the health line shows for the hovered or focused cluster, or once there is room.
export const BADGE_ROOM_Z = 1.3; // zoom (relative to the fitted view) from which every drawn name may carry its badge
export const badgeWanted = (o: { hovered: boolean; focused: boolean; z: number }) => o.hovered || o.focused || o.z >= BADGE_ROOM_Z;
