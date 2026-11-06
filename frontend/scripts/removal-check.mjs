// Self-check for the "If you remove this" Inspector section (#76), on invented values only.
import { strict as assert } from "node:assert";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

const vite = await createServer({ server: { middlewareMode: true, watch: null, ws: false }, appType: "custom" });
try {
  const { RemovalBody, RemovalPreview } = await vite.ssrLoadModule("/src/components/inspector/Removal.tsx");
  const row = (id, name, why) => ({ id, name, kind: "skill", why });
  const base = { id: "a", name: "alpha", kind: "skill", safe: true, verdict: "Safe to remove", reasons: ["Nothing refers to it."], loses_coverage: false, covered_by: [], cluster: null, referenced_by: [], hooks: [], contains: [], used: null, last_used: null };
  const nodes = [{ id: "b", name: "beta", kind: "skill" }];
  const safe = renderToStaticMarkup(createElement(RemovalBody, { data: base, model: { nodes }, onSelect() {} }));
  assert.match(safe, /Safe to remove/);
  assert.match(safe, /Nothing is changed here/);
  assert.doesNotMatch(safe, /<h4/);
  const risky = { ...base, safe: false, verdict: "Check these first", reasons: ["1 other Item refers to it."], referenced_by: [row("b", "beta", "mentions its name"), row("gone", "ghost", "calls it")], cluster: { name: "Tidy", others: ["x", "y"], more: 3 } };
  const html = renderToStaticMarkup(createElement(RemovalBody, { data: risky, model: { nodes }, onSelect() {} }));
  assert.match(html, /Check these first/);
  assert.match(html, /Refer to it/);
  assert.equal((html.match(/<button/g) ?? []).length, 1); // only the Item the map holds is clickable
  assert.match(html, /ghost/); // an unknown id still shows its name
  assert.match(html, /Same group, Tidy: x, y and 3 more\./);
  const closed = renderToStaticMarkup(createElement(RemovalPreview, { item: { id: "a" }, model: { nodes }, onSelect() {} }));
  assert.match(closed, /If you remove this/);
  assert.match(closed, /aria-expanded="false"/);
  assert.doesNotMatch(closed, /Safe to remove|Checking/); // closed: nothing fetched, nothing shown
  // A covering Item the Inspector already lists under "Does the same job" is named once, there.
  const covered = { ...base, covered_by: [row("b", "beta", "same steps")] };
  const deduped = renderToStaticMarkup(createElement(RemovalBody, { data: covered, model: { nodes }, onSelect() {}, listed: new Set(["b"]) }));
  assert.doesNotMatch(deduped, /<h4|<button|same steps/);
  assert.match(deduped, /Still covered by beta, listed below/);
  assert.match(renderToStaticMarkup(createElement(RemovalBody, { data: covered, model: { nodes }, onSelect() {} })), /Still covered by/); // not listed elsewhere: the group stays
  // Brief headline with no usage history: no "0 to 0 a day", no "0 sessions"; a lens is named as not scoping the numbers.
  const { Headline } = await vite.ssrLoadModule("/src/components/Brief.tsx");
  const range = { low: 0, high: 410, unknown: 0, per_day: [0, 0] };
  const none = renderToStaticMarkup(createElement(Headline, { range, evidence: { sessions: 0, active_days: 0 }, lensed: false }));
  assert.match(none, /No usage history yet/);
  assert.doesNotMatch(none, /a day at your pace|0 sessions/);
  const some = renderToStaticMarkup(createElement(Headline, { range: { ...range, per_day: [1, 5] }, evidence: { sessions: 3, active_days: 2 }, lensed: true }));
  assert.match(some, /About 1 to 5 a day/);
  assert.match(some, /Based on 3 sessions/);
  assert.match(some, /whole setup/);
  console.log("Removal preview passes.");
} finally {
  await vite.close();
}
