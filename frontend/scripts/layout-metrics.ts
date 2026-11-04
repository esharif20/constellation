// Layout metrics, no browser: node scripts/layout-metrics.ts  (npm run layout:check)
// Builds the model for the invented demos at desktop and phone size, then checks the layout and the cluster-name placer.
// `--legacy` runs the same checks on a replica of the old force layout (global charge, centroid pull, random seeds)
// so the numbers before and after can be compared.
import { readFileSync } from "node:fs";
import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY } from "d3-force";
import { strict as assert } from "node:assert";
import { buildModel, clusterSummary, groupWarnings, rankMembers, costRadius, RMAX, RMIN, RUNK, type Constellation, type GNode, type Model } from "../src/graph/model.ts";
import { flightMs, flightPath } from "../src/graph/flight.ts";
import { fitView, focusView, GAP, haloOf, K, type View } from "../src/graph/layout.ts";
import { searchItems } from "../src/graph/search.ts";
import { didYouMean, matchClusters, mergeResults, warningMention } from "../src/graph/searchMerge.ts";
import { chooseSpot, hit, type Box } from "../src/graph/names.ts";

const legacy = process.argv.includes("--legacy");
const load = (f: string) => JSON.parse(readFileSync(new URL(`../../docs/design/${f}`, import.meta.url), "utf8")) as Constellation;

// old layout: what StarMap did before layout.ts (forces and numbers copied from it)
function legacyLayout(m: Model, tall: number) {
  const rnd = Math.random;
  [...m.clusters].sort((a, b) => b.members.length - a.members.length).forEach((c, i) => {
    const t = i * 2.39996, rad = 60 * Math.sqrt(i);
    for (const n of c.members) {
      n.x = (Math.cos(t) * rad + (rnd() - 0.5) * 30) / Math.sqrt(tall);
      n.y = (Math.sin(t) * rad + (rnd() - 0.5) * 30) * Math.sqrt(tall);
    }
  });
  const sim = forceSimulation(m.nodes).stop().alphaDecay(0.025).velocityDecay(0.3).alphaMin(0);
  sim.force("link", forceLink(m.links).distance((l) => (l.kind === "contains" ? 34 : 60)).strength(0.5));
  sim.force("charge", forceManyBody().strength(-55).distanceMax(320));
  sim.force("collide", forceCollide<(typeof m.nodes)[number]>((n) => n.r + 3));
  sim.force("x", forceX().strength(0.06 * tall));
  sim.force("y", forceY().strength(0.06 / tall));
  const pull = (alpha: number) => {
    for (const c of m.clusters) {
      let x = 0, y = 0;
      for (const n of c.members) { x += n.x!; y += n.y!; }
      x /= c.members.length; y /= c.members.length;
      for (const n of c.members) { n.vx! += (x - n.x!) * 0.12 * alpha; n.vy! += (y - n.y!) * 0.12 * alpha; }
    }
  };
  pull.initialize = () => {};
  sim.force("cluster", pull);
  for (let i = 0; i < 660; i++) sim.tick();
  // halos as the old painter drew them: member RMS * 1.5 + 18
  for (const c of m.clusters) {
    let x = 0, y = 0, d2 = 0;
    for (const n of c.members) { x += n.x!; y += n.y!; }
    c.x = x / c.members.length; c.y = y / c.members.length;
    for (const n of c.members) d2 += (n.x! - c.x) ** 2 + (n.y! - c.y) ** 2;
    c.r = Math.sqrt(d2 / c.members.length) * 1.5 + 18;
  }
}

// costRadius self-check: floor, cap, area proportionality, unknown
assert.equal(costRadius(0, 100), RMIN);
{
  const g = groupWarnings([
    "Offline: no labels.",
    "frontmatter is not valid YAML, read name and description leniently (~/a/SKILL.md)",
    "frontmatter is not valid YAML, read name and description leniently (~/b/SKILL.md)",
    "skipped skill 'x': no description (~/c/SKILL.md)",
    "no frontmatter in ~/d/SKILL.md",
    "could not label 'y': boom",
    "something new",
  ]);
  assert.deepEqual(g.map((x) => x.id), ["missing", "label", "loose", "bare", "other"]);
  assert.deepEqual(g.find((x) => x.id === "loose")!.items.map((i) => i.path), ["~/a/SKILL.md", "~/b/SKILL.md"]);
  assert.deepEqual(g[0].items, [{ text: "skill 'x': no description (~/c/SKILL.md)", path: "~/c/SKILL.md" }]);
  assert.equal(g.find((x) => x.id === "bare")!.items[0].path, "~/d/SKILL.md");
  assert.equal(groupWarnings(["Offline: x"]).length, 0); // a mode, not a warning
}
// clusterSummary self-check: unknown never added in (all unknown is null, not 0), top 3 by cost then name, unused counts tracked Items only
{
  const mk = (name: string, always_on: number | null, usage?: number): GNode => ({ name, kind: "skill", unknown: always_on == null, cost: { always_on, on_use: null }, usage: usage == null ? undefined : { count: usage, last_used: null } }) as GNode;
  const sum = (members: GNode[], usageWindow: Model["usageWindow"] = null) => clusterSummary({ members } as never, { overlaps: [], usageWindow });
  const s = sum([mk("b", 10, 0), mk("a", 10, 3), mk("z", null), mk("c", 5), mk("d", 0), mk("e", 7)], { files: 3, first: null, last: null, skipped: 0 });
  assert.equal(s.known, 32);
  assert.equal(s.unknown, 1);
  assert.deepEqual(s.top.map((n) => n.name), ["a", "b", "e"]);
  assert.deepEqual(s.unused, { tracked: 2, unseen: 1 });
  assert.equal(sum([mk("x", null), mk("y", null)]).known, null);
  assert.equal(sum([mk("x", 0)]).known, 0);
  assert.equal(sum([mk("x", null)]).top.length, 0);
  assert.equal(sum([mk("x", 1, 1)]).unused, null); // no usage window
}
assert.equal(costRadius(100, 100), RMAX);
assert.equal(costRadius(1e6, 100), RMAX);
assert.equal(costRadius(null, 100), RUNK);
assert.equal(costRadius(undefined, 100), RUNK);
assert.ok(Math.abs(costRadius(100, 100) / costRadius(25, 100) - 2) < 1e-9); // 4x the cost, 2x the radius

// Cluster focus (docs/design/cluster-focus.md section 12): the camera target of every cluster, the flight to it, and member names there.
function focusChecks(m: Model, fv: View, phone: boolean, top: number, bottom: number, W: number, H: number) {
  const left = phone ? 0 : 364, bot = phone ? Math.max(bottom, 0.4 * H + 8) : bottom, pad = phone ? 14 : 36;
  const ins = { top, bottom: bot, left, right: 0 };
  const L = left + pad, R = W - pad, T = top + pad, B = H - bot - pad;
  let kRange = 0, outside = 0, small = 0, capped = 0, clamped = 0, flightEnds = 0, flightMs_ = 0, named = 0, members = 0, namedMin = 1, nameClash = 0;
  const minR = phone ? 90 : 120;
  for (const c of m.clusters) {
    const halo = { x: c.x, y: c.y, r: c.r }, v = focusView(halo, ins, W, H, fv.k), ratio = c.r * v.k;
    if (v.k < fv.k - 1e-9 || v.k > fv.k * 10 + 1e-9) kRange++;
    const atMax = v.k >= fv.k * 10 - 1e-9, atMin = v.k <= fv.k + 1e-9 && c.r * fv.k > (0.86 * Math.min(R - L, B - T)) / 2;
    if (atMax) capped++;
    if (atMin) clamped++; // the circle is bigger than the free box even at the fitted zoom: the flight is a pan
    const cx = W / 2 + (c.x - v.x) * v.k, cy = H / 2 + (c.y - v.y) * v.k;
    if (!atMin && (cx - ratio < L - 0.5 || cx + ratio > R + 0.5 || cy - ratio < T - 0.5 || cy + ratio > B + 0.5)) outside++;
    if (!atMax && !atMin && ratio < minR) small++;
    // flight from the fitted view: exact endpoints, bounded duration
    const i = flightPath(fv, v, W), p0 = i(0), p1 = i(1), ms = flightMs(i.duration);
    if (Math.hypot(p0[0] - fv.x, p0[1] - fv.y) * fv.k > 0.5 || Math.hypot(p1[0] - v.x, p1[1] - v.y) * v.k > 0.5 || Math.abs(W / p1[2] - v.k) / v.k * W > 0.5 || ms < 700 || ms > 1300) flightEnds++;
    flightMs_ = Math.max(flightMs_, ms);
    // member names at the landing view: rank order, 22-char cut, half-em widths, none over a star or another name
    const sxy = (n: GNode) => [W / 2 + (n.x! - v.x) * v.k, H / 2 + (n.y! - v.y) * v.k] as const;
    const rad = (n: GNode) => n.r * Math.min(1, Math.sqrt(2.5 / v.k)) * v.k;
    const stars: Box[] = m.nodes.map((n) => { const [x, y] = sxy(n), r = rad(n) + 2; return [x - r, y - r, x + r, y + r]; });
    const placed: Box[] = [[0, 0, W, top], [0, 0, left, H], [0, H - bot, W, H]];
    let got = 0;
    for (const n of rankMembers(c)) {
      const [x, y] = sxy(n), w = 0.5 * 12 * Math.min(22, n.name.length), y0 = y + rad(n) + 5;
      const box: Box = [x - w / 2 - 2, y0, x + w / 2 + 2, y0 + 14];
      if (box[0] < 0 || box[2] > W || placed.some((p) => hit(box, p)) || stars.some((s, j) => m.nodes[j] !== n && hit(box, s))) continue;
      placed.push(box);
      got++;
    }
    for (let a = 3; a < placed.length; a++) for (let b = a + 1; b < placed.length; b++) if (hit(placed[a], placed[b])) nameClash++;
    named += got; members += c.members.length; namedMin = Math.min(namedMin, got / c.members.length);
  }
  const share = named / members;
  return { focusK: kRange, focusOutside: outside, focusSmall: small, focusCapped: capped, focusPan: clamped, flightBad: flightEnds, flightMax: Math.round(flightMs_), focusNamed: +(share * 100).toFixed(0), focusNamedMin: +(namedMin * 100).toFixed(0), focusClash: nameClash, focusShare: share };
}

function measure(file: string, W: number, H: number) {
  const tall = Math.max(0.55, Math.min(2, H / W));
  const m = buildModel(load(file), H / W);
  if (legacy) legacyLayout(m, tall);
  const hash = (mm: Model) => mm.nodes.map((n) => `${n.id}:${Math.round(n.x! * 10)},${Math.round(n.y! * 10)}`).join("|");
  const first = hash(m);
  const second = hash(buildModel(load(file), H / W));

  let minDist = Infinity, overlaps = 0;
  for (let i = 0; i < m.nodes.length; i++) for (let j = i + 1; j < m.nodes.length; j++) {
    const a = m.nodes[i], b = m.nodes[j], d = Math.hypot(a.x! - b.x!, a.y! - b.y!);
    minDist = Math.min(minDist, d);
    if (d < a.r + b.r + 1) overlaps++;
  }
  const inside = m.nodes.filter((n) => !n.cluster || Math.hypot(n.x! - n.cluster.x, n.y! - n.cluster.y) + n.r <= n.cluster.r + 0.5).length / m.nodes.length;
  // size rule: known r in [RMIN, RMAX], unknown exactly RUNK, and r never falls as cost rises
  const known = m.nodes.filter((n) => !n.unknown).sort((a, b) => a.cost!.always_on! - b.cost!.always_on!);
  let sizeRule = m.nodes.filter((n) => (n.unknown ? n.r !== RUNK : n.r < RMIN || n.r > RMAX)).length;
  for (let i = 1; i < known.length; i++) if (known[i].r < known[i - 1].r) sizeRule++;
  const data = load(file), wantOverlaps = (data.overlaps ?? []).filter((o) => o.verdict !== "distinct" && m.nodes.some((n) => n.id === o.a_id) && m.nodes.some((n) => n.id === o.b_id)).length;
  const overlapLinks = m.overlaps.length === wantOverlaps ? 0 : 1;
  // slot gap: clear space between two slots of one cluster, before any force runs (replays the spiral in layout.ts)
  let slotGap = Infinity;
  for (const c of m.clusters) {
    const slots: { x: number; y: number; r: number }[] = [];
    let used = 0;
    [...c.members].sort((a, b) => b.degree - a.degree || a.id.localeCompare(b.id)).forEach((n, i) => {
      const area = (n.r + GAP) ** 2, rad = K * Math.sqrt(used + area / 2), t = i * 2.39996;
      used += area;
      slots.push({ x: Math.cos(t) * rad, y: Math.sin(t) * rad, r: n.r });
    });
    for (let i = 0; i < slots.length; i++) for (let j = i + 1; j < slots.length; j++) slotGap = Math.min(slotGap, Math.hypot(slots[i].x - slots[j].x, slots[i].y - slots[j].y) - slots[i].r - slots[j].r);
  }
  let circleClash = 0;
  for (let i = 0; i < m.clusters.length; i++) for (let j = i + 1; j < m.clusters.length; j++) {
    const a = m.clusters[i], b = m.clusters[j];
    if (Math.hypot(a.x - b.x, a.y - b.y) < a.r + b.r + 20) circleClash++;
  }

  // halo: at rest it is the home circle; one member moved by (d, 0) shifts the centre by d / n; the radius stays within 1.4 r
  let haloBad = 0;
  if (!legacy) {
    for (const c of m.clusters) {
      const h = haloOf(c);
      if (Math.abs(h.x - c.x) > 1e-9 || Math.abs(h.y - c.y) > 1e-9 || Math.abs(h.r - c.r) > 1e-9) haloBad++;
      const n = c.members[0], d = 40;
      n.x! += d;
      const g = haloOf(c);
      n.x! -= d;
      if (Math.abs(g.x - c.x - d / c.members.length) > 1e-6 || Math.abs(g.y - c.y) > 1e-6 || g.r > 1.4 * c.r + 1e-9 || g.r < c.r) haloBad++;
    }
  }

  // the fitted view (fitView, shared with StarMap), and the name placer run over it
  const phone = W <= 640, top = phone ? 146 : 72, bottom = phone ? 100 : 56;
  const fv = fitView(m.nodes, m.clusters, { top, bottom, left: 0, right: 0 }, W, H), k = fv.k;
  const sx = (x: number) => W / 2 + (x - fv.x) * k, sy = (y: number) => H / 2 + (y - fv.y) * k;
  const stars: Box[] = m.nodes.map((n) => { const R = n.r * k + 4, x = sx(n.x!), y = sy(n.y!); return [x - R, y - R, x + R, y + R]; });
  const placed: Box[] = [[0, 0, W, top], [0, H - bottom, W, H]];
  const eligible = m.clusters.filter((c) => c.members.length >= 5).sort((a, b) => b.members.length - a.members.length);
  let named = 0, labelOnStar = 0;
  const boxes: Box[] = [];
  for (const c of eligible) {
    const size = (phone ? 12 : 13) + 4 * Math.min(1, Math.max(0, (c.members.length - 3) / 20));
    const w = 0.5 * size * c.name.length, h = size * 1.15; // text measured as half an em per character
    const spot = chooseSpot({ cx: sx(c.x), cy: sy(c.y), r: c.r * k, w, h, pick: 0, allowed: 0, W, H, top, bottom: bottom, right: 0, placed, obstacles: stars });
    if (spot) { named++; placed.push(spot.box); boxes.push(spot.box); }
  }
  for (const b of boxes) for (const s of stars) if (hit(b, s)) labelOnStar++;
  let labelClash = 0;
  for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) if (hit(boxes[i], boxes[j])) labelClash++;
  const f = focusChecks(m, fv, phone, top, bottom, W, H);
  return { ...f, items: m.nodes.length, clusters: m.clusters.length, minDist: +minDist.toFixed(2), starOverlaps: overlaps, inside: +(inside * 100).toFixed(1), circleClash, named: `${named}/${eligible.length}`, namedShare: eligible.length ? named / eligible.length : 1, labelOnStar, labelClash, deterministic: first === second, sizeRule, overlapLinks, slotGap: +slotGap.toFixed(2), haloBad };
}

// forgiving search, on invented Items
{
  const mk = (name: string, description: string, kind = "skill") => ({ name, description, kind });
  const items = [mk("frontend-design", "Build distinctive interfaces"), mk("ponytail", "Lazy senior developer mode"), mk("pony-ride", "Horse booking"), mk("tail-logs", "Follow a log file"), mk("pdf-tools", "Read and fill PDF files"), mk("talk-to-me", "Voice chat helper")];
  const top = (q: string) => searchItems(items, q)[0]?.item.name;
  for (const q of ["where is pony tail", "ponytail", "pony-tail", "ponyatil", "Pony Tail?"]) assert.equal(top(q), "ponytail", q);
  assert.equal(top("frontend design"), "frontend-design");
  assert.equal(top("find my frontend-design skill"), "frontend-design");
  assert.equal(top("pdf"), "pdf-tools");
  assert.equal(top("skill"), "frontend-design"); // a lone filler word is kept
  assert.equal(searchItems(items, "pony")[0].why, "name starts with it");
  assert.equal(searchItems(items, "ponyatil")[0].why, 'close to "ponytail"');
  assert.equal(searchItems(items, "fill files")[0].why, "in description");
  assert.deepEqual(searchItems(items, "qwxzvkj"), []);
  assert.deepEqual(searchItems(items, "where is the"), []);
  assert.ok(searchItems(items, "pony").length <= 8);
}

// merging server results with local, cluster matching, did-you-mean
{
  const mk = (id: string, name: string, description = "") => ({ id, name, description, kind: "skill" });
  const items = [mk("a", "ponytail", "Lazy mode"), mk("b", "shadcn", "UI components"), mk("c", "pptx", "Make slides"), mk("d", "pdf-tools", "Fill forms")];
  const byId = new Map(items.map((i) => [i.id, i]));
  const local = searchItems(items, "pdf");
  const merged = mergeResults(local, { results: [{ id: "d", why: "name" }, { id: "c", why: "similar meaning" }, { id: "b", why: "in description" }, { id: "zz", why: "name" }], note: null }, byId);
  assert.deepEqual(merged.map((r) => [r.item.id, r.related]), [["d", false], ["b", false], ["c", true]]); // deduped, unknown ids dropped, Related last
  assert.equal(merged[0].why, "name starts with it"); // the instant local reason wins
  assert.deepEqual(mergeResults(searchItems(items, "pdf"), null, byId).map((r) => r.item.id), ["d"]); // API down: local alone
  const clusters = [{ name: "Documents" }, { name: "Frontend design" }, { name: "Git workflow" }];
  assert.deepEqual(matchClusters(clusters, "document").map((c) => c.name), ["Documents"]);
  assert.deepEqual(matchClusters(clusters, "frontend").map((c) => c.name), ["Frontend design"]);
  assert.deepEqual(matchClusters(clusters, "documnets").map((c) => c.name), ["Documents"]); // typo
  assert.deepEqual(matchClusters(clusters, "qwxzvkj"), []);
  assert.equal(didYouMean("shadnc", "shadcn"), "shadcn");
  assert.equal(didYouMean("shadcn", "shadcn"), null); // already right
  assert.equal(didYouMean("sha", "shadcn"), null); // too short to guess
  assert.equal(didYouMean("pytail", "ponytail"), "ponytail");
  assert.equal(didYouMean("slides", "shadcn"), null); // far off
  assert.equal(didYouMean("x", undefined), null);
  assert.equal(warningMention(["Skipped skill ripgrep: bad frontmatter"], "ripgrep"), "Skipped skill ripgrep: bad frontmatter");
  assert.equal(warningMention(["Skipped skill ripgrep"], "gh"), null);
}

let failed = false;
const rows: Record<string, unknown>[] = [];
for (const file of ["demo.json", "demo-250.json", "demo-offline.json"]) {
  for (const [W, H] of [[1440, 900], [390, 844]]) {
    const r = measure(file, W, H);
    rows.push({ file, size: `${W}x${H}`, ...r });
    const bad = r.starOverlaps > 0 || r.inside < 98 || r.circleClash > 0 || r.labelClash > 0 || r.labelOnStar > 0 || r.namedShare < (W <= 640 ? 0.7 : 0.8) || !r.deterministic || r.sizeRule > 0 || r.overlapLinks > 0 || r.slotGap < GAP - 0.5 || r.haloBad > 0 || r.focusK > 0 || r.focusOutside > 0 || r.focusSmall > 0 || r.flightBad > 0 || r.focusClash > 0 || r.focusShare < (W <= 640 ? 0.4 : 0.6);
    if (bad) failed = true;
  }
}
console.log(legacy ? "OLD force layout (replica)" : "NEW slot layout");
console.table(rows);
if (failed && !legacy) { console.error("layout check failed"); process.exit(1); }
