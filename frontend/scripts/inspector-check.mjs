// Self-check for the Inspector's verdict (inspector.md section 2) and header origin/scope, on invented fixtures only.
import { strict as assert } from "node:assert";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

const vite = await createServer({ server: { middlewareMode: true, watch: null, ws: false }, appType: "custom" });
try {
  const { verdictOf, DORMANT_DAYS } = await vite.ssrLoadModule("/src/lib/verdict.ts");
  const { Header } = await vite.ssrLoadModule("/src/components/inspector/Header.tsx");
  const win = { files: 40, first: "2026-09-04", last: "2026-11-04", skipped: 0 };
  const node = (name, o = {}) => ({ id: name, kind: "skill", name, ...o });
  const dayBefore = (n) => new Date(Date.parse(win.last) - n * 864e5).toISOString().slice(0, 10);
  const used = (n) => ({ count: 3, last_used: dayBefore(n) });
  const cost = { always_on: 840, on_use: null };
  const run = (item, os = [], kids = [], w = win) => verdictOf(item, os, kids, w);
  const other = node("changelog-draft");

  assert.equal(DORMANT_DAYS, 30);
  const off = run(node("a", { disabled: true, usage: used(0), cost }));
  assert.deepEqual([off.tone, off.label], ["off", "Switched off"]);
  const me = node("me", { cost, usage: used(0) });
  assert.deepEqual([run(me, [{ a: me, b: other, verdict: "duplicate" }]).label, run(me, [{ a: me, b: other, verdict: "duplicate" }]).why], ["Keep one", "Does the same job as changelog-draft."]);
  assert.equal(run(me, [{ a: other, b: me, verdict: "duplicate" }]).why, "Does the same job as changelog-draft.");
  assert.equal(run(me, [{ a: me, b: other, verdict: "wrapper" }]).label, "Keep the wrapped one");
  assert.equal(run(me, [{ a: other, b: me, verdict: "wrapper" }]).label, "Keep"); // this is the wrapped one: not flagged
  assert.equal(run(me, [{ a: me, b: other, verdict: "overlap" }]).label, "Keep"); // plain overlap is no verdict
  const never = run(node("n", { cost, usage: { count: 0, last_used: null } }));
  assert.deepEqual([never.label, never.tone, never.basis], ["Could go", "destructive", true]);
  assert.match(never.why, /Not seen in 62 days of sessions; costs 840 tokens every session\./);
  for (const [age, label] of [[29, "Keep"], [30, "Review"], [31, "Review"]]) assert.equal(run(node("d", { cost, usage: used(age) })).label, label, `${age} days`);
  assert.equal(run(node("free", { cost: { always_on: 0, on_use: null }, usage: used(90) })).label, "Keep"); // nothing to save
  assert.equal(run(node("unk", { cost: { always_on: null, on_use: null }, usage: { count: 0, last_used: null } })).label, "Not enough data");
  assert.equal(run(node("k", { cost, usage: used(2) })).tone, "keep");
  assert.equal(run(node("hk", { kind: "hook" })).why, "Usage is not tracked for hooks.");
  const kids = [node("c1", { cost, usage: { count: 0, last_used: null } }), node("c2", { cost, usage: { count: 0, last_used: null } })];
  assert.equal(run(node("p", { kind: "plugin" }), [], kids).label, "Could go");
  assert.equal(run(node("p", { kind: "plugin" }), [], [kids[0], node("c3", { cost, usage: used(1) })]).label, "Not enough data");
  assert.equal(run(node("p", { kind: "plugin" }), [], []).label, "Not enough data");
  assert.ok(run(me, [{ a: me, b: node("x".repeat(200)), verdict: "duplicate" }]).why.length <= 90);

  const html = (item) => renderToStaticMarkup(createElement(Header, { item }));
  assert.match(html(node("s", { origin: "obra/superpowers", scope: "project", project: "dev-constellation" })), /from obra\/superpowers[\s\S]*Project · dev-constellation/);
  assert.match(html(node("s", { scope: "global" })), />Global</);
  assert.doesNotMatch(html(node("s")), /Global|Project|from /);
  console.log("Inspector verdict rows, the 29/30/31-day edge and header origin/scope pass.");
} finally {
  await vite.close();
}
