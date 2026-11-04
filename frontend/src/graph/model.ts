// The Constellation as the API serves it (GET /api/constellation), and the graph model the canvas draws.
import { forceCollide, forceSimulation, forceX, forceY } from "d3-force";

export type Item = { id: string; kind: string; name: string; description: string; source: string };
export type Relation = { source: string; target: string; kind: string };
export type Cost = { always_on: number | null; on_use: number | null };
export type Constellation = {
  items: Item[];
  relations?: Relation[];
  labels?: Record<string, string>;
  clusters?: { name: string; item_ids: string[] }[];
  warnings?: string[];
  costs?: Record<string, Cost>;
};

export type Shape = "dot" | "ring" | "diamond" | "square";
export type GNode = Item & {
  label: string;
  shape: Shape;
  degree: number;
  r: number;
  cluster?: Cluster;
  cost?: Cost;
  // simulation and animation state, mutated in place each frame (never React state)
  x?: number; y?: number; vx?: number; vy?: number; fx?: number; fy?: number;
  a: number; s: number; born: number;
  sx: number; sy: number; // the slot the layout assigns: a tidy spot in its cluster that the force pulls it back to
};
export type GLink = { source: GNode; target: GNode; kind: string; a: number; hot: boolean };
// la/lx/ly/pick: the cluster name's eased alpha, its position in graph units, and which candidate spot it last took (see paint.ts)
export type Cluster = { name: string; members: GNode[]; x: number; y: number; r: number; a: number; la: number; lx: number; ly: number; pick: number };
export type Model = { nodes: GNode[]; links: GLink[]; clusters: Cluster[]; neighbours: Map<GNode, Set<GNode>>; warnings: string[]; offline: boolean };

const KIND_NAME: Record<string, string> = { skill: "Skill", hook: "Hook", agent: "Agent", plugin: "Plugin", mcp_server: "MCP server", connector: "Connector" };
export const kindName = (k: string) => KIND_NAME[k] ?? k.replace(/_/g, " ");

const SHAPE: Record<string, Shape> = { plugin: "ring", mcp_server: "diamond", connector: "square" }; // structural kinds share one colour, so shape carries identity

const REL_NAME: Record<string, [string, string]> = {
  contains: ["Contains", "Contained in"],
  triggers: ["Triggers", "Triggered by"],
  uses: ["Uses", "Used by"],
  duplicates: ["Duplicates", "Duplicated by"],
  wraps: ["Wraps", "Wrapped by"],
};
export const relName = (kind: string, out: boolean) => (REL_NAME[kind] ?? [kind, `${kind} (from)`])[out ? 0 : 1];

// Without labels (an offline scan) a cluster is named after its first Item, which is often kebab-case: read it as words.
const tidy = (s: string) => s.replace(/[-_]+/g, " ");

// `aspect` is the viewport's height over width: tall (phone) screens seed a taller layout so the map fills them.
export function buildModel(data: Constellation, aspect = 1): Model {
  const labels = data.labels ?? {}, costs = data.costs ?? {}, labelled = Object.keys(labels).length > 0;
  const tall = Math.max(1, Math.min(2, aspect));
  const byId = new Map<string, GNode>();
  const nodes = data.items.map((it) => {
    const n: GNode = { ...it, label: labels[it.id] ?? "", shape: SHAPE[it.kind] ?? "dot", degree: 0, r: 0, cost: costs[it.id], a: 0, s: 1, born: 0, sx: 0, sy: 0 };
    byId.set(n.id, n);
    return n;
  });
  const clusters: Cluster[] = (data.clusters ?? [])
    .map((c) => ({ name: labelled ? c.name : tidy(c.name), members: c.item_ids.flatMap((id) => byId.get(id) ?? []), x: 0, y: 0, r: 0, a: 0, la: 0, lx: 0, ly: 0, pick: 0 }))
    .filter((c) => c.members.length);
  clusters.forEach((c) => c.members.forEach((n) => (n.cluster = c)));
  const neighbours = new Map(nodes.map((n) => [n, new Set<GNode>()]));
  const links: GLink[] = (data.relations ?? []).flatMap((r) => {
    const source = byId.get(r.source), target = byId.get(r.target);
    if (!source || !target) return [];
    neighbours.get(source)!.add(target);
    neighbours.get(target)!.add(source);
    return [{ source, target, kind: r.kind, a: 0, hot: false }];
  });
  for (const n of nodes) {
    n.degree = neighbours.get(n)!.size;
    n.r = 3.2 + Math.min(10, Math.sqrt(n.degree) * 1.9);
  }
  placeSlots(nodes, clusters, tall);
  return { nodes, links, clusters, neighbours, warnings: data.warnings ?? [], offline: (data.warnings ?? []).some((w) => w.startsWith("Offline")) };
}

// Search rank: name prefix, then name substring, then label substring; hubs first within a rank.
export function search(nodes: GNode[], query: string): GNode[] {
  const s = query.trim().toLowerCase();
  if (!s) return [];
  return nodes
    .flatMap((n) => {
      const i = n.name.toLowerCase().indexOf(s);
      const rank = i === 0 ? 0 : i > 0 ? 1 : n.label.toLowerCase().includes(s) ? 2 : -1;
      return rank < 0 ? [] : [[rank, n] as const];
    })
    .sort((a, b) => a[0] - b[0] || b[1].degree - a[1].degree)
    .map(([, n]) => n);
}

// Arrow-key step: the nearest Item inside a cone around the pressed direction.
export function step(nodes: GNode[], from: GNode, dx: number, dy: number): GNode | undefined {
  let best: GNode | undefined, bestScore = Infinity;
  for (const n of nodes) {
    if (n === from) continue;
    const vx = n.x! - from.x!, vy = n.y! - from.y!;
    const along = vx * dx + vy * dy, across = Math.abs(vx * dy - vy * dx);
    if (along <= 0 || across > along * 1.7) continue;
    const score = along + across * 2;
    if (score < bestScore) { best = n; bestScore = score; }
  }
  return best;
}

// Layout, step 1 of 2 (the force sim in StarMap is step 2). Every cluster is laid out on its own: its hub (an Item with
// Relations) in the middle, its Items with Relations on the first ring around it, the rest on further rings. Then the
// clusters are packed as circles so they never overlap and always leave a gap for their names. Items in no cluster form
// one more group. A force then pulls each Item back to its slot, which is what makes a dragged Item spring home.
const PITCH = 17; // ring spacing and Item spacing along a ring
const GAP = 40; // clear space between two clusters (room for a name)

function ringLayout(members: GNode[]): { slots: [number, number][]; radius: number } {
  const order = [...members].sort((a, b) => b.degree - a.degree);
  const hubs = order.filter((n) => n.degree >= 3).slice(0, 3), rest = order.filter((n) => !hubs.includes(n));
  const slots = new Map<GNode, [number, number]>();
  let inner = 0;
  if (hubs.length === 1) {
    slots.set(hubs[0], [0, 0]);
    inner = 24;
  } else if (hubs.length > 1) {
    const r = Math.max(22, (hubs.length * PITCH) / (2 * Math.PI) + 10);
    hubs.forEach((h, i) => slots.set(h, [Math.cos((i / hubs.length) * 2 * Math.PI) * r, Math.sin((i / hubs.length) * 2 * Math.PI) * r]));
    inner = r + 22;
  }
  let i = 0, ring = 0, radius = inner;
  while (i < rest.length) {
    radius = Math.max(inner, 13) + ring * PITCH;
    const cap = Math.max(1, Math.floor((2 * Math.PI * radius) / PITCH)), take = Math.min(cap, rest.length - i);
    for (let j = 0; j < take; j++) {
      const t = (j / take) * 2 * Math.PI + ring * 0.6;
      slots.set(rest[i + j], [Math.cos(t) * radius, Math.sin(t) * radius]);
    }
    i += take;
    ring++;
  }
  return { slots: members.map((n) => slots.get(n)!), radius: radius + 14 };
}

function placeSlots(nodes: GNode[], clusters: Cluster[], tall: number) {
  const groups = clusters.map((c) => c.members);
  const loose = nodes.filter((n) => !n.cluster);
  if (loose.length) groups.push(loose);
  const laid = groups.map((g) => ({ g, ...ringLayout(g) }));
  // pack: a small force sim on the cluster centres, pulled gently to the middle (harder across on a tall screen)
  const order = laid.map((l, i) => ({ i, r: l.radius })).sort((a, b) => b.r - a.r);
  const centres = laid.map(() => ({ x: 0, y: 0, r: 0 }));
  order.forEach(({ i, r }, k) => {
    const t = k * 2.39996, d = 55 * Math.sqrt(k + 0.5) * 1.4;
    centres[i] = { x: (Math.cos(t) * d) / Math.sqrt(tall), y: Math.sin(t) * d * Math.sqrt(tall), r };
  });
  const sim = forceSimulation(centres)
    .stop()
    .alphaDecay(0.01)
    .velocityDecay(0.5)
    .force("x", forceX<{ x: number; y: number; r: number }>().strength(0.04 * tall))
    .force("y", forceY<{ x: number; y: number; r: number }>().strength(0.04 / tall))
    .force("collide", forceCollide<{ x: number; y: number; r: number }>((c) => c.r + GAP / 2).strength(1).iterations(4));
  for (let k = 0; k < 400; k++) sim.tick();
  laid.forEach((l, i) => l.g.forEach((n, j) => {
    n.sx = n.x = centres[i].x + l.slots[j][0];
    n.sy = n.y = centres[i].y + l.slots[j][1];
  }));
}
