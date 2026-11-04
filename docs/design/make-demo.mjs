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
    if (hub && kind === "skill" && rnd() < 0.6) relations.push({ source: hub, target: id, kind: "contains" });
  }
  clusters.push({ name: theme, item_ids: ids });
});
// a few cross-cluster Relations
const skills = items.filter((i) => i.kind !== "plugin");
for (let i = 0; i < 8; i++) relations.push({ source: pick(skills).id, target: pick(skills).id, kind: pick(["uses", "triggers"]) });
const fixed = relations.filter((r) => r.source !== r.target);
fs.writeFileSync(new URL("demo-250.json", import.meta.url), JSON.stringify({ items, relations: fixed, labels, clusters, costs, warnings: [] }, null, 1) + "\n");
console.log(items.length, "items", fixed.length, "relations", clusters.length, "clusters");
