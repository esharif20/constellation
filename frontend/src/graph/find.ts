// "Find by what it does" (#80): when the typed text names no Item well, ask the local skill search. Pure helpers, no DOM.
export type FindHit = { id: string; name: string; description: string; invoke: string; why: string };
export type Found = { available: boolean; results: FindHit[]; note: string | null };

const MIN = 3;
// Name-ish reasons from searchItems: a typed name or a near miss of one. Anything else (description, letters of) is not a name the user knew.
const nameWhy = (why: string) => why === "name" || why === "name starts with it" || why.startsWith("close to");

export function wantsFind(rows: { why: string }[], query: string): boolean {
  return query.trim().length >= MIN && !rows.some((r) => nameWhy(r.why));
}

// Short enough to read in a list row; the server already redacts and caps hints.
export const oneLine = (s: string, max = 110) => { const t = s.replace(/\s+/g, " ").trim(); return t.length > max ? `${t.slice(0, max - 1)}…` : t; };
