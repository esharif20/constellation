// Self-check for the "Tools this server offers" Inspector section (#9), on invented values only.
import { strict as assert } from "node:assert";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

const vite = await createServer({ server: { middlewareMode: true, watch: null, ws: false }, appType: "custom" });
try {
  const { listing, ToolsBody, ToolsSection } = await vite.ssrLoadModule("/src/components/inspector/Tools.tsx");
  const html = (data) => renderToStaticMarkup(createElement(ToolsBody, { data }));
  const ok = listing(200, { status: "expanded", items: [{ name: "b_tool", description: "Does  B\n today." }, { name: "a_tool", description: "" }] });
  assert.equal(ok.tools.length, 2);
  const shown = html(ok);
  assert.match(shown, /Tools <span[^>]*>2</); // count
  assert.match(shown, /a_tool/);
  assert.match(shown, /Does B today\./); // one line, whitespace collapsed
  assert.match(html(listing(200, { status: "expanded", items: [] })), /offers no tools/);
  assert.match(html(listing(200, { status: "not_expandable", message: "x" })), /only be listed for local servers/);
  for (const [status, body] of [[200, { status: "unreachable", message: "/Users/me/secret-token-1234 failed" }], [200, { status: "unavailable" }], [404, {}], [422, {}], [500, null]]) {
    const out = html(listing(status, body));
    assert.match(out, /Could not reach this server: /);
    assert.doesNotMatch(out, /Users|secret|token/); // server text and paths never reach the screen
  }
  const closed = (kind) => renderToStaticMarkup(createElement(ToolsSection, { item: { id: "a", kind } }));
  assert.equal(closed("skill"), ""); // hidden for other kinds
  const server = closed("mcp_server");
  assert.match(server, /Tools this server offers/);
  assert.match(server, /aria-expanded="false"/);
  assert.doesNotMatch(server, /List tools|starts the server|Asking/); // closed: nothing shown, nothing started
  assert.match(closed("connector"), /Tools this server offers/);
  console.log("Expand tools section passes.");
} finally {
  await vite.close();
}
