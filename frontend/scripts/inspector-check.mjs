// Self-check for the Inspector's verdict (inspector.md section 2) and header origin/scope, on invented fixtures only.
import { strict as assert } from "node:assert";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

const vite = await createServer({ server: { middlewareMode: true, watch: null, ws: false }, appType: "custom" });
try {
  const { verdictOf, DORMANT_DAYS } = await vite.ssrLoadModule("/src/lib/verdict.ts");
  const { Header } = await vite.ssrLoadModule("/src/components/inspector/Header.tsx");
  const { splitDescription } = await vite.ssrLoadModule("/src/lib/describe.ts");
  const { hookInfo, pluginInfo } = await vite.ssrLoadModule("/src/lib/details.ts");
  const { relatedGroups, CAP } = await vite.ssrLoadModule("/src/lib/related.ts");
  const { KindDetails } = await vite.ssrLoadModule("/src/components/inspector/KindDetails.tsx");
  const { About } = await vite.ssrLoadModule("/src/components/inspector/About.tsx");
  const { instructionFor } = await vite.ssrLoadModule("/src/lib/instruction.ts");
  const { Actions, briefRow } = await vite.ssrLoadModule("/src/components/inspector/Actions.tsx");
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

  const html = (item) => renderToStaticMarkup(createElement(Header, { item, model: { projects: { p1: "dev-constellation" } } }));
  assert.match(html(node("s", { origin: "obra/superpowers", scope: "project", project: "p1" })), /from obra\/superpowers[\s\S]*Project · dev-constellation/);
  assert.match(html(node("s", { scope: "global" })), />Global</);
  assert.doesNotMatch(html(node("s")), /Global|Project|from /);

  // Description split (section 3): no trigger, trigger-only, trigger first, trigger last, e.g., URL, empty.
  const sp = splitDescription;
  assert.deepEqual(sp("Drafts release notes from commits."), { does: "Drafts release notes from commits.", when: "" });
  assert.deepEqual(sp("Use when the task involves PDFs.", "Reads PDFs"), { does: "Reads PDFs", when: "Use when the task involves PDFs." }); // trigger-only: label stands in
  assert.deepEqual(sp("Use when the task involves PDFs."), { does: "", when: "Use when the task involves PDFs." });
  assert.deepEqual(sp("Use when editing docs. Fixes typos."), { does: "Fixes typos.", when: "Use when editing docs." });
  assert.deepEqual(sp("Fixes typos. Triggers on docs edits."), { does: "Fixes typos.", when: "Triggers on docs edits." });
  assert.deepEqual(sp("Use when editing, e.g. README files. Then lints it when saved. Fixes typos."), { does: "Fixes typos.", when: "Use when editing, e.g. README files. Then lints it when saved." });
  assert.equal(sp("Reads https://example.com/a.b and v1.2 notes. Fast.").does, "Reads https://example.com/a.b and v1.2 notes. Fast.");
  assert.deepEqual(sp("  \n "), { does: "", when: "" });
  assert.deepEqual(sp(null), { does: "", when: "" });

  // Hooks (section 4).
  const hk = (n) => hookInfo(node(n, { kind: "hook" }));
  assert.deepEqual(hk("PreToolUse:Bash"), { event: "PreToolUse", matcher: "Bash", promptTime: false, canBlock: true });
  assert.deepEqual(hk("SessionStart:"), { event: "SessionStart", matcher: "all tools", promptTime: true, canBlock: false });
  assert.deepEqual(hk("PostToolUse:Edit"), { event: "PostToolUse", matcher: "Edit", promptTime: false, canBlock: false });
  assert.deepEqual(hk("mend-gasket"), { event: null, matcher: null, promptTime: false, canBlock: false }); // no event in the name: unknown, not guessed
  // Plugins: unknown cost is counted, never summed as 0.
  const kid = (n, k, a, c) => node(n, { kind: k, cost: { always_on: a, on_use: null }, usage: c == null ? undefined : { count: c, last_used: null } });
  const pi = pluginInfo([kid("a", "skill", 100, 0), kid("b", "skill", 50, 2), kid("c", "hook", null)]);
  assert.deepEqual([pi.total, pi.unknown, pi.tracked, pi.unseen, pi.counts[0]], [150, 1, 2, 1, ["skill", 2]]);
  assert.equal(pluginInfo([kid("c", "hook", null)]).total, null);

  // Related: groups, cap constant, plugin siblings, cluster excluding listed Items, empty.
  const mk = (n, o = {}) => node(n, o);
  const plug = mk("plug", { kind: "plugin" }), me2 = mk("me2"), sib = mk("sib"), dup = mk("dup"), mate = mk("mate"), rich = mk("rich", { cost: { always_on: 900, on_use: null } });
  const cluster = { members: [me2, sib, dup, mate, rich] };
  me2.cluster = cluster;
  const links = [{ source: plug, target: me2, kind: "contains" }, { source: plug, target: sib, kind: "contains" }];
  const g = relatedGroups(me2, { links, overlapsOf: new Map([[me2, [{ a: me2, b: dup, verdict: "duplicate", reason: "same" }]]]) });
  assert.deepEqual(g.map((x) => x.title), ["Does the same job", "Contained in", "In the same plugin", "Same cluster"]);
  assert.deepEqual(g[3].rows.map((r) => r.other.name), ["rich", "mate"]); // sib and dup are listed above; known cost first
  assert.equal(g[0].rows[0].reason, "same");
  assert.deepEqual(relatedGroups(mk("solo"), { links: [], overlapsOf: new Map() }), []);
  assert.equal(CAP, 5);

  // Rendered markup: raw kinds skip the split, plugin shows contents, no 0 for unknown.
  const km = (it, ls = []) => renderToStaticMarkup(createElement(KindDetails, { item: it, model: { links: ls } }));
  assert.match(km(node("PreToolUse:Bash", { kind: "hook", description: "./guard.sh" })), /PreToolUse[\s\S]*Bash[\s\S]*Can block[\s\S]*\.\/guard\.sh/);
  assert.match(km(node("x", { kind: "hook" })), />unknown</);
  assert.match(km(node("srv", { kind: "mcp_server", description: "stdio: npx", scope: "project" })), /Shape[\s\S]*stdio: npx[\s\S]*Project/);
  assert.match(km(plug, [{ source: plug, target: kid("k", "hook", null), kind: "contains" }]), /Total always-on[\s\S]*unknown/);
  assert.doesNotMatch(km(plug, [{ source: plug, target: kid("k", "hook", null), kind: "contains" }]), /0 tokens/);
  assert.equal(km(node("s")), "");
  const ab = (it) => renderToStaticMarkup(createElement(About, { item: it }));
  assert.match(ab(node("s", { description: "Fixes typos. Use when editing docs.", label: "L" })), /What it does[\s\S]*Fixes typos\.[\s\S]*When it triggers[\s\S]*Use when editing docs\./);
  assert.match(ab(node("s", { description: "" })), /No description\./);
  assert.doesNotMatch(ab(node("h", { kind: "hook", description: "Use when x." })), /What it does|When it triggers/);

  // Actions (section 5): instruction wording matches answer.py handoff(); Add only for Brief cost/pairs rows; Compare only with onAsk.
  const noOs = { overlapsOf: new Map() }, V = (label, tone) => ({ label, tone, why: "", basis: false });
  assert.equal(instructionFor(node("release-notes"), noOs, V("Could go", "destructive")), 'Remove the skill "release-notes": find its folder (under ~/.claude/skills) and delete only that folder. Show me exactly what will change and wait for my OK.');
  assert.equal(instructionFor(node("pdf-tools", { kind: "plugin" }), noOs, V("Not enough data", "none")), 'Disable the plugin "pdf-tools" in my user settings.json enabledPlugins; do not delete files. Show me exactly what will change and wait for my OK.');
  assert.equal(instructionFor(node("s"), noOs, V("Keep", "keep")), 'Review the skill "s": tell me what it does and whether I still need it. Change nothing.');
  assert.match(instructionFor(node("srv", { kind: "mcp_server", origin: "acme" }), noOs, V("Could go", "destructive")), /^Remove the MCP server "srv" from my Claude Code config.*It came from "acme": if that is a plugin or pack/);
  const dupOs = { overlapsOf: new Map([[me, [{ a: me, b: other, verdict: "duplicate" }]]]) };
  assert.equal(instructionFor(me, dupOs, V("Keep one", "destructive")), 'The skill "me" and "changelog-draft" do the same job. Compare them and recommend which to remove; remove nothing until I choose. Show me exactly what will change and wait for my OK.');
  assert.match(instructionFor(me, { overlapsOf: new Map([[me, [{ a: me, b: other, verdict: "wrapper" }]]]) }, V("Keep the wrapped one", "warn")), /only calls "changelog-draft"\. Show me how to use/);
  assert.ok(instructionFor(node("w".repeat(500)), noOs, V("Could go", "destructive")).length <= 400);
  const row = { id: "r1", kind: "review_cost", item_ids: ["me"] }, grp = (rows) => ({ rows });
  const brief = { cost: grp([row]), pairs: grp([]), scope: { rows: [{ id: "s1", kind: "move_to_project", item_ids: ["scoped"] }] }, checklist: { ids: [] } };
  assert.equal(briefRow(brief, me).id, "r1");
  assert.equal(briefRow(brief, node("scoped")), undefined); // scope rows 404: never offered
  const act = (p) => renderToStaticMarkup(createElement(Actions, { item: me, instruction: "x", ...p }));
  assert.match(act({ brief }), /Copy instruction for Claude Code[\s\S]*Add to checklist/);
  assert.doesNotMatch(act({}), /Add to checklist|Compare with/);
  assert.doesNotMatch(act({ brief: { ...brief, checklist: undefined } }), /Add to checklist/);
  assert.match(act({ brief: { ...brief, checklist: { ids: ["r1"] } } }), /disabled[^>]*>[\s\S]*On checklist/);
  assert.match(act({ onAsk: () => {} }), /Compare with…/);

  console.log("Inspector verdict rows, the 29/30/31-day edge, header, description split, kind details and Related groups pass.");
} finally {
  await vite.close();
}
