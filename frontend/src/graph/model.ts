// The Constellation as the API serves it (GET /api/constellation), and the graph model the canvas draws.
import { layout } from "./layout.ts";

export type Item = { id: string; kind: string; name: string; description: string; source: string };
export type Relation = { source: string; target: string; kind: string };
export type Cost = { always_on: number | null; on_use: number | null };
export type Usage = { count: number; last_used: string | null };
export type UsageWindow = { files: number; first: string | null; last: string | null; skipped: number };
export type Weight = { bytes: number | null; tokens: number | null };
export type Constellation = {
  items: Item[];
  relations?: Relation[];
  labels?: Record<string, string>;
  clusters?: { name: string; item_ids: string[] }[];
  warnings?: string[];
  costs?: Record<string, Cost>;
  overlaps?: Overlap[];
  usage?: Record<string, Usage>; // only skills, agents and MCP servers/connectors have an entry; no entry means not tracked, not 0
  usage_window?: UsageWindow | null;
  hook_weights?: Record<string, Weight>;
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
  usage?: Usage;
  weight?: Weight;
  // simulation and animation state, mutated in place each frame (never React state)
  x?: number; y?: number; vx?: number; vy?: number; fx?: number; fy?: number;
  a: number; s: number; born: number;
  sx: number; sy: number; // the slot the layout assigns: a tidy spot in its cluster that the force pulls it back to
};
// An Overlap verdict between two Items; for `wrapper`, a is the wrapper and b what it calls. Not a force link.
export type GOverlap = { a: GNode; b: GNode; verdict: Exclude<Verdict, "distinct">; reason: string; alpha: number };
export type GLink = { source: GNode; target: GNode; kind: string; a: number; hot: boolean };
// la/lx/ly/pick: the cluster name's eased alpha, its position in graph units, and which candidate spot it last took (see paint.ts)
export type Cluster = { name: string; members: GNode[]; x: number; y: number; r: number; mx: number; my: number; fr: number; a: number; la: number; lx: number; ly: number; pick: number; slug: string; box: [number, number, number, number]; hit: boolean }; // slug: the #cluster= deep link; box/hit: where its name was last drawn on screen (paint.ts post), for clicks
export type Model = { nodes: GNode[]; links: GLink[]; clusters: Cluster[]; neighbours: Map<GNode, Set<GNode>>; overlaps: GOverlap[]; overlapsOf: Map<GNode, GOverlap[]>; costRef: number; usageWindow: UsageWindow | null; warnings: string[]; offline: boolean; offlineNote: string };

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

const newBox = (): Cluster["box"] => [0, 0, 0, 0];

// Without labels (an offline scan) a cluster is named after its first Item, which is often kebab-case: read it as words.
const tidy = (s: string) => s.replace(/[-_]+/g, " ");

// `aspect` is the viewport's height over width: tall (phone) screens seed a taller layout so the map fills them.
export function buildModel(data: Constellation, aspect = 1): Model {
  const labels = data.labels ?? {}, costs = data.costs ?? {}, labelled = Object.keys(labels).length > 0;
  const tall = Math.max(0.55, Math.min(2, aspect)); // wide screens spread the clusters sideways, tall ones downwards
  const byId = new Map<string, GNode>();
  const nodes = data.items.map((it) => {
    const n: GNode = { ...it, label: labels[it.id] ?? "", shape: SHAPE[it.kind] ?? "dot", degree: 0, r: 0, unknown: false, cost: costs[it.id], usage: data.usage?.[it.id], weight: data.hook_weights?.[it.id], a: 0, s: 1, born: 0, sx: 0, sy: 0 };
    byId.set(n.id, n);
    return n;
  });
  const clusters: Cluster[] = (data.clusters ?? [])
    .map((c) => ({ name: labelled ? c.name : tidy(c.name), members: c.item_ids.flatMap((id) => byId.get(id) ?? []), x: 0, y: 0, r: 0, mx: 0, my: 0, fr: 0, a: 0, la: 0, lx: 0, ly: 0, pick: 0, slug: "", box: newBox(), hit: false }))
    .filter((c) => c.members.length);
  // Clusters of fewer than 3 Items, and Items in no cluster, share one quiet region called "Other"
  const big = clusters.filter((c) => c.members.length >= 3);
  big.forEach((c) => c.members.forEach((n) => (n.cluster = c)));
  const rest = nodes.filter((n) => !n.cluster);
  if (rest.length) {
    const other: Cluster = { name: "Other", members: rest, x: 0, y: 0, r: 0, mx: 0, my: 0, fr: 0, a: 0, la: 0, lx: 0, ly: 0, pick: 0, slug: "", box: newBox(), hit: false };
    rest.forEach((n) => (n.cluster = other));
    big.push(other);
  }
  clusters.splice(0, clusters.length, ...big);
  const slugs = new Set<string>();
  for (const c of clusters) {
    const base = c.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "cluster";
    let slug = base;
    for (let i = 2; slugs.has(slug); i++) slug = `${base}-${i}`;
    slugs.add(slug);
    c.slug = slug;
  }
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
  const offlineNote = (data.warnings ?? []).find((w) => w.startsWith("Offline")) ?? "";
  layout(nodes, links, clusters, tall);
  return { nodes, links, clusters, neighbours, overlaps, overlapsOf, costRef, usageWindow: data.usage_window ?? null, warnings: data.warnings ?? [], offline: offlineNote !== "", offlineNote };
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

// Warnings grouped for the top bar. Keyed on the message prefixes the Python side emits; tests/test_warning_contract.py pins them.
// "Offline" is a mode (Model.offline), not a warning, so it is left out. "actionable": the user can fix it; "degraded": a paid
// step failed and the map is partly offline; "info": safe to ignore.
export type WarningKind = "actionable" | "degraded" | "info";
export type WarningItem = { text: string; path?: string };
export type WarningGroup = { id: string; kind: WarningKind; title: (n: number) => string; hint?: string; items: WarningItem[] };

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
const RULES: { prefix: string; id: string; kind: WarningKind; title: (n: number) => string; hint?: string }[] = [
  { prefix: "skipped ", id: "missing", kind: "actionable", title: (n) => `Not on the map: ${plural(n, "file is", "files are")} missing a name or description`, hint: "Add the missing field to the file's frontmatter." },
  { prefix: "could not save the", id: "cache", kind: "actionable", title: () => "Cache not writable: the next scan will pay again", hint: "Check the folder is writable." },
  { prefix: "could not label", id: "label", kind: "degraded", title: (n) => `Partly offline: ${plural(n, "label", "labels")} failed` },
  { prefix: "could not verify", id: "verify", kind: "degraded", title: (n) => `Partly offline: ${plural(n, "overlap check", "overlap checks")} failed` },
  { prefix: "could not count", id: "count", kind: "degraded", title: () => "Partly offline: token counts failed" },
  { prefix: "could not cluster", id: "cluster", kind: "degraded", title: () => "Partly offline: grouping into clusters failed" },
  { prefix: "frontmatter is not valid YAML", id: "loose", kind: "info", title: (n) => `${plural(n, "file has", "files have")} loose frontmatter, read anyway`, hint: "Safe to ignore: Claude Code reads them too. To tidy, quote the description." },
  { prefix: "no frontmatter in", id: "bare", kind: "info", title: (n) => `${plural(n, "file has", "files have")} no frontmatter`, hint: "Safe to ignore unless the file should be a skill or agent." },
  { prefix: "usage:", id: "usage", kind: "info", title: () => "Usage reading", hint: "Some transcripts were not read; usage counts may be low." },
];

export function groupWarnings(warnings: string[]): WarningGroup[] {
  const groups = new Map<string, WarningGroup>();
  for (const w of warnings) {
    if (w.startsWith("Offline")) continue;
    const rule = RULES.find((r) => w.startsWith(r.prefix)) ?? { prefix: "", id: "other", kind: "info" as const, title: () => "Other notes" };
    const g = groups.get(rule.id) ?? { id: rule.id, kind: rule.kind, title: rule.title, hint: rule.hint, items: [] };
    const m = /^(.*?) \((~?\/[^()]*)\)$/.exec(w);
    const bare = rule.id === "bare" ? w.slice(rule.prefix.length).trim() : null;
    g.items.push(bare ? { text: bare, path: bare } : m ? { text: rule.id === "missing" ? `${m[1].replace(/^skipped /, "")} (${m[2]})` : m[2], path: m[2] } : { text: w });
    groups.set(rule.id, g);
  }
  const order = { actionable: 0, degraded: 1, info: 2 };
  return [...groups.values()].sort((a, b) => order[a.kind] - order[b.kind]);
}

// What a cluster costs, for the card. Unknown cost is never added in and never shown as 0: `known` is null when no member has a cost.
export type ClusterSummary = {
  count: number;
  kinds: [string, number][]; // by count desc, then kind name
  known: number | null; // sum of known always-on costs
  unknown: number; // members whose cost is unknown
  top: GNode[]; // the 3 costliest members with a known cost, cost desc then name
  overlaps: GOverlap[]; // Overlaps with both ends inside
  unused: { tracked: number; unseen: number } | null; // only Items of tracked kinds (a usage entry) count; null without a usage window
};
export function clusterSummary(c: Cluster, model: Pick<Model, "overlaps" | "usageWindow">): ClusterSummary {
  const kinds = new Map<string, number>();
  let known: number | null = null, unknown = 0, tracked = 0, unseen = 0;
  for (const n of c.members) {
    kinds.set(n.kind, (kinds.get(n.kind) ?? 0) + 1);
    if (n.unknown) unknown++;
    else known = (known ?? 0) + n.cost!.always_on!;
    if (n.usage) { tracked++; if (n.usage.count === 0) unseen++; }
  }
  const top = c.members.filter((n) => !n.unknown).sort((a, b) => b.cost!.always_on! - a.cost!.always_on! || a.name.localeCompare(b.name)).slice(0, 3);
  return {
    count: c.members.length,
    kinds: [...kinds].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])),
    known, unknown, top,
    overlaps: model.overlaps.filter((o) => o.a.cluster === c && o.b.cluster === c),
    unused: model.usageWindow && tracked > 0 ? { tracked, unseen } : null,
  };
}

// Focus order for member names: known cost first (high to low), then hubs, then name.
export const rankMembers = (c: Cluster): GNode[] =>
  [...c.members].sort((a, b) => (a.unknown ? 1 : 0) - (b.unknown ? 1 : 0) || (b.cost?.always_on ?? 0) - (a.cost?.always_on ?? 0) || b.degree - a.degree || a.name.localeCompare(b.name));
