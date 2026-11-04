// Forgiving Item search. STOPGAP until the real natural-language search (#40/#41) lands; pure, no DOM.
type Searchable = { name: string; description: string; kind: string; label?: string; degree?: number };
export type Hit<T> = { item: T; why: string };

const FILLER = new Set("where is are the my find show me a an of to for do i which what skill skills plugin plugins agent agents hook hooks".split(" "));
const words = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim().split(" ").filter(Boolean);

export function tokens(query: string): string[] {
  const all = words(query), rest = all.filter((w) => !FILLER.has(w));
  return rest.length ? rest : all; // filler words go only when something else remains
}

// Optimal string alignment distance (adjacent swap counts 1), capped: returns 2 once it is certainly > 1
function near(a: string, b: string): boolean {
  if (a === b) return true;
  if (Math.abs(a.length - b.length) > 1) return false;
  let i = 0;
  while (i < a.length && i < b.length && a[i] === b[i]) i++;
  const x = a.slice(i), y = b.slice(i);
  if (x.slice(1) === y.slice(1)) return true; // substitution
  if (x.slice(1) === y || x === y.slice(1)) return true; // insertion or deletion
  return x.length > 1 && y.length > 1 && x[0] === y[1] && x[1] === y[0] && x.slice(2) === y.slice(2); // swap
}

const subsequence = (q: string, s: string) => { let i = 0; for (const c of s) if (c === q[i]) i++; return i === q.length; };

// Tiers, best first: 0 exact name, 1 name prefix, 2 name contains, 3 every token in name/description/kind, 4 typo, 5 subsequence of name
function tier(it: Searchable, toks: string[], joined: string): [number, string] | null {
  const nameWords = words(it.name), name = nameWords.join("");
  if (name === joined) return [0, "name"];
  if (name.startsWith(joined)) return [1, "name starts with it"];
  if (name.includes(joined)) return [2, "name"];
  const nameHay = ` ${nameWords.join(" ")} `, hay = ` ${nameWords.join(" ")} ${words(it.description).join(" ")} ${words(it.kind).join(" ")} ${words(it.label ?? "").join(" ")} `;
  if (toks.every((t) => hay.includes(t))) return [3, toks.every((t) => nameHay.includes(t)) ? "name" : "in description"];
  for (const q of [joined, ...toks]) {
    if (q.length < 5) continue;
    for (const c of [name, ...nameWords]) if (near(q, c)) return [4, `close to "${it.name}"`];
  }
  if (joined.length >= 3 && subsequence(joined, name)) return [5, `letters of "${it.name}"`];
  return null;
}

// Top `limit` Items for a query, each with a short plain-language reason it matched
export function searchItems<T extends Searchable>(items: T[], query: string, limit = 8): Hit<T>[] {
  const toks = tokens(query);
  if (!toks.length) return [];
  const joined = toks.join("");
  const hits: { item: T; t: number; why: string }[] = [];
  for (const item of items) { const r = tier(item, toks, joined); if (r) hits.push({ item, t: r[0], why: r[1] }); }
  hits.sort((a, b) => a.t - b.t || (b.item.degree ?? 0) - (a.item.degree ?? 0) || a.item.name.localeCompare(b.item.name));
  return hits.slice(0, limit).map(({ item, why }) => ({ item, why }));
}
