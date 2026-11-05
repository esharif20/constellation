// Self-check for hover intent and badge disclosure helpers, invented values only.
import { strict as assert } from "node:assert";
import { createServer } from "vite";

const vite = await createServer({ server: { middlewareMode: true, watch: null, ws: false }, appType: "custom" });
try {
  const { hoverTarget } = await vite.ssrLoadModule("/src/graph/hover.ts");
  const { badgeWanted } = await vite.ssrLoadModule("/src/graph/badge.ts");
  const pos = { a: { x: 0, y: 0, r: 4 }, b: { x: 20, y: 0, r: 4 }, tiny: { x: 100, y: 0, r: 1 } };
  const at = (n) => pos[n];
  assert.equal(hoverTarget(null, "a", { x: 1, y: 0 }, at), "a"); // nothing shown: take the candidate
  assert.equal(hoverTarget(null, null, { x: 1, y: 0 }, at), null);
  assert.equal(hoverTarget("a", "b", { x: 9, y: 0 }, at), "a"); // b barely closer (11 vs 9 is farther): stay
  assert.equal(hoverTarget("a", "b", { x: 11, y: 0 }, at), "a"); // 9 vs 11 is not 30% closer: stay
  assert.equal(hoverTarget("a", "b", { x: 13, y: 0 }, at), "b"); // 7 vs 13: clearly closer: switch
  assert.equal(hoverTarget("a", null, { x: 10, y: 0 }, at), "a"); // in the gap but within the padded radius (17): keep
  assert.equal(hoverTarget("a", null, { x: 18, y: 0 }, at), null); // clearly left (radius floor 9 + margin 8 = 17): hide
  assert.equal(hoverTarget("tiny", null, { x: 100 + 16, y: 0 }, at), "tiny"); // tiny star keeps a 9 px hit radius
  assert.equal(hoverTarget("tiny", null, { x: 100 + 18, y: 0 }, at), null);
  assert.equal(hoverTarget("a", "b", { x: 40, y: 0 }, at), "b"); // far outside the shown star: follow the canvas
  assert.equal(badgeWanted({ hovered: false, focused: false, z: 1 }), false); // zoomed out: names only
  assert.equal(badgeWanted({ hovered: true, focused: false, z: 1 }), true);
  assert.equal(badgeWanted({ hovered: false, focused: true, z: 1 }), true);
  assert.equal(badgeWanted({ hovered: false, focused: false, z: 1.4 }), true); // room to spare
  console.log("Hover intent and badge disclosure pass.");
} finally {
  await vite.close();
}
