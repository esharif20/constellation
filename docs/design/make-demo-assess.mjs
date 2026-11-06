import fs from "node:fs";
// Writes demo-assess.json (demo.json plus invented `assessments`) and demo-assess-brief.json (a Brief in the smarter-verdict 5.4
// shape), so the verdict UI can be looked at before slice S4 wires /api/assess. Invented data only: node docs/design/make-demo-assess.mjs
// Serve the brief with: agent-browser network route "**/api/brief" --body "$(cat docs/design/demo-assess-brief.json)"
const demo = JSON.parse(fs.readFileSync(new URL("./demo.json", import.meta.url)));
const skills = demo.items.filter((i) => i.kind === "skill");
const plugin = demo.items.find((i) => i.kind === "plugin");
const kids = demo.relations.filter((r) => r.source === plugin.id && r.kind === "contains").map((r) => r.target);
const A = (id, tier, label, confidence, reasons, action = "none", saves = null, group = null, recheck_after = null) =>
  ({ id, tier, label, confidence, reasons: reasons.map(([code, text]) => ({ code, text })), action, saves, risk: confidence === "high" ? 1 : 2, group, recheck_after });
const assessments = {};
for (const it of demo.items) assessments[it.id] = A(it.id, "keep", "Keep", "high", [["heavy_use", "Used 12 times in 3 of 3 projects"]]);
const [a, b, c, d, e, f, g, h, i] = skills.map((s) => s.id);
const cost = (id) => demo.costs[id]?.always_on ?? 300;
const set = (id, ...args) => { assessments[id] = A(id, ...args); };
set(a, "redundant", "Likely redundant", "high", [["duplicate_loser", `Does the same job as ${skills[8].name}; you used that 9 times, this one never`], ["no_origin", "Written by hand, so removing it cannot be undone"]], "remove_twin", cost(a), "safe");
set(b, "could_go", "Could go", "high", [["never_seen", "0 uses in 34 active days (52 sessions); costs 610 tokens every session"]], "remove", 610, "safe");
set(c, "could_go", "Could go", "high", [["never_seen", "0 uses in 34 active days; costs 280 tokens every session"]], "remove", 280, "safe");
set(d, "redundant", "Likely redundant", "medium", [["wrapper", `Only calls ${skills[4].name}; use that one directly`]], "use_underlying", cost(d), "look");
set(e, "review", "Review", "medium", [["single_project", "Used 9 times, all in one repo; moving it there saves 520 tokens elsewhere"]], "move_to_project", 520, "look");
set(f, "review", "Review", "medium", [["stale", "Used 6 times, none in 74 active days (you used it about every 9)"]], "remove", 200, "look");
set(g, "review", "Review", "low", [["vague", "Its description is 3 words, so Claude may never pick it; sharpen or remove"]], "fix_description", 90, "look");
set(h, "too_early", "Not enough history yet", "low", [["too_early", "Added 5 days ago; no verdict yet"]], "none", null, "wait", 12);
set(i, "keep_rare", "Keep (rarely needed)", "low", [["rare_purpose", "Made for occasional work (release); 34 active days can't tell yet"]], "none", null, "wait", 56);
set(plugin.id, "could_go", "Could go", "medium", [["children_unused", `None of its ${kids.length} skills used in 34 active days`], ["plugin", "A plugin can't be split: it turns off together"]], "disable_plugin", 1900, "look");
const row = (id, kind, extra = {}) => {
  const x = assessments[id], it = demo.items.find((n) => n.id === id);
  return { id: `${kind}-${id}`, kind, item_ids: [id], removes: kind === "remove_duplicate" || kind === "use_underlying" ? id : null, reason: x.reasons[0].text, saves: x.saves, tier: x.tier, confidence: x.confidence, reasons: x.reasons, name: it.name, ...extra };
};
const safe = [row(a, "remove_duplicate", { item_ids: [a, skills[8].id] }), row(b, "remove_unused"), row(c, "remove_unused")];
const look = [row(plugin.id, "disable_plugin"), row(e, "move_to_project"), row(d, "use_underlying", { item_ids: [d, skills[4].id] }), row(f, "remove_unused"), row(g, "fix_description")];
const wait = [row(h, "wait"), row(i, "wait")];
const sum = (rows) => rows.reduce((s, r) => s + (r.saves ?? 0), 0);
const brief = {
  evidence: { sessions: 52, active_days: 34, span_days: 52, ledger: true },
  safe: { rows: safe, saves: sum(safe) }, look: { rows: look, saves: sum(look), unknown: 1 },
  wait: { summary: [{ code: "too_early", count: 1, recheck_after: 12 }, { code: "keep_rare", count: 1, recheck_after: 56 }], rows: wait },
  range: { low: sum(safe), high: sum(safe) + sum(look), per_day: [1600, 6000], unknown: 3 },
  scope: { rows: [], caveat: "" }, checklist: { path: "~/constellation-checklist.md", ids: [], frees: null, unknown_rows: 0 },
};
fs.writeFileSync(new URL("./demo-assess.json", import.meta.url), JSON.stringify({ ...demo, usage_window: { files: 52, first: "2026-09-14", last: "2026-11-04", skipped: 0 }, assessments }));
fs.writeFileSync(new URL("./demo-assess-brief.json", import.meta.url), JSON.stringify(brief));
console.log(Object.keys(assessments).length, "assessments;", safe.length, "safe,", look.length, "look,", wait.length, "wait");

// "This week" (src/constellation/weekly.py shape): invented Items and counts, so the Brief's top section can be looked at on demo data.
brief.weekly = {
  state: "ready", since: "2026-10-30", days: 7,
  headline: "Since 2026-10-30: 2 added, 1 removed; session start 5,640 to 6,310 tokens (+670) counting known costs only; 2 went quiet; you could free 3,500 to 7,400 tokens (was 2,900 to 6,100).",
  added: [{ kind: "skill", name: skills[0].name }, { kind: "agent", name: "demo-reviewer" }],
  removed: [{ kind: "skill", name: "old-notes-helper" }],
  went_quiet: [{ kind: "skill", name: skills[5].name }, { kind: "mcp_server", name: "demo-search" }],
  session_start: { then: 5640, now: 6310, delta: 670, unknown_then: 1, unknown_now: 2 },
  verdict_changes: [
    { kind: "skill", name: skills[5].name, from: "Keep", to: "Review", why: "Used 6 times, none in 74 active days (you used it about every 9)" },
    { kind: "skill", name: skills[1].name, from: "Review", to: "Could go", why: "0 uses in 34 active days; costs 610 tokens every session" },
  ],
  used_most: [{ kind: "skill", name: skills[8].name, uses: 9 }, { kind: "skill", name: skills[4].name, uses: 4 }, { kind: "agent", name: "demo-reviewer", uses: 2 }],
  reclaim: { now: { low: 3500, high: 7400, unknown: 3, confidence: "high" }, then: { low: 2900, high: 6100, unknown: 3, confidence: "high" } },
};
fs.writeFileSync(new URL("./demo-assess-brief.json", import.meta.url), JSON.stringify(brief));
