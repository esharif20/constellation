// Self-check for the Clashes panel (docs/plans/lenses.md #64), on invented values only.
import { strict as assert } from "node:assert";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

const vite = await createServer({ server: { middlewareMode: true, watch: null, ws: false }, appType: "custom" });
try {
  const { Conflicts, conflictTitle, sortConflicts } = await vite.ssrLoadModule("/src/components/Conflicts.tsx");
  const hook = { kind: "hook", key: "PreToolUse:Edit", item_ids: ["h1", "h2"], reason: "2 hooks run on PreToolUse (Edit). Order is not fixed." };
  const mcp = { kind: "mcp_name", key: "files", item_ids: ["m1"], reason: "Two servers." };
  const trig = { kind: "trigger", key: "fix bug", item_ids: ["s1", "gone"], reason: "Two skills claim it." };
  assert.equal(conflictTitle(hook), "Hooks on PreToolUse (Edit)");
  assert.equal(conflictTitle({ ...hook, key: "Stop:" }), "Hooks on Stop");
  assert.equal(conflictTitle(trig), 'Both claim "fix bug"');
  assert.equal(conflictTitle(mcp), "Two servers named files");
  assert.deepEqual(sortConflicts([hook, mcp, trig]).map((c) => c.kind), ["trigger", "mcp_name", "hook"]);
  const nodes = [{ id: "h1", name: "lint", kind: "hook" }, { id: "h2", name: "fmt", kind: "hook" }, { id: "s1", name: "debugger", kind: "skill" }, { id: "m1", name: "files", kind: "mcp_server" }];
  const html = renderToStaticMarkup(createElement(Conflicts, { rows: [hook, trig], nodes, onItem() {} }));
  assert.match(html, /lint/);
  assert.match(html, /<button/); // known Items are clickable
  assert.match(html, /gone/); // unknown id falls back to the id, not a crash
  assert.equal((html.match(/<button/g) ?? []).length, 3);
  assert.match(renderToStaticMarkup(createElement(Conflicts, { rows: [], nodes, onItem() {} })), /No clashes found/);
  console.log("Clashes panel passes.");
} finally {
  await vite.close();
}
