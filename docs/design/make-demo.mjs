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
// Usage and hook weights come from a third seeded stream, so every name, Relation and Overlap above stays unchanged.
// Only skills and agents get a usage entry (hooks and plugins are not tracked, which is different from count 0).
let seed3 = 23;
const rnd3 = () => ((seed3 = (seed3 * 1664525 + 1013904223) % 4294967296) / 4294967296);
const usage = {}, hook_weights = {};
const day = (back) => new Date(Date.UTC(2026, 10, 4) - back * 864e5).toISOString().slice(0, 10);
for (const it of items) {
  if (it.kind === "skill" || it.kind === "agent") usage[it.id] = rnd3() < 0.28 ? { count: 0, last_used: null } : { count: 1 + Math.floor(rnd3() * rnd3() * 60), last_used: day(Math.floor(rnd3() * 30)) };
  if (it.kind === "hook") { const r = rnd3(); hook_weights[it.id] = r < 0.25 ? { bytes: null, tokens: null } : r < 0.6 ? { bytes: 400 + Math.floor(rnd3() * 5000), tokens: null } : (b => ({ bytes: b, tokens: Math.round(b / 3.6) }))(400 + Math.floor(rnd3() * 5000)); }
}
const usage_window = { files: 132, first: "2026-10-05", last: "2026-11-04", skipped: 0 };
const fixed = relations.filter((r) => r.source !== r.target);
fs.writeFileSync(new URL("demo-250.json", import.meta.url), JSON.stringify({ items, relations: fixed, labels, clusters, costs, overlaps, hook_weights, usage, usage_window, warnings: [] }, null, 1) + "\n");
console.log(overlaps.length, "overlaps,", items.length, "items", fixed.length, "relations", clusters.length, "clusters");

// Label and tooltip fixtures (docs/design/labels.md 12.7): four invented Items added to all three demos, after everything above so
// no existing name, Relation or Overlap changes. Two names are over 22 chars (the canvas cut and the full name in the tooltip) and two are
// `disabled: true` (a switched-off plugin and what it contains: the "Disabled" badge). Idempotent: skipped when already present.
for (const [file, indent] of [["demo.json", 2], ["demo-offline.json", 2], ["demo-250.json", 1]]) {
  const url = new URL(file, import.meta.url), d = JSON.parse(fs.readFileSync(url, "utf8"));
  if (d.items.some((i) => i.id === "skill:extra:quarterly-ledger-reconciliation-helper")) continue;
  const known = d.costs && Object.values(d.costs).some((c) => c.always_on != null); // offline demos have no cost to give
  const big = d.clusters.filter((c) => c.item_ids.length >= 8).slice(2); // clusters 2 and 3: the choice that keeps every existing layout:check floor (the phone named share is 15/19 on demo-250)
  const add = (cluster, it, cost) => {
    d.items.push({ ...it, source: `~/.claude/${it.kind}s/${it.name}` });
    cluster.item_ids.push(it.id);
    if (d.labels && Object.keys(d.labels).length) d.labels[it.id] = it.description.replace(/\.$/, "");
    if (d.costs) d.costs[it.id] = known ? cost : { always_on: null, on_use: null };
    if (d.usage && it.kind !== "plugin") d.usage[it.id] = it.disabled ? { count: 0, last_used: null } : { count: 3, last_used: "2026-11-02" };
  };
  add(big[0], { id: "skill:extra:quarterly-ledger-reconciliation-helper", kind: "skill", name: "quarterly-ledger-reconciliation-helper", description: "Use when closing the quarter and matching ledgers." }, { always_on: 410, on_use: 2600 });
  add(big[0], { id: "agent:extra:lighthouse-lamp-maintenance-scheduler", kind: "agent", name: "lighthouse-lamp-maintenance-scheduler", description: "Plans lamp upkeep rounds around the tides." }, { always_on: 150, on_use: 900 });
  add(big[1], { id: "plugin:extra:idle-beekeeping-bundle", kind: "plugin", name: "idle-beekeeping-bundle", description: "A bundle for hive inspection, switched off.", disabled: true }, { always_on: 90, on_use: null });
  add(big[1], { id: "skill:extra:idle-hive-inspector", kind: "skill", name: "idle-hive-inspector", description: "Use when inspecting a hive. Switched off with its plugin.", disabled: true }, { always_on: 60, on_use: 700 });
  d.relations.push({ source: "plugin:extra:idle-beekeeping-bundle", target: "skill:extra:idle-hive-inspector", kind: "contains" });
  if (d.overlaps) { // a duplicate of an existing skill in the same cluster, so the Overlap badge and arc can be screenshotted
    const twin = d.items.find((i) => i.kind === "skill" && big[0].item_ids.includes(i.id) && !i.id.includes(":extra:"));
    d.overlaps.push({ a_id: twin.id, b_id: "skill:extra:quarterly-ledger-reconciliation-helper", verdict: "duplicate", reason: "Same steps and trigger wording; one could go." });
  }
  fs.writeFileSync(url, JSON.stringify(d, null, indent) + "\n");
}

// Per-project fixtures (docs/plans/per-project.md 5): two invented projects, appended after every other stream so no existing name,
// Relation, Overlap or usage number changes. `alpha-shop` (p1) is the scanned repo. Three project-scope Items are added (one local MCP
// server with no key), then global skills with usage get per-project counts: one used almost only in p1 (a high-confidence move), one only in
// p2 (medium), one split between both (no move), so the Inspector rows and the Scope group all have something to show. Idempotent.
for (const [file, indent] of [["demo.json", 2], ["demo-offline.json", 2], ["demo-250.json", 1]]) {
  const url = new URL(file, import.meta.url), d = JSON.parse(fs.readFileSync(url, "utf8"));
  if (d.projects) continue;
  d.projects = { p1: "alpha-shop", p2: "thesis" };
  d.current_project = "p1";
  const big = d.clusters.filter((c) => c.item_ids.length >= 8);
  const mk = (cluster, kind, nm, project, desc) => {
    const id = `${kind}:proj:${nm}`;
    d.items.push({ id, kind, name: nm, description: desc, source: kind === "mcp_server" ? `.mcp.json#${nm}` : `.claude/${kind}s/${nm}`, scope: "project", ...(project ? { project } : {}) });
    cluster.item_ids.push(id);
    if (d.labels && Object.keys(d.labels).length) d.labels[id] = desc.replace(/\.$/, "");
    if (d.costs) d.costs[id] = Object.values(d.costs).some((c) => c.always_on != null) ? { always_on: 70, on_use: 800 } : { always_on: null, on_use: null };
    if (d.usage) d.usage[id] = { count: 4, last_used: "2026-11-01" };
    return id;
  };
  mk(big[Math.min(0 + 4, big.length - 1)], "skill", "cart-checkout-audit", "p1", "Use when reviewing the alpha-shop checkout flow.");
  mk(big[Math.min(1 + 4, big.length - 1)], "agent", "thesis-citation-checker", "p2", "Checks citations in the thesis draft.");
  mk(big[Math.min(2 + 4, big.length - 1)], "mcp_server", "shop-catalog-db", null, "Local catalog database for the shop.");
  const inPlugin = new Set(d.relations.filter((r) => r.kind === "contains").map((r) => r.target));
  const pool = d.items.filter((i) => i.kind === "skill" && !i.scope && !i.disabled && !inPlugin.has(i.id) && d.usage?.[i.id]?.count >= 6 && !(d.overlaps ?? []).some((o) => o.a_id === i.id || o.b_id === i.id));
  d.usage_by_project = {};
  const set = (it, byProject) => {
    d.usage_by_project[it.id] = Object.fromEntries(Object.entries(byProject).map(([k, count]) => [k, { count, last_used: d.usage[it.id].last_used }]));
    d.usage[it.id].count = Math.max(d.usage[it.id].count, Object.values(byProject).reduce((a, b) => a + b, 0));
  };
  if (pool[0]) set(pool[0], { p1: 18, p2: 1 });
  if (pool[1]) set(pool[1], { p2: 5 });
  if (pool[2]) set(pool[2], { p1: 6, p2: 5 });
  fs.writeFileSync(url, JSON.stringify(d, null, indent) + "\n");
}
