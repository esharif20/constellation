// Self-check for the Hook safety panel (#67), on invented hooks only.
import { strict as assert } from "node:assert";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

const vite = await createServer({ server: { middlewareMode: true, watch: null, ws: false }, appType: "custom" });
try {
  const { HookSafety, hookLine, hookWeight } = await vite.ssrLoadModule("/src/components/HookSafety.tsx");
  const row = (id, o = {}) => ({ id, name: `UserPromptSubmit:${id}`, event: "UserPromptSubmit", matcher: null, phase: "before_prompt", can_block: true, runs: "shell", bytes: 120, tokens: null, ...o });
  assert.match(hookLine(row("a")), /every prompt you send · can stop/);
  assert.match(hookLine(row("a", { phase: "session_start", can_block: false, runs: "mcp_tool" })), /once when a session starts · only observes · calls an MCP tool/);
  assert.equal(hookWeight(row("a", { tokens: 1500 })), "1,500 tokens");
  assert.equal(hookWeight(row("a")), "120 bytes");
  assert.equal(hookWeight(row("a", { bytes: null })), null);
  const html = (rows) => renderToStaticMarkup(createElement(HookSafety, { rows, onItem() {} }));
  assert.match(html([]), /No hooks found/);
  const many = html(Array.from({ length: 8 }, (_, i) => row(`h${i}`)));
  assert.match(many, /8 hooks run automatically, 8 can block your prompt/);
  assert.match(many, /Show all 8/);
  assert.doesNotMatch(many, /h7/);
  assert.match(html([row("x", { bytes: null })]), /unknown/);
  console.log("Hook safety panel passes.");
} finally {
  await vite.close();
}
