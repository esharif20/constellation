// The Constellation as the API serves it (GET /api/constellation), and the graph model the canvas draws.
import { layout } from "./layout.ts";
import { searchItems } from "./search.ts";

export type Item = { id: string; kind: string; name: string; description: string; source: string; disabled?: boolean;
  origin?: string | null; scope?: string; project?: string | null }; // local display data; scope is "global" or "project"
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
  assessments?: Record<string, Assessment>; // Item id -> verdict; absent on an old server
  hook_weights?: Record<string, Weight>;
  projects?: Record<string, string>; // opaque key -> display label; local only, never sent anywhere
  usage_by_project?: Record<string, Record<string, Usage>>; // Item id -> project key -> Usage
  current_project?: string | null; // key of the repo the scan was run for
};
export type Verdict = "duplicate" | "wrapper" | "overlap" | "distinct";
export type Overlap = { a_id: string; b_id: string; verdict: Verdict; reason: string };

// The server's verdict for one Item (smarter-verdict.md 4.1; src/constellation/verdict_types.py). The app only reads it.
export type Tier = "keep" | "keep_rare" | "review" | "redundant" | "could_go" | "too_early" | "off" | "untracked";
export type Confidence = "high" | "medium" | "low";
export type Habit = { sessions_used: number; days_used: number; idle_active_days: number | null; mean_gap: number | null; trend: "new" | "rising" | "steady" | "fading" | null; percentile: number | null; pinned: boolean };
export type Habits = { items: Record<string, Habit>; sessions: number; activeDays: number }; // from GET /api/assess: counts and words only
export type Assessment = { id: string; tier: Tier; label: string; confidence: Confidence | null; reasons: { code: string; text: string }[]; action: string; saves: number | null; risk: number; group: "safe" | "look" | "wait" | null; recheck_after: number | null; twin_id?: string | null };
export type BriefRow = { id: string; kind: string; item_ids: string[]; removes: string | null; reason: string; saves?: number | null; tokens_saved?: number | null; tier?: Tier; confidence?: Confidence | null; reasons?: { code: string; text: string }[]; project?: string | null; project_label?: string | null };
export type BriefGroup = { rows: BriefRow[]; saves?: number; unknown?: number };
export type Checklist = { path: string; ids: string[]; frees: number | null; unknown_rows: number };
// smarter-verdict.md 5.4. `per_day` is absent when the pace is unknown.
// `weekly` (src/constellation/weekly.py) is null until a second scan exists: names, labels and counts only, never an id or a path.
type WeeklyRow = { kind: string; name: string };
export type WeeklyData = {
  state: "ready"; since: string; days: number; headline: string; added: WeeklyRow[]; removed: WeeklyRow[]; went_quiet: WeeklyRow[];
  session_start: { then: number | null; now: number | null; delta: number | null; unknown_then: number; unknown_now: number };
  verdict_changes: (WeeklyRow & { from: string; to: string; why: string })[];
  used_most: (WeeklyRow & { uses: number })[];
  reclaim: { now: WeeklyRange; then: WeeklyRange };
};
type WeeklyRange = { low: number; high: number; unknown: number; confidence: Confidence };
export type BriefData = {
  weekly?: WeeklyData | null;
  evidence?: { sessions: number; active_days: number; span_days: number; ledger?: boolean };
  safe: BriefGroup; look: BriefGroup;
  wait: { summary: { code: string; count: number; recheck_after: number | null }[]; rows: BriefRow[] };
  range: { low: number; high: number; per_day?: [number, number] | null; unknown: number };
  scope?: { rows: BriefRow[]; caveat: string }; checklist?: Checklist;
};

// The scope filter: which stars stay lit. "repo" is only offered when the scan knows its repo.
export type Scope = "all" | "global" | "repo";

export type Shape = "dot" | "ring" | "diamond" | "square" | "triangle";
export type GNode = Item & {
  label: string;
  shape: Shape;
  degree: number;
  r: number;
  unknown: boolean; // always-on cost not known (null or missing): drawn hollow, never as zero
  cluster?: Cluster;
  cost?: Cost;
  usage?: Usage;
  byProject?: Record<string, Usage>; // uses per project key; labels live in Model.projects
  weight?: Weight;
  // simulation and animation state, mutated in place each frame (never React state)
  x?: number; y?: number; vx?: number; vy?: number; fx?: number; fy?: number;
  a: number; s: number; born: number;
  la: number; // canvas name alpha, eased over time toward 0 or 1 (paint.ts); never a zoom-scrubbed partial
  sx: number; sy: number; // the slot the layout assigns: a tidy spot in its cluster that the force pulls it back to
};
// An Overlap verdict between two Items; for `wrapper`, a is the wrapper and b what it calls. Not a force link.
export type GOverlap = { a: GNode; b: GNode; verdict: Exclude<Verdict, "distinct">; reason: string; alpha: number };
export type GLink = { source: GNode; target: GNode; kind: string; a: number; hot: boolean };
// la/lx/ly/pick: the cluster name's eased alpha, its position in graph units, and which candidate spot it last took (see paint.ts)
export type Cluster = { name: string; members: GNode[]; x: number; y: number; r: number; mx: number; my: number; fr: number; core?: boolean; a: number; la: number; lx: number; ly: number; pick: number; slug: string; box: [number, number, number, number]; hit: boolean }; // slug: the #cluster= deep link; box/hit: where its name was last drawn on screen (paint.ts post), for clicks
export type Pack = { origin: string; members: GNode[] }; // Items that share an origin, biggest first
export type Model = { nodes: GNode[]; links: GLink[]; clusters: Cluster[]; neighbours: Map<GNode, Set<GNode>>; overlaps: GOverlap[]; overlapsOf: Map<GNode, GOverlap[]>; costRef: number; heavyR: number; usageWindow: UsageWindow | null; assessments: Record<string, Assessment>; projects: Record<string, string>; currentProject: string | null; warnings: string[]; packs: Pack[]; offline: boolean; offlineNote: string };

// Star radius from always-on cost, area-proportional (magnitude by area, not radius). cRef is the scan's 95th percentile,
// so one huge MCP server cannot shrink everything else. Unknown cost gets its own middling size (and is drawn hollow).
export const RMIN = 2.6, RMAX = 9, RUNK = 4.5;
export const costRadius = (alwaysOn: number | null | undefined, cRef: number) =>
  alwaysOn == null ? RUNK : Math.max(RMIN, Math.min(RMAX, RMAX * Math.sqrt(alwaysOn / cRef)));

const KIND_NAME: Record<string, string> = { skill: "Skill", hook: "Hook", agent: "Agent", plugin: "Plugin", mcp_server: "MCP server", connector: "Connector", command: "Command" };
export const kindName = (k: string) => KIND_NAME[k] ?? k.replace(/_/g, " ");

const SHAPE: Record<string, Shape> = { plugin: "ring", mcp_server: "diamond", connector: "square", command: "triangle" }; // structural kinds share one colour, so shape carries identity

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
    const n: GNode = { ...it, label: labels[it.id] ?? "", shape: SHAPE[it.kind] ?? "dot", degree: 0, r: 0, unknown: false, cost: costs[it.id], usage: data.usage?.[it.id], byProject: data.usage_by_project?.[it.id], weight: data.hook_weights?.[it.id], a: 0, s: 1, born: 0, la: 0, sx: 0, sy: 0 };
    byId.set(n.id, n);
    return n;
  });
  const clusters: Cluster[] = (data.clusters ?? [])
    .map((c) => ({ name: labelled ? c.name : tidy(c.name), members: c.item_ids.flatMap((id) => byId.get(id) ?? []), x: 0, y: 0, r: 0, mx: 0, my: 0, fr: 0, a: 0, la: 0, lx: 0, ly: 0, pick: 0, slug: "", box: newBox(), hit: false }))
    .filter((c) => c.members.length);
  // Clusters of fewer than 3 Items, and Items in no cluster, share one quiet region called "Other"
  const big = clusters.filter((c) => c.members.length >= 3);
  big.forEach((c) => c.members.forEach((n) => (n.cluster = c)));
  // No real clusters, or one blob holding nearly everything (an offline or failed grouping): group by pack origin, else by kind, so the map still shows distinct regions
  if ((!big.length || (big.length === 1 && big[0].members.length >= 0.8 * nodes.length)) && nodes.length >= 12) {
    for (const key of [(n: GNode) => (n.origin ? originTail(n.origin) : ""), (n: GNode) => kindName(n.kind)]) {
      const by = new Map<string, GNode[]>();
      for (const n of nodes) { const k = key(n); if (k) by.set(k, [...(by.get(k) ?? []), n]); }
      const groups = [...by].filter(([, m]) => m.length >= 3);
      if (groups.length < 2 || groups.reduce((t, [, m]) => t + m.length, 0) < nodes.length / 2) continue; // too few or too little covered: try the next key
      big.length = 0;
      for (const [name, members] of groups) {
        const c: Cluster = { name, members, x: 0, y: 0, r: 0, mx: 0, my: 0, fr: 0, a: 0, la: 0, lx: 0, ly: 0, pick: 0, slug: "", box: newBox(), hit: false };
        members.forEach((n) => (n.cluster = c));
        big.push(c);
      }
      break;
    }
  }
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
  // the star radius at the 90th percentile of known cost: the "heavy" stars whose names show at the fitted view (labels.md 1, tuned: a fixed r >= 7 named 47% of the demo's known stars)
  const heavyR = known.length ? costRadius(known[Math.floor(0.9 * known.length)], costRef) : Infinity;
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
  return { nodes, links, clusters, neighbours, overlaps, overlapsOf, costRef, heavyR, usageWindow: data.usage_window ?? null, assessments: data.assessments ?? {}, projects: data.projects ?? {}, currentProject: data.current_project ?? null, warnings: data.warnings ?? [], packs: packsOf(nodes), offline: offlineNote !== "", offlineNote };
}

// Forgiving search (stopgap until #40/#41); see search.ts for the ranking.
export const search = (nodes: GNode[], query: string): GNode[] => searchItems(nodes, query, Infinity).map((h) => h.item);

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
  { prefix: "could not read skill lock", id: "lock", kind: "info", title: () => "Skill origins not read", hint: "The skills installer's lockfile was not valid JSON, so packs show no origin. Safe to ignore, or scan with --no-origins." },
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

// Shared by the hover tooltip and the Inspector (labels.md 9). `year` is dropped by the tooltip when the date is in the window's year.
export const day = (iso: string, year = true) => new Date(`${iso}T00:00:00Z`).toLocaleDateString(undefined, { day: "numeric", month: "short", ...(year ? { year: "numeric" } : {}), timeZone: "UTC" });
export const noun = (n: number, one: string) => `${n.toLocaleString()} ${one}${n === 1 ? "" : "s"}`;

// One usage line for the tooltip, or null when the kind is not tracked (no entry is not 0).
export function usageLine(n: Pick<GNode, "usage">, w: UsageWindow | null): string | null {
  const u = n.usage;
  if (!u) return null;
  if (u.count > 0) return u.last_used ? `${noun(u.count, "use")}, last ${day(u.last_used, u.last_used.slice(0, 4) !== w?.last?.slice(0, 4))}` : noun(u.count, "use");
  if (!w?.files) return "no transcripts scanned";
  if (w.first && w.last) return `never seen in ${noun(Math.round((Date.parse(w.last) - Date.parse(w.first)) / 864e5) + 1, "day")}`;
  return `never seen in ${noun(w.files, "transcript")}`;
}

// Badges under the tooltip: disabled, and the strongest Overlap verdict of the Item (duplicate > wrapper > overlap) with its count.
export const originTail = (origin: string) => origin.slice(origin.lastIndexOf("/") + 1);

// Origins with three or more members (a lone plugin name is not a pack worth a filter), biggest first, then by name.
export function packsOf(nodes: GNode[]): Pack[] {
  const by = new Map<string, GNode[]>();
  for (const n of nodes) if (n.origin) by.set(n.origin, [...(by.get(n.origin) ?? []), n]);
  return [...by].filter(([, m]) => m.length >= 3).map(([origin, members]) => ({ origin, members })).sort((a, b) => b.members.length - a.members.length || a.origin.localeCompare(b.origin));
}

export function tipBadges(n: GNode, model: Pick<Model, "overlapsOf">): { disabled: boolean; overlap: string | null } {
  const os = model.overlapsOf.get(n) ?? [];
  const role = (o: GOverlap) => (o.verdict === "duplicate" ? "Duplicate" : o.verdict === "wrapper" ? (o.a === n ? "Wraps" : "Wrapped by") : "Overlaps");
  const best = ["Duplicate", "Wraps", "Wrapped by", "Overlaps"].find((r) => os.some((o) => role(o) === r));
  const count = best ? os.filter((o) => role(o) === best).length : 0;
  return { disabled: !!n.disabled, overlap: best ? (count > 1 ? `${best} ${count}` : best) : null };
}

// The scope filter is offered only when the scan carries project data. "This repo" is what lives in the scanned repo, plus global Items
// used there; it needs current_project.
export const hasScopes = (m: Pick<Model, "nodes" | "projects">) => Object.keys(m.projects).length > 0 || m.nodes.some((n) => n.scope === "project");
export function scopeSet(m: Pick<Model, "nodes" | "currentProject">, scope: Scope): Set<GNode> | null {
  if (scope === "all") return null;
  const cur = m.currentProject;
  return new Set(m.nodes.filter((n) => scope === "global" ? n.scope !== "project" : n.scope === "project" ? n.project == null || n.project === cur : !!cur && (n.byProject?.[cur]?.count ?? 0) > 0));
}

// "9 in dev-constellation, 1 in another": the current repo and named projects first, labels local. Null when the Item has no per-project counts.
export function projectUses(n: Pick<GNode, "byProject">, m: Pick<Model, "projects" | "currentProject">): { label: string; count: number; current: boolean }[] | null {
  const rows = Object.entries(n.byProject ?? {}).filter(([, u]) => u.count > 0).map(([k, u]) => ({ label: m.projects[k] ?? "another project", count: u.count, current: k === m.currentProject }));
  return rows.length ? rows.sort((a, b) => +b.current - +a.current || b.count - a.count || a.label.localeCompare(b.label)) : null;
}

// Session-start budget. Unknown cost is counted, never summed as 0. An Item's always-on cost wins; a hook without one falls back to its prompt-time weight.
export type Budget = { measured: boolean; known: number; items: number; hooks: number; unknown: number; saved: number; removed: number; removedUnknown: number };
export function budget(nodes: GNode[], removed: ReadonlySet<GNode> = new Set()): Budget {
  const b: Budget = { measured: false, known: 0, items: 0, hooks: 0, unknown: 0, saved: 0, removed: 0, removedUnknown: 0 };
  for (const n of nodes) {
    const gone = removed.has(n), cost = n.cost?.always_on ?? null, tokens = n.kind === "hook" ? n.weight?.tokens ?? null : null;
    if (gone) b.removed++;
    if (cost == null && tokens == null) { if (gone) b.removedUnknown++; else b.unknown++; continue; }
    b.measured = true;
    if (gone) b.saved += cost ?? tokens!;
    else if (cost != null) { b.items += cost; b.known += cost; } else { b.hooks += tokens!; b.known += tokens!; }
  }
  return b;
}

// What-if: the picked Items plus everything they contain (a plugin takes its skills, hooks and servers). A visited set ends cycles.
export function withContents(model: Pick<Model, "links">, picked: ReadonlySet<GNode>): Set<GNode> {
  const out = new Set(picked), todo = [...picked];
  for (let n = todo.pop(); n; n = todo.pop()) {
    for (const l of model.links) if (l.kind === "contains" && l.source === n && !out.has(l.target)) { out.add(l.target); todo.push(l.target); }
  }
  return out;
}

// Cluster health (#71): what each named cluster costs, its share of recorded uses, its Overlaps and its cost rank. Follows what-if.
// Unknown cost is never summed as 0; rank is by known cost, ties by name, null when the cluster has no known cost.
export type Health = { known: number | null; unknown: number; useShare: number | null; overlaps: number; rank: number | null };
export function clusterHealth(model: Pick<Model, "clusters" | "nodes" | "overlaps" | "usageWindow">, removed?: ReadonlySet<GNode> | null): Map<Cluster, Health> {
  const gone = (n: GNode) => !!removed?.has(n);
  const total = model.nodes.reduce((s, n) => s + (gone(n) ? 0 : n.usage?.count ?? 0), 0);
  const out = new Map<Cluster, Health>();
  for (const c of model.clusters) {
    let known: number | null = null, unknown = 0, uses = 0;
    for (const n of c.members) {
      if (gone(n)) continue;
      if (n.unknown) unknown++; else known = (known ?? 0) + n.cost!.always_on!;
      uses += n.usage?.count ?? 0;
    }
    out.set(c, {
      known, unknown, rank: null,
      useShare: model.usageWindow && total > 0 ? uses / total : null,
      overlaps: model.overlaps.filter((o) => o.a.cluster === c && o.b.cluster === c && !gone(o.a) && !gone(o.b)).length,
    });
  }
  [...out].filter(([, h]) => h.known != null).sort((a, b) => b[1].known! - a[1].known! || a[0].name.localeCompare(b[0].name)).forEach(([, h], i) => { h.rank = i + 1; });
  return out;
}
