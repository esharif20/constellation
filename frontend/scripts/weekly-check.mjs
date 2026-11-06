// Self-check for the Brief's "This week" section (src/components/Weekly.tsx) on invented fixtures only.
import { strict as assert } from "node:assert";
import fs from "node:fs";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

const vite = await createServer({ server: { middlewareMode: true, watch: null, ws: false }, appType: "custom" });
try {
  const { Weekly } = await vite.ssrLoadModule("/src/components/Weekly.tsx");
  const { briefFrom } = await vite.ssrLoadModule("/src/lib/brief.ts");
  const demo = JSON.parse(fs.readFileSync(new URL("../../docs/design/demo-assess-brief.json", import.meta.url)));
  const html = (w) => renderToStaticMarkup(createElement(Weekly, { data: w }));
  const text = (w) => html(w).replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
  const w = demo.weekly;

  const shown = text(w);
  assert.match(shown, /This week/);
  assert.match(shown, /since (Oct 30|30 Oct) · 7 days/);
  assert.match(shown, /2 added 1 removed 2 went quiet/);
  assert.match(shown, /5,640 → 6,310 \(\+670\)/);
  assert.match(shown, /Known costs only: 1 → 2 with unknown cost/); // an approximate delta says so
  assert.match(shown, /Could free 3,500 to 7,400 tokens · high confidence/);
  assert.match(shown, /Last time 2,900 to 6,100\. \+ 3 with unknown cost, not counted\./);
  assert.match(shown, /Keep → Review/); // the verdict move and why live in the disclosure
  assert.match(html(w), /<details[^>]*>\s*<summary[^>]*>What changed<\/summary>/); // closed by default: no `open` attribute
  assert.doesNotMatch(html(w), /<details[^>]* open/);
  assert.doesNotMatch(shown, /[0-9a-f]{12}|constellation-|\/Users\//); // names and counts only

  // Unknown costs are never shown as 0.
  const nothing = text({ ...w, session_start: { then: null, now: null, delta: null, unknown_then: 2, unknown_now: 2 } });
  assert.match(nothing, /Session start not measured/);
  assert.doesNotMatch(nothing, /Known costs only|→ 0|\b0 → /);
  assert.match(text({ ...w, session_start: { ...w.session_start, delta: -300, then: 900, now: 600 } }), /900 → 600 \(−300\)/);
  assert.match(text({ ...w, session_start: { then: 100, now: 100, delta: 0, unknown_then: 0, unknown_now: 0 } }), /100 → 100 \(±0\)/);
  assert.doesNotMatch(text({ ...w, session_start: { then: 100, now: 100, delta: 0, unknown_then: 0, unknown_now: 0 } }), /Known costs only/);

  // A single value, a single day, and a quiet week (no disclosure when there is nothing to list).
  const calm = { ...w, days: 1, added: [], removed: [], went_quiet: [], verdict_changes: [], used_most: [], reclaim: { now: { low: 700, high: 700, unknown: 0, confidence: "low" }, then: { low: 700, high: 700, unknown: 0, confidence: "low" } } };
  assert.match(text(calm), /since (Oct 30|30 Oct) · 1 day\b/);
  assert.match(text(calm), /Could free 700 tokens · low confidence Last time 700\./);
  assert.doesNotMatch(html(calm), /<details/);

  // The Brief's data shape: `weekly` passes through briefFrom, and null (first scan, old server) means the section is absent.
  assert.equal(briefFrom(demo).weekly.since, "2026-10-30");
  assert.equal(briefFrom({ ...demo, weekly: null }).weekly, null);
  assert.equal(briefFrom({ ...demo, weekly: undefined }).weekly, undefined);
  console.log("This week section: counts, honest unknowns, closed disclosure, no ids or paths.");
} finally {
  await vite.close();
}
