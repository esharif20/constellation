// Render the public panel in both states without starting an HTTP server.
import { strict as assert } from "node:assert";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

const vite = await createServer({ server: { middlewareMode: true, watch: null, ws: false }, appType: "custom" });
try {
  const { Chat } = await vite.ssrLoadModule("/src/components/Chat.tsx");
  const props = {
    model: { nodes: [] }, selected: null, briefOpen: false,
    onOpen() {}, onActions() {}, onReset() {}, onItem() {},
  };
  for (const open of [false, true]) {
    const html = renderToStaticMarkup(createElement(Chat, { ...props, open }));
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
  console.log("Chat disclosure references exist in both open and collapsed states.");
} finally {
  await vite.close();
}
