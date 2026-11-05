// Self-check for the cluster health lines in the card (docs/plans/whatif.md #71), on invented values only.
import { strict as assert } from "node:assert";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

const vite = await createServer({ server: { middlewareMode: true, watch: null, ws: false }, appType: "custom" });
try {
  const { ClusterCard } = await vite.ssrLoadModule("/src/components/ClusterCard.tsx");
  const node = (name, always_on, count) => ({ id: name, name, kind: "skill", unknown: always_on == null, cost: { always_on, on_use: null }, usage: { count }, degree: 0 });
  const mk = (name, members) => ({ name, members });
  const [a, b] = [node("a", 300, 1), node("b", 100, 99)];
  const cA = mk("Big", [a]), cB = mk("Small", [b]);
  const model = { nodes: [a, b], clusters: [cA, cB], overlaps: [], usageWindow: { files: 3, first: null, last: null } };
  const html = (c, removed) => renderToStaticMarkup(createElement(ClusterCard, { cluster: c, model, leaving: false, focusTitle: false, onBack() {}, onItem() {}, onPreview() {}, onPair() {}, onGone() {}, removed }));
  assert.match(html(cA), /1% of all recorded uses/);
  assert.match(html(cA), /Costliest cluster: 1 of 2/);
  assert.match(html(cB), /99% of all recorded uses/);
  assert.match(html(cB), /Costliest cluster: 2 of 2/);
  assert.doesNotMatch(html(cB, new Set([b])), /Costliest cluster/); // nothing known left after removal
  console.log("Cluster health card lines pass.");
} finally {
  await vite.close();
}
