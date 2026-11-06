// Obsidian-style elastic drag, pure (no DOM, runs in Node for `npm run elastic:check`). The layout's home slots never change:
// a pulled star keeps a spring offset from its home, and the offset decays to exactly zero after release.
export type Pt = { x?: number; y?: number };
export const HOPS = [1, 0.35, 0.15]; // pull share by link distance from the dragged star; 3+ hops: none
export const MATE = 0.15; // same-cluster star, falling to 0 at MATE_REACH graph units from the dragged star's home
export const MATE_REACH = 90;
export const HUB = 0.08; // the cluster's hub is always pulled at least this much
const OMEGA = 22, ZETA = 0.6; // ~10% overshoot; a 100-unit pull is within 0.1 of home in about 0.5 s
const SUB = 1 / 240; // fixed substep: same result at any frame rate

type Spring = { hx: number; hy: number; ox: number; oy: number; vx: number; vy: number; w: number };

// Pull weight of every star around `from`: link hops, plus cluster mates by closeness and the cluster hub.
export function pullWeights<N extends Pt>(from: N, linked: (n: N) => Iterable<N>, mates: N[], hub: N | undefined, hx: (n: N) => [number, number]): Map<N, number> {
  const w = new Map<N, number>([[from, 1]]);
  let ring = [from];
  for (let h = 1; h < HOPS.length; h++) {
    const next: N[] = [];
    for (const n of ring) for (const m of linked(n)) if (!w.has(m)) { w.set(m, HOPS[h]); next.push(m); }
    ring = next;
  }
  const [fx, fy] = hx(from);
  for (const m of mates) {
    const [x, y] = hx(m), k = MATE * Math.max(0, 1 - Math.hypot(x - fx, y - fy) / MATE_REACH);
    if (m !== from && k > (w.get(m) ?? 0)) w.set(m, k);
  }
  if (hub && hub !== from && (w.get(hub) ?? 0) < HUB) w.set(hub, HUB);
  for (const [n, k] of w) if (k <= 0) w.delete(n);
  return w;
}

export function createElastic<N extends Pt>() {
  const s = new Map<N, Spring>();
  let held: N | null = null, dx = 0, dy = 0;
  const home = (n: N) => s.get(n) ?? { hx: n.x!, hy: n.y! };
  return {
    home: (n: N): [number, number] => { const h = home(n); return [h.hx, h.hy]; },
    // Start pulling. A star still settling from an earlier drag keeps its original home.
    grab(n: N, weights: Map<N, number>) {
      held = n; dx = dy = 0;
      for (const [m, w] of weights) {
        const e = s.get(m);
        if (e) e.w = w; else s.set(m, { hx: m.x!, hy: m.y!, ox: 0, oy: 0, vx: 0, vy: 0, w });
      }
    },
    // The held star's own position is the pointer (force-graph sets it); the others chase w * its displacement.
    move() { if (held) { const h = s.get(held)!; dx = held.x! - h.hx; dy = held.y! - h.hy; } },
    release() {
      if (!held) return;
      const h = s.get(held)!; h.ox = held.x! - h.hx; h.oy = held.y! - h.hy; h.vx = h.vy = 0;
      held = null; dx = dy = 0;
    },
    // Advance by dt seconds; writes positions. Returns true while anything is still displaced.
    tick(dt: number): boolean {
      for (const [n, e] of s) {
        if (n === held) continue;
        const tx = e.w * dx, ty = e.w * dy;
        for (let t = Math.min(dt, 1 / 20); t > 1e-9; t -= SUB) {
          const h = Math.min(SUB, t);
          e.vx += (OMEGA * OMEGA * (tx - e.ox) - 2 * ZETA * OMEGA * e.vx) * h;
          e.vy += (OMEGA * OMEGA * (ty - e.oy) - 2 * ZETA * OMEGA * e.vy) * h;
          e.ox += e.vx * h; e.oy += e.vy * h;
        }
        if (!held && Math.hypot(e.ox, e.oy) < 0.1 && Math.hypot(e.vx, e.vy) < 1) { n.x = e.hx; n.y = e.hy; s.delete(n); continue; } // at rest: exactly home, and out of the map
        n.x = e.hx + e.ox; n.y = e.hy + e.oy;
      }
      return s.size > 0;
    },
    // How far the pair is stretched past its home distance, 0..1, for the tension line
    stretch(a: N, b: N): number {
      const p = s.get(a), q = s.get(b);
      if (!p && !q) return 0;
      const [ax, ay] = [a.x!, a.y!], [bx, by] = [b.x!, b.y!], ha = home(a), hb = home(b);
      const rest = Math.hypot(ha.hx - hb.hx, ha.hy - hb.hy);
      return Math.min(1, Math.max(0, Math.hypot(ax - bx, ay - by) - rest) / 40);
    },
    active: () => s.size > 0,
    clear() { for (const [n, e] of s) { n.x = e.hx; n.y = e.hy; } s.clear(); held = null; },
  };
}
