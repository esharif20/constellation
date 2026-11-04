// The Constellation as the API serves it (GET /api/constellation), and the graph model the canvas draws.
import { layout } from "./layout.ts";

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
  overlaps?: Overlap[];
};
export type Verdict = "duplicate" | "wrapper" | "overlap" | "distinct";
export type Overlap = { a_id: string; b_id: string; verdict: Verdict; reason: string };

export type BriefRow = { id: string; kind: "review_cost" | "remove_duplicate" | "use_underlying"; item_ids: string[]; removes: string | null; reason: string; tokens_saved: number | null };
export type BriefGroup = { rows: BriefRow[]; unknown: number; unknown_rows: number; frees: number | null };
export type Checklist = { path: string; ids: string[]; frees: number | null; unknown_rows: number };
export type BriefData = { cost: BriefGroup & { measured: boolean }; pairs: BriefGroup; checklist?: Checklist };

export type Shape = "dot" | "ring" | "diamond" | "square";
export type GNode = Item & {
  label: string;
  shape: Shape;
  degree: number;
  r: number;
  unknown: boolean; // always-on cost not known (null or missing): drawn hollow, never as zero
  cluster?: Cluster;
  cost?: Cost;
  // simulation and animation state, mutated in place each frame (never React state)
  x?: number; y?: number; vx?: number; vy?: number; fx?: number; fy?: number;
  a: number; s: number; born: number;
  sx: number; sy: number; // the slot the layout assigns: a tidy spot in its cluster that the force pulls it back to
};
// An Overlap verdict between two Items; for `wrapper`, a is the wrapper and b what it calls. Not a force link.
export type GOverlap = { a: GNode; b: GNode; verdict: Exclude<Verdict, "distinct">; reason: string; alpha: number };
export type GLink = { source: GNode; target: GNode; kind: string; a: number; hot: boolean };
// la/lx/ly/pick: the cluster name's eased alpha, its position in graph units, and which candidate spot it last took (see paint.ts)
export type Cluster = { name: string; members: GNode[]; x: number; y: number; r: number; a: number; la: number; lx: number; ly: number; pick: number };
export type Model = { nodes: GNode[]; links: GLink[]; clusters: Cluster[]; neighbours: Map<GNode, Set<GNode>>; overlaps: GOverlap[]; overlapsOf: Map<GNode, GOverlap[]>; costRef: number; warnings: string[]; offline: boolean };

// Star radius from always-on cost, area-proportional (magnitude by area, not radius). cRef is the scan's 95th percentile,
// so one huge MCP server cannot shrink everything else. Unknown cost gets its own middling size (and is drawn hollow).
export const RMIN = 2.6, RMAX = 9, RUNK = 4.5;
export const costRadius = (alwaysOn: number | null | undefined, cRef: number) =>
  alwaysOn == null ? RUNK : Math.max(RMIN, Math.min(RMAX, RMAX * Math.sqrt(alwaysOn / cRef)));

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
  const tall = Math.max(0.55, Math.min(2, aspect)); // wide screens spread the clusters sideways, tall ones downwards
  const byId = new Map<string, GNode>();
  const nodes = data.items.map((it) => {
    const n: GNode = { ...it, label: labels[it.id] ?? "", shape: SHAPE[it.kind] ?? "dot", degree: 0, r: 0, unknown: false, cost: costs[it.id], a: 0, s: 1, born: 0, sx: 0, sy: 0 };
    byId.set(n.id, n);
    return n;
  });
  const clusters: Cluster[] = (data.clusters ?? [])
    .map((c) => ({ name: labelled ? c.name : tidy(c.name), members: c.item_ids.flatMap((id) => byId.get(id) ?? []), x: 0, y: 0, r: 0, a: 0, la: 0, lx: 0, ly: 0, pick: 0 }))
    .filter((c) => c.members.length);
  // Clusters of fewer than 3 Items, and Items in no cluster, share one quiet region called "Other"
  const big = clusters.filter((c) => c.members.length >= 3);
  big.forEach((c) => c.members.forEach((n) => (n.cluster = c)));
  const rest = nodes.filter((n) => !n.cluster);
  if (rest.length) {
    const other: Cluster = { name: "Other", members: rest, x: 0, y: 0, r: 0, a: 0, la: 0, lx: 0, ly: 0, pick: 0 };
    rest.forEach((n) => (n.cluster = other));
    big.push(other);
  }
  clusters.splice(0, clusters.length, ...big);
  const neighbours = new Map(nodes.map((n) => [n, new Set<GNode>()]));
  const links: GLink[] = (data.relations ?? []).flatMap((r) => {
    const source = byId.get(r.source), target = byId.get(r.target);
    if (!source || !target) return [];
    neighbours.get(source)!.add(target);
    neighbours.get(target)!.add(source);
    return [{ source, target, kind: r.kind, a: 0, hot: false }];
  });
  const known = nodes.flatMap((n) => n.cost?.always_on ?? []).sort((a, b) => a - b);
  const costRef = Math.max(1, known[Math.min(known.length - 1, Math.floor(0.95 * known.length))] ?? 1);
  for (const n of nodes) {
    n.degree = neighbours.get(n)!.size;
    n.unknown = n.cost?.always_on == null;
    n.r = costRadius(n.cost?.always_on, costRef);
  }
  const overlapsOf = new Map(nodes.map((n) => [n, [] as GOverlap[]]));
  const overlaps = (data.overlaps ?? []).flatMap((o) => {
    const a = byId.get(o.a_id), b = byId.get(o.b_id);
    if (!a || !b || o.verdict === "distinct") return [];
    const g: GOverlap = { a, b, verdict: o.verdict, reason: o.reason, alpha: 0 };
    overlapsOf.get(a)!.push(g);
    overlapsOf.get(b)!.push(g);
    return [g];
  });
  layout(nodes, links, clusters, tall);
  return { nodes, links, clusters, neighbours, overlaps, overlapsOf, costRef, warnings: data.warnings ?? [], offline: (data.warnings ?? []).some((w) => w.startsWith("Offline")) };
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
