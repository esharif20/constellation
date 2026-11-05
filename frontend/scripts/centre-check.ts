// Centre rule, no browser: node scripts/centre-check.ts  (npm run centre:check)
// Every cluster of 3 or more (bar "Other") has an anchor of degree >= 2 near its centre, or a layout-only centre that is
// exactly (c.x, c.y), with no member inside its claimed disc. The centre is not an Item, and layout is deterministic.
import { readFileSync } from "node:fs";
import { strict as assert } from "node:assert";
import { buildModel, type Constellation } from "../src/graph/model.ts";
import { CORE_R, GAP, K, hubless } from "../src/graph/layout.ts";
import { searchItems } from "../src/graph/search.ts";

const load = (f: string) => JSON.parse(readFileSync(new URL(`../../docs/design/${f}`, import.meta.url), "utf8")) as Constellation;
assert.ok(hubless("x", [0, 1, 1]) && !hubless("x", [0, 2]) && !hubless("Other", [0]));
let cores = 0, anchors = 0;
for (const f of ["demo-250.json", "demo.json", "demo-offline.json"]) {
  for (const tall of [0.6, 1.8]) {
    const data = load(f), m = buildModel(data, tall), again = buildModel(data, tall);
    assert.equal(m.nodes.length, data.items.length, "the centre is not a node");
    assert.ok(m.nodes.every((n) => n.id && data.items.some((i) => i.id === n.id)), "every node is an Item");
    assert.deepEqual(m.nodes.map((n) => [n.x, n.y]), again.nodes.map((n) => [n.x, n.y]), `${f} deterministic`);
    assert.deepEqual(m.clusters.map((c) => [c.x, c.y, c.r, c.core]), again.clusters.map((c) => [c.x, c.y, c.r, c.core]));
    for (const c of m.clusters.filter((c) => c.name !== "Other")) {
      const top = [...c.members].sort((a, b) => b.degree - a.degree || a.id.localeCompare(b.id))[0];
      assert.equal(!!c.core, top.degree < 2, `${c.name}: core iff no member of degree >= 2`);
      if (c.core) {
        cores++;
        for (const n of c.members) assert.ok(Math.hypot(n.x! - c.x, n.y! - c.y) - n.r >= CORE_R, `${c.name}: ${n.id} inside the centre`);
      } else {
        anchors++;
        assert.ok(Math.hypot(top.x! - c.x, top.y! - c.y) <= 2 * K * (top.r + GAP) + 10, `${c.name}: anchor far from centre`);
      }
    }
    assert.ok(m.clusters.find((c) => c.name === "Other")?.core !== true, "Other has no centre");
    assert.deepEqual(searchItems(data.items, "centre").filter((r) => !/centre/i.test(r.item.name + r.item.description)), []);
  }
}
assert.ok(cores > 0 && anchors > 0, `exercise both branches (${cores} centres, ${anchors} anchors)`);
console.log(`centre-check ok: ${cores} synthetic centres, ${anchors} anchored clusters`);
