import fs from "node:fs";
// Writes demo-250.json: invented names only, shaped like a real setup (about 250 Items, 30 clusters of very different
// sizes, a few plugin hubs with Relations, most Items with none). Seeded, so identical every run: node docs/design/make-demo.mjs
let seed = 7;
const rnd = () => ((seed = (seed * 1664525 + 1013904223) % 4294967296) / 4294967296);
const pick = (a) => a[Math.floor(rnd() * a.length)];
const themes = ["Tidy the changelog", "Plan the quarterly review", "Hook script execution", "Pressing flowers", "Stage lighting cues", "Tide table lookups", "Bread and fermentation", "Orchard pruning notes", "Kite building", "Lantern repair", "Map making", "Chess openings", "Beekeeping log", "Compost schedule", "Glass blowing", "Marathon pacing", "Tea tasting", "Moth identification", "Bridge inspection", "Lighthouse upkeep", "Feature implementation planning", "Plan design interview", "Garden irrigation", "Vinyl cataloguing", "Telescope alignment", "Ceramic glazes", "Rope knots", "Weather diary", "Puppet staging", "Claude Code hook setup"];
const verbs = ["sort", "fold", "trace", "mend", "weigh", "chart", "polish", "label", "sweep", "gather", "draft", "check", "tune", "bind", "scout"];
const nouns = ["ledger", "stencil", "compass", "ribbon", "lattice", "beacon", "anvil", "tally", "thread", "plinth", "wick", "crate", "valve", "gasket", "canvas"];
const sizes = [28, 26, 20, 17, 14, 13, 12, 11, 10, 9, 8, 8, 7, 7, 6, 6, 5, 5, 4, 4, 3, 3, 2, 2, 2, 1, 1, 1, 1, 3];
const items = [], relations = [], labels = {}, clusters = [], costs = {};
const used = new Set();
const name = () => { for (;;) { const n = `${pick(verbs)}-${pick(nouns)}${rnd() < 0.5 ? "" : "-" + pick(["two", "lite", "pro", "mini"])}`; if (!used.has(n)) { used.add(n); return n; } } };
themes.forEach((theme, ci) => {
  const ids = [];
  const hub = sizes[ci] >= 8 ? `plugin:${theme.split(" ")[0].toLowerCase()}${ci}` : null;
  if (hub) { items.push({ id: hub, kind: "plugin", name: `${theme.split(" ")[0].toLowerCase()}${ci}`, description: `A bundle for ${theme.toLowerCase()}.`, source: `~/.claude/plugins/p${ci}/plugin.json` }); ids.push(hub); labels[hub] = theme; }
  const n = sizes[ci] - (hub ? 1 : 0);
  for (let i = 0; i < n; i++) {
    const nm = name(), kind = rnd() < 0.12 ? "hook" : rnd() < 0.1 ? "agent" : "skill";
    const id = `${kind}:${ci}:${nm}`;
    items.push({ id, kind, name: nm, description: `Use when the task involves ${nm.replace("-", " ")}. Keeps the work small.`, source: `~/.claude/${kind}s/${nm}` });
    ids.push(id); labels[id] = `${nm.replace("-", " ")} for ${theme.toLowerCase()}`;
    costs[id] = rnd() < 0.2 ? { always_on: null, on_use: null } : { always_on: Math.floor(20 + rnd() * 80), on_use: Math.floor(300 + rnd() * 5000) };
    if (kind === "hook") costs[id] = { always_on: null, on_use: null }; // a real scan cannot know hook output until it runs
    if (hub && kind === "skill" && rnd() < 0.6) relations.push({ source: hub, target: id, kind: "contains" });
  }
  clusters.push({ name: theme, item_ids: ids });
});
// a few cross-cluster Relations
const skills = items.filter((i) => i.kind !== "plugin");
for (let i = 0; i < 8; i++) relations.push({ source: pick(skills).id, target: pick(skills).id, kind: pick(["uses", "triggers"]) });
// Plugin costs and Overlaps come from their own seeded stream, so adding them leaves every name and Relation above unchanged.
let seed2 = 11;
const rnd2 = () => ((seed2 = (seed2 * 1664525 + 1013904223) % 4294967296) / 4294967296);
const pick2 = (a) => a[Math.floor(rnd2() * a.length)];
for (const it of items) if (it.kind === "plugin") costs[it.id] = { always_on: Math.floor(30 + rnd2() * 70), on_use: null };
const clusterOf = new Map(clusters.flatMap((c) => c.item_ids.map((id) => [id, c.name])));
const real = items.filter((i) => i.kind === "skill" || i.kind === "agent");
const seen = new Set();
const overlaps = [];
// verdict, how many, reason; about three quarters of each stay inside one cluster
for (const [verdict, count, reason] of [["duplicate", 8, "Same steps and trigger wording; one could go."], ["wrapper", 6, "Mostly a thin call into the other Item."], ["overlap", 16, "Half of the instructions cover the same ground."], ["distinct", 6, "Look alike by name only; they do different work."]]) {
  for (let n = 0; n < count; ) {
    const a = pick2(real);
    const same = rnd2() < 0.75;
    const pool = real.filter((b) => b !== a && (clusterOf.get(b.id) === clusterOf.get(a.id)) === same);
    if (!pool.length) continue;
    const b = pick2(pool), [x, y] = verdict === "wrapper" ? [a.id, b.id] : [a.id, b.id].sort(), key = [a.id, b.id].sort().join("|");
    if (seen.has(key)) continue;
    seen.add(key);
    overlaps.push({ a_id: x, b_id: y, verdict, reason: `${reason.replace(/\.$/, "")} (${a.name} and ${b.name}).` });
    n++;
  }
}
overlaps.sort((p, q) => p.a_id.localeCompare(q.a_id) || p.b_id.localeCompare(q.b_id));
const fixed = relations.filter((r) => r.source !== r.target);
fs.writeFileSync(new URL("demo-250.json", import.meta.url), JSON.stringify({ items, relations: fixed, labels, clusters, costs, overlaps, warnings: [] }, null, 1) + "\n");
console.log(overlaps.length, "overlaps,", items.length, "items", fixed.length, "relations", clusters.length, "clusters");
