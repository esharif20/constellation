// Layout without a DOM (it runs in Node for the metrics script). Every Item gets a fixed home, so the picture is the
// same on every load and a dragged Item has somewhere to spring back to. Forces only tidy up around the homes.
//   Pass A: each cluster is a circle (radius from its member count); the circles are packed so none overlap.
//   Pass B: the members take evenly spaced slots on a phyllotaxis spiral inside their circle, hubs in the middle.
import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, type ForceLink } from "d3-force";

export const K = 1.45; // (1.3 broke the slot-gap check; the phone name count is not monotonic in K: 1.35 and 1.45 pass, 1.4 and 1.5 do not) sunflower spacing: a slot at cumulative area A sits K * sqrt(A) from the centre
export const GAP = 3; // clear space each star claims around itself (collide pads r + 2.5, so GAP is more)
export const RIM = 26; // clear space between two circles, room for a cluster name at the fitted zoom
const PAD = 12;
// Each slot claims the area (r + GAP)^2, so a circle holding big stars grows and equal stars give the old even spiral.
const area = (r: number) => (r + GAP) ** 2;
export const circleRadius = (rs: number[]) => K * Math.sqrt(rs.reduce((s, r) => s + area(r), 0)) + PAD;

export type LNode = { id: string; degree: number; r: number; cluster?: LCluster; x?: number; y?: number; vx?: number; vy?: number; sx: number; sy: number };
export type LCluster = { name: string; members: LNode[]; x: number; y: number; r: number; mx: number; my: number; fr: number }; // mx, my, fr: mean member position and farthest reach at rest
export type LLink = { source: LNode; target: LNode; kind: string };

// small deterministic random source (so two runs give the same picture)
export function lcg(seed: number) {
  let s = seed >>> 0;
  return () => (s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 4294967296;
}

type Setter = (name: string, force: unknown) => void;

// The forces both the up-front settle and the live simulation use. `link` is the simulation's own link force.
export function applyForces(link: ForceLink<LNode, LLink>, set: Setter) {
  const same = (l: LLink) => !!l.source.cluster && l.source.cluster === l.target.cluster;
  link
    .distance((l) => (!same(l) ? 120 : l.kind === "contains" ? 28 : 44))
    .strength((l) => (!same(l) ? 0.02 : l.kind === "contains" ? 0.6 : 0.3));
  set("charge", forceManyBody<LNode>().strength(-14).distanceMax(40));
  set("collide", forceCollide<LNode>((n) => n.r + 2.5).strength(0.8).iterations(2));
  set("x", forceX<LNode>((n) => n.sx).strength((n) => (n.degree > 0 ? 0.25 : 0.35)));
  set("y", forceY<LNode>((n) => n.sy).strength((n) => (n.degree > 0 ? 0.25 : 0.35)));
  // keep every Item inside its own halo
  let nodes: LNode[] = [];
  const contain = (alpha: number) => {
    for (const n of nodes) {
      const c = n.cluster;
      if (!c) continue;
      const dx = n.x! - c.x, dy = n.y! - c.y, d = Math.hypot(dx, dy), limit = c.r - n.r;
      if (d > limit && d > 0) { const k = ((d - limit) * 0.5 * alpha) / d; n.vx! -= dx * k; n.vy! -= dy * k; }
    }
  };
  contain.initialize = (ns: LNode[]) => (nodes = ns);
  set("contain", contain);
}

// Where a cluster's halo belongs now: its home circle moved by how far the members' mean has moved from rest, and widened
// (up to 1.4x) when a member is dragged out. At rest this is exactly (c.x, c.y, c.r).
const reach = (c: LCluster, x: number, y: number) => Math.max(...c.members.map((m) => Math.hypot(m.x! - x, m.y! - y) + m.r));
export function haloOf(c: LCluster) {
  const n = c.members.length;
  let mx = 0, my = 0;
  for (const m of c.members) { mx += m.x!; my += m.y!; }
  const x = c.x + mx / n - c.mx, y = c.y + my / n - c.my;
  return { x, y, r: Math.max(c.r, Math.min(1.4 * c.r, c.r + reach(c, x, y) - c.fr)) };
}

// Sets x, y, sx, sy on every node and x, y, r, mx, my on every cluster. `tall` is the viewport's height over width, clamped to 1..2.
export function layout(nodes: LNode[], links: LLink[], clusters: LCluster[], tall: number) {
  // Pass A: circles, largest first (ties by name), the catch-all last so it lands on the rim
  const rand = lcg(0x5eed);
  type Disc = { c: LCluster; x: number; y: number; R: number };
  const order = [...clusters].sort((a, b) => (a.name === "Other" ? 1 : b.name === "Other" ? -1 : b.members.length - a.members.length || a.name.localeCompare(b.name)));
  const discs: Disc[] = order.map((c, k) => {
    const R = circleRadius(c.members.map((n) => n.r)), t = k * 2.39996, d = 70 * Math.sqrt(k + 0.5);
    return { c, R, x: (Math.cos(t) * d) / Math.sqrt(tall), y: Math.sin(t) * d * Math.sqrt(tall) };
  });
  const pack = forceSimulation(discs)
    .stop()
    .randomSource(rand)
    .alphaDecay(0.01)
    .force("x", forceX<Disc>(0).strength(0.05 * tall))
    .force("y", forceY<Disc>(0).strength(0.05 / tall))
    // a phone shows the map small, so its names need more room around each circle
    .force("collide", forceCollide<Disc>((d) => d.R + (tall > 1.2 ? RIM * 1.7 : RIM) / 2).strength(1).iterations(4));
  for (let i = 0; i < 400; i++) pack.tick();

  // Pass B: slots on a spiral inside each circle, each claiming area for its own radius; hubs (most Relations) first, so they take the middle
  for (const d of discs) {
    d.c.x = d.x; d.c.y = d.y; d.c.r = d.R;
    let used = 0; // area claimed by the slots so far
    [...d.c.members].sort((a, b) => b.degree - a.degree || a.id.localeCompare(b.id)).forEach((n, i) => {
      const t = i * 2.39996, rad = K * Math.sqrt(used + area(n.r) / 2);
      used += area(n.r);
      n.sx = n.x = d.x + Math.cos(t) * rad;
      n.sy = n.y = d.y + Math.sin(t) * rad;
      n.vx = n.vy = 0;
    });
  }
  // settle: same forces as the live simulation, run before the first paint
  const sim = forceSimulation(nodes).stop().randomSource(rand).alphaDecay(0.0228).velocityDecay(0.4);
  const link = forceLink<LNode, LLink>(links);
  sim.force("link", link);
  applyForces(link, (name, f) => sim.force(name, f as never));
  for (let i = 0; i < 300; i++) sim.tick();
  for (const c of clusters) {
    c.mx = c.members.reduce((t, m) => t + m.x!, 0) / c.members.length;
    c.my = c.members.reduce((t, m) => t + m.y!, 0) / c.members.length;
    c.fr = reach(c, c.x, c.y);
  }
}
