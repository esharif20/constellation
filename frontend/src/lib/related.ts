// Related Items for the Inspector (docs/design/inspector.md section 1.6): Overlap verdicts, Relations, plugin siblings, same cluster.
import { relName, type GNode, type GOverlap, type Model } from "@/graph/model";

export type RelatedGroup = { title: string; rows: { other: GNode; reason?: string }[] };
export const CAP = 5;
const OVERLAP = ["Does the same job", "Wraps", "Wrapped by", "Overlaps with"];

const byCost = (a: GNode, b: GNode) => (a.cost?.always_on == null ? 1 : 0) - (b.cost?.always_on == null ? 1 : 0) || (b.cost?.always_on ?? 0) - (a.cost?.always_on ?? 0) || a.name.localeCompare(b.name);

export function relatedGroups(item: GNode, model: Pick<Model, "links" | "overlapsOf">): RelatedGroup[] {
  const groups: RelatedGroup[] = [];
  const title = (o: GOverlap) => (o.verdict === "duplicate" ? OVERLAP[0] : o.verdict === "wrapper" ? (o.a === item ? OVERLAP[1] : OVERLAP[2]) : OVERLAP[3]);
  const os = model.overlapsOf.get(item) ?? [];
  for (const t of OVERLAP) {
    const rows = os.filter((o) => title(o) === t).map((o) => ({ other: o.a === item ? o.b : o.a, reason: o.reason }));
    if (rows.length) groups.push({ title: t, rows });
  }
  const rel = new Map<string, GNode[]>();
  const parents: GNode[] = [];
  for (const l of model.links) {
    const out = l.source === item;
    if (!out && l.target !== item) continue;
    const key = relName(l.kind, out);
    rel.set(key, [...(rel.get(key) ?? []), out ? l.target : l.source]);
    if (!out && l.kind === "contains") parents.push(l.source);
  }
  for (const [t, others] of rel) groups.push({ title: t, rows: others.sort((a, b) => a.name.localeCompare(b.name)).map((other) => ({ other })) });
  const seen = new Set(groups.flatMap((g) => g.rows.map((r) => r.other)));
  seen.add(item);
  const siblings = [...new Set(model.links.filter((l) => l.kind === "contains" && parents.includes(l.source)).map((l) => l.target))].filter((n) => n !== item).sort((a, b) => a.name.localeCompare(b.name));
  if (siblings.length) groups.push({ title: "In the same plugin", rows: siblings.map((other) => ({ other })) });
  siblings.forEach((s) => seen.add(s));
  const mates = (item.cluster?.members ?? []).filter((n) => !seen.has(n)).sort(byCost);
  if (mates.length) groups.push({ title: "Same cluster", rows: mates.map((other) => ({ other })) });
  return groups;
}
