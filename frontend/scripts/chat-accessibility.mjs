// Render the public panel in both states without starting an HTTP server.
import { strict as assert } from "node:assert";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

const vite = await createServer({ server: { middlewareMode: true, watch: null, ws: false }, appType: "custom" });
try {
  const { Chat, AskTrigger, Answer, readBlocks } = await vite.ssrLoadModule("/src/components/Chat.tsx");
  const props = {
    model: { nodes: [], overlaps: [], clusters: [] }, selected: null, briefOpen: false, clusterOpen: false,
    onOpen() {}, onActions() {}, onReset() {}, onItem() {},
  };
  for (const open of [false, true]) {
    const html = renderToStaticMarkup(createElement(AskTrigger, { open, onOpen() {} })) + renderToStaticMarkup(createElement(Chat, { ...props, open }));
    for (const [, targets] of html.matchAll(/aria-controls="([^"]+)"/g)) {
      for (const target of targets.split(" ")) assert.ok(html.includes(`id="${target}"`), `Missing controlled region: ${target}`);
    }
    if (open) {
      assert.match(html, /<section[^>]*id="chat-panel"/);
      assert.match(html, /aria-controls="chat-panel"/);
      assert.match(html, /aria-expanded="true"/);
    } else {
      assert.doesNotMatch(html, /aria-controls=/);
      assert.match(html, /aria-expanded="false"/);
    }
  }
  const card = { handoff: { instruction: "Review the skill \"alpha\".", checklist_id: null }, id: "a", name: "alpha", kind: "skill", kind_label: "skill", what: "Does a thing.", always_on: "1,468 tokens", on_use: "unknown", usage: "Usage unknown", overlap: null, verdict: { label: "Not enough data", tone: "unknown", why: "Usage was not read in this scan" } };
  const blocks = { headline: "alpha is a skill.", cards: [card], compare: null, rows: [{ id: "a", name: "alpha", kind: "skill", what: "Does a thing.", value: "Cost unknown" }], more: 2, note: "A note.", next: "Do this.", follow_ups: ["What is alpha?"], did_you_mean: [], handoff: null };
  assert.deepEqual(readBlocks(blocks, new Set(["a"])), blocks);
  assert.equal(readBlocks(blocks, new Set(["b"])), null, "an unknown id drops the blocks");
  assert.equal(readBlocks({ ...blocks, cards: [{ ...card, verdict: { ...card.verdict, tone: "bad" } }] }, new Set(["a"])), null);
  const html = renderToStaticMarkup(createElement(Answer, { reply: { answer: "plain", blocks, actions: [], mode: "local", cached: false }, copied: false, onCopy() {}, onItem() {}, onAsk() {} }));
  const live = [...html.matchAll(/<p[^>]*role="status"[^>]*>(.*?)<\/p>/g)];
  assert.equal(live.length, 1);
  assert.equal(live[0][1], blocks.headline, "the live region holds only the headline");
  assert.match(html, /aria-label="Copy answer"/);
  assert.match(html, /2 more\. Ask a narrower question\./);
  const plain = renderToStaticMarkup(createElement(Answer, { reply: { answer: "plain text", blocks: null, actions: [], mode: "local", cached: false }, copied: false, onCopy() {}, onItem() {}, onAsk() {} }));
  assert.match(plain, /role="status"[^>]*>plain text</);
  console.log("Chat disclosure references exist in both open and collapsed states.");
} finally {
  await vite.close();
}
