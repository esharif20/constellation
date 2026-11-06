// Self-check for the Explain card upgrade: use-vs-pay maths and cluster share. Invented values only.
import { strict as assert } from "node:assert";
import { createServer } from "vite";

const vite = await createServer({ server: { middlewareMode: true, watch: null, ws: false }, appType: "custom" });
try {
  const { useVsPay, pct } = await vite.ssrLoadModule("/src/components/ExplainCard.tsx");
  const node = (id, always_on) => ({ id, cost: always_on === undefined ? undefined : { always_on, on_use: null } });
  const nodes = [node("a", 100), node("b", 300), node("c", null), node("d")];
  const habits = (sessions, items) => ({ sessions, activeDays: 3, items });
  assert.deepEqual(useVsPay(nodes, habits(5, { a: { sessions_used: 2 }, b: { sessions_used: 0 } })), { pay: 400, used: 100, usedItems: 1, paidItems: 2, unmeasured: 2, sessions: 5 });
  assert.equal(useVsPay(nodes, null), null);
  assert.equal(useVsPay(nodes, habits(0, {})), null); // no recorded sessions: nothing to compare
  assert.equal(useVsPay([node("c", null)], habits(5, {})), null); // nothing measured is never "0 tokens"
  assert.deepEqual([pct(100, 400), pct(1, 0), pct(2, 3)], [25, 0, 67]);
  console.log("Explain use-vs-pay passes.");
} finally {
  await vite.close();
}
