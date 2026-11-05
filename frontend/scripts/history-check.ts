// History chart geometry, no browser: node scripts/history-check.ts  (npm run history:check)
// Checks chartPoints on the invented seeded history in docs/design/demo-250-history.json (the server's timeline shape is built here from it).
import { readFileSync } from "node:fs";
import { strict as assert } from "node:assert";
import { chartPoints, hoverLine, type HistoryEntry } from "../src/graph/history.ts";

const raw = JSON.parse(readFileSync(new URL("../../docs/design/demo-250-history.json", import.meta.url), "utf8")) as { entries: { date: string; items: number; always_on: number; unknown: number; ids: string[] }[] };
const entries: HistoryEntry[] = raw.entries.map((e, i) => {
  const prev = new Set(raw.entries[i - 1]?.ids ?? e.ids), now = new Set(e.ids);
  return { date: e.date, items: e.items, always_on: e.always_on, unknown: e.unknown, added: e.ids.filter((x) => !prev.has(x)).length, removed: [...prev].filter((x) => !now.has(x)).length, gone: 0 };
});
const box = { left: 44, right: 304, top: 10, bottom: 116 };
const points = chartPoints(entries, box);

assert.equal(points.length, entries.length);
assert.ok(points.every((p, i) => i === 0 || p.x > points[i - 1].x), "x increases with the date");
assert.equal(points[0].x, box.left);
assert.equal(points[points.length - 1].x, box.right);
assert.equal(Math.min(...points.map((p) => p.y)), box.top, "the largest value touches the top");
assert.ok(points.every((p) => p.y <= box.bottom && p.y > box.top - 1), "y stays between baseline and top");
assert.equal(chartPoints([{ ...entries[0], always_on: 0 }, { ...entries[1], always_on: 0 }], box)[0].y, box.bottom, "y(0) is the baseline");
assert.equal(points.filter((p) => p.marker).length, entries.filter((e) => e.added > 0).length);
const uneven = chartPoints([{ ...entries[0], date: "2026-01-01" }, { ...entries[1], date: "2026-01-02" }, { ...entries[2], date: "2026-01-11" }], box);
assert.ok(Math.abs((uneven[1].x - box.left) / (box.right - box.left) - 0.1) < 1e-9, "x follows the date, not the index");
assert.equal(chartPoints([entries[0]], box)[0].x, (box.left + box.right) / 2);
assert.deepEqual(chartPoints([], box), []);
assert.match(hoverLine({ date: "2026-11-04", items: 212, always_on: 19050, unknown: 0, added: 3, removed: 1, gone: 0 }), /^4 Nov 2026 · 19,050 tokens · 212 Items · \+3 −1$/);
console.log(`history:check ok (${points.length} points, ${points.filter((p) => p.marker).length} markers)`);

// Time travel (#70): absentAt on the same seeded history
import { absentAt } from "../src/graph/history.ts";
const firstSeen: Record<string, string> = {};
for (const e of raw.entries) for (const id of e.ids) firstSeen[id] ??= e.date;
const nodes = [...new Set(raw.entries.flatMap((e) => e.ids))].map((id) => ({ id })).concat([{ id: "unknown-id" }]);
const dates = raw.entries.map((e) => e.date), oldest = dates[0], newest = dates[dates.length - 1];
const atOldest = absentAt(nodes, firstSeen, oldest);
assert.ok(nodes.every((n) => atOldest.has(n) === (firstSeen[n.id] !== undefined && firstSeen[n.id] > oldest)), "oldest: only Items first seen then are present");
assert.equal(absentAt(nodes, firstSeen, newest).size, 0, "newest: nothing is absent");
assert.ok(![...absentAt(nodes, firstSeen, oldest)].some((n) => n.id === "unknown-id"), "an unknown id is present");
console.log("absentAt ok");
