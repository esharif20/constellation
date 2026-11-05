// Self-check for the install-preview panel (docs/plans/install-preview.md P3): untrusted file shapes render nothing. Invented values only.
import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { createServer } from "vite";

const vite = await createServer({ server: { middlewareMode: true, watch: null, ws: false }, appType: "custom" });
try {
  const { isPreview, loadPreview } = await vite.ssrLoadModule("/src/components/Preview.tsx");
  const good = JSON.parse(readFileSync("../docs/design/demo-preview.json", "utf8"));
  assert.ok(isPreview(good));
  for (const bad of [null, [], "x", {}, { ...good, always_on: { counted: "1", estimated: 0, unknown: 0 } }, { ...good, items: [{ id: 1, kind: "k", name: "n" }] },
    { ...good, overlaps: [{ new_id: "a" }] }, { ...good, already_installed: "no" }, { ...good, pack: null }]) assert.equal(isPreview(bad), false);
  const reply = (body, ok = true) => async () => ({ ok, json: async () => body });
  assert.deepEqual(await loadPreview(reply(good)), good);
  assert.equal(await loadPreview(reply(good, false)), null);
  assert.equal(await loadPreview(reply({ nope: 1 })), null);
  assert.equal(await loadPreview(async () => { throw new Error("down"); }), null);
  console.log("Install preview guard passes.");
} finally {
  await vite.close();
}
