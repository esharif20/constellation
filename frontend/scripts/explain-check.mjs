// Self-check for the explain card (docs/plans/whatif.md #68b): the public copy is refused unless the server says public === true. Invented values only.
import { strict as assert } from "node:assert";
import { createServer } from "vite";

const vite = await createServer({ server: { middlewareMode: true, watch: null, ws: false }, appType: "custom" });
try {
  const { copyPublic } = await vite.ssrLoadModule("/src/components/ExplainCard.tsx");
  const reply = (body, ok = true) => async () => ({ ok, json: async () => body });
  let copied = null;
  const write = async (t) => { copied = t; };
  let r = await copyPublic(reply({ public: true, text: "safe" }), write);
  assert.deepEqual([r.result, copied], ["ok", "safe"]);
  for (const body of [{ public: false, text: "private" }, { text: "private" }, { public: "true", text: "private" }]) {
    copied = null;
    r = await copyPublic(reply(body), write);
    assert.deepEqual([r.result, copied], ["refused", null]);
  }
  copied = null;
  assert.equal((await copyPublic(reply({ public: true, text: "x" }, false), write)).result, "refused");
  assert.equal((await copyPublic(async () => { throw new Error("down"); }, write)).result, "failed");
  assert.equal(copied, null);
  console.log("Explain public-copy guard passes.");
} finally {
  await vite.close();
}
