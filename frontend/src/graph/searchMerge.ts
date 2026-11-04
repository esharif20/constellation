// Pure helpers for the search box: merge the server's answer under the instant local one, match cluster names, suggest a spelling.
import { searchItems, type Hit } from "./search.ts";

export type Remote = { results: { id: string; why: string }[]; note: string | null };
export type Row<T> = { item: T; why: string; related: boolean };

// Local hits first (instant, and an exact name is already first); server hits not already shown follow.
// "similar meaning" hits are the Related group; any other server reason stays in the main list.
export function mergeResults<T extends { id: string }>(local: Hit<T>[], remote: Remote | null, byId: Map<string, T>): Row<T>[] {
  const rows: Row<T>[] = local.map((h) => ({ ...h, related: false }));
  const seen = new Set(rows.map((r) => r.item.id));
  for (const r of remote?.results ?? []) {
    const item = byId.get(r.id);
    if (!item || seen.has(r.id)) continue;
    seen.add(r.id);
    rows.push({ item, why: r.why, related: r.why === "similar meaning" });
  }
  return [...rows.filter((r) => !r.related), ...rows.filter((r) => r.related)]; // Related last, so a cut keeps the strongest
}

// Cluster names matching the query, by the Item ranker; the weakest tier (loose letters) is too noisy for a short list.
export function matchClusters<C extends { name: string }>(clusters: C[], query: string, limit = 3): C[] {
  const cards = clusters.map((c) => ({ name: c.name, description: "", kind: "", c }));
  return searchItems(cards, query, limit * 3).filter((h) => !h.why.startsWith("letters of")).slice(0, limit).map((h) => h.item.c);
}

function distance(a: string, b: string): number {
  // optimal string alignment: an adjacent swap ("shadnc") costs 1
  const d = Array.from({ length: a.length + 1 }, (_, i) => Array.from({ length: b.length + 1 }, (_, j) => (i ? (j ? 0 : i) : j)));
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
    }
  }
  return d[a.length][b.length];
}

const squash = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "");

// The top hit's name when the query is a near miss of it (1 edit, 2 for long names); null when it is already right or far off
export function didYouMean(query: string, topName: string | undefined): string | null {
  if (!topName) return null;
  const q = squash(query), n = squash(topName);
  if (q.length < 4 || q === n) return null;
  const d = distance(q, n);
  return d >= 1 && d <= (n.length >= 8 ? 2 : 1) ? topName : null;
}

// Plan A "why is X not shown": a scan warning that mentions the query explains a skipped Item
export function warningMention(warnings: string[], query: string): string | null {
  const q = query.trim().toLowerCase();
  return q.length >= 3 ? (warnings.find((w) => w.toLowerCase().includes(q)) ?? null) : null;
}
