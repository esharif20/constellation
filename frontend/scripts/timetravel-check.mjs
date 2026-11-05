// Self-check for the time-travel scrubber (#70): text, accessible names and the range, on invented values only.
import { strict as assert } from "node:assert";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

const vite = await createServer({ server: { middlewareMode: true, watch: null, ws: false }, appType: "custom" });
try {
  const { Scrubber } = await vite.ssrLoadModule("/src/components/Scrubber.tsx");
  const entries = [{ date: "2026-10-01", items: 3, always_on: 1, unknown: 0, added: 0, removed: 0, gone: 0 }, { date: "2026-11-01", items: 3, always_on: 2, unknown: 0, added: 2, removed: 1, gone: 0 }];
  const nodes = [{ id: "a" }, { id: "b" }, { id: "c" }], firstSeen = { a: "2026-10-01", b: "2026-10-01", c: "2026-11-01" };
  const html = (date) => renderToStaticMarkup(createElement(Scrubber, { entries, nodes, firstSeen, date, onDate() {}, onClose() {} }));
  const old = html("2026-10-01");
  assert.match(old, /aria-labelledby="scrub-title"/);
  assert.match(old, /type="range"[^>]*min="0"|min="0"[^>]*type="range"/);
  assert.match(old, /aria-valuetext="1 Oct 2026, 3 Items"/);
  assert.match(old, /2 of 3 Items · 1 since removed/);
  assert.match(old, /aria-label="Close time travel"/);
  assert.match(html("2026-11-01"), />3 of 3 Items</);
  console.log("Time-travel scrubber text and controls pass.");
} finally {
  await vite.close();
}
