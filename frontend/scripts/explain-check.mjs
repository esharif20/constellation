// Self-check for the explain card (docs/plans/whatif.md #68b): the public copy is refused unless the server says public === true. Invented values only.
import { strict as assert } from "node:assert";
import { createServer } from "vite";

const vite = await createServer({ server: { middlewareMode: true, watch: null, ws: false }, appType: "custom" });
try {
  const { copyPublic, fmtDay, dateNote, splitReason, kindLabel } = await vite.ssrLoadModule("/src/components/ExplainCard.tsx");
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
  assert.equal(fmtDay("2026-11-05"), "5 Nov");
  assert.equal(fmtDay("2026-11-05T10:00:00Z"), "5 Nov");
  assert.deepEqual([fmtDay(null), fmtDay("soon"), fmtDay("2026-13-45x"), fmtDay(undefined)], [null, null, null, null]);
  assert.equal(dateNote({ reason: "r", tokens_saved: 1, last_used: "2026-10-09" }, "2026-11-05"), "Last used 9 Oct · based on your last scan, 5 Nov");
  assert.equal(dateNote({ reason: "r", tokens_saved: 1, since: "2026-10-01" }, null), "Unused since 1 Oct");
  assert.equal(dateNote({ reason: "r", tokens_saved: null }, undefined), "");
  assert.deepEqual(splitReason("Do this. Because that."), ["Do this.", "Because that."]);
  assert.deepEqual(splitReason("Only one"), ["Only one", ""]);
  assert.deepEqual([kindLabel("remove_unused"), kindLabel(undefined), kindLabel("zzz")], ["Unused", "Tidy", "Tidy"]);
  console.log("Explain public-copy guard passes.");
} finally {
  await vite.close();
}
