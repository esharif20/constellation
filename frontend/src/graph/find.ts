// "Find by what it does" (#80): when the typed text names no Item well, ask the local skill search. Pure helpers, no DOM.
export type FindHit = { id: string; name: string; description: string; invoke: string; why: string; last_seen?: string; cost?: string };
export type FindFilters = { kind: "skill" | "agent" | "command" | "mcp"; forgotten: boolean; origin: "" | "plugin" | "yours" };
export const NO_FILTERS: FindFilters = { kind: "skill", forgotten: false, origin: "" };
export const filtersActive = (f: FindFilters) => f.kind !== "skill" || f.forgotten || f.origin !== "";
// The /api/find query string; the server filters, so the 8 shown are the best 8 after filtering.
export const findQuery = (q: string, f: FindFilters) => `q=${encodeURIComponent(q)}&kind=${f.kind}${f.forgotten ? "&forgotten=true" : ""}${f.origin ? `&origin=${f.origin}` : ""}`;
export type Found = { available: boolean; results: FindHit[]; note: string | null };

const MIN = 3;
// Name-ish reasons from searchItems: a typed name or a near miss of one. Anything else (description, letters of) is not a name the user knew.
const nameWhy = (why: string, typo: boolean) => why === "name" || why === "name starts with it" || (typo && why.startsWith("close to"));

export function wantsFind(rows: { why: string }[], query: string): boolean {
  const q = query.trim();
  // A near miss only counts for one word (a typo of a name); a phrase with a fuzzy hit is still a question about what an Item does.
  return q.length >= MIN && !rows.some((r) => nameWhy(r.why, !/\s/.test(q)));
}

// Short enough to read in a list row; the server already redacts and caps hints.
export const oneLine = (s: string, max = 110) => { const t = s.replace(/\s+/g, " ").trim(); return t.length > max ? `${t.slice(0, max - 1)}…` : t; };

// ⌘K on a Mac, Ctrl+K elsewhere; it works even while typing in another field, as in most developer tools.
export const isSearchShortcut = (e: { key: string; metaKey: boolean; ctrlKey: boolean; altKey: boolean; shiftKey: boolean }) =>
  e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey;
export const searchHint = (platform: string) => (/mac|iphone|ipad/i.test(platform) ? "⌘K" : "Ctrl K");

// What the "Find by what it does" group shows: nothing asked, still looking, a server note, hits, or nothing found.
export type FindState = "off" | "loading" | "note" | "hits" | "none";
export function findState(asking: boolean, found: Found | null, pending: boolean, hits: number): FindState {
  if (!asking) return "off";
  if (!found) return pending ? "loading" : "off"; // no answer and none coming: the API is absent
  if (found.note) return "note";
  return hits > 0 ? "hits" : "none";
}
