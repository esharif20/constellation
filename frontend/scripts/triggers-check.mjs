// Self-check for the trigger audit panel, on invented rows only.
import { strict as assert } from "node:assert";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

const vite = await createServer({ server: { middlewareMode: true, watch: null, ws: false }, appType: "custom" });
try {
  const { Triggers, reasons } = await vite.ssrLoadModule("/src/components/Triggers.tsx");
  const row = (flags, count = 0) => ({ id: "s:" + flags.join(), name: "demo-" + flags.join("-"), count, last_used: null, flags });
  assert.deepEqual(reasons(row(["never", "vague"]), 1), ["Never used in your last 1 session file.", "Its description is very short, so Claude may not know when to pick it."]);
  assert.match(reasons(row(["greedy"], 60), 40)[0], /Used 60 times/);
  const html = (data) => renderToStaticMarkup(createElement(Triggers, { data, onItem() {} }));
  assert.match(html({ files: 0, rows: [] }), /No session history/);
  assert.match(html({ files: 9, rows: [] }), /Nothing found/);
  const list = html({ files: 40, rows: [row(["greedy"], 60), row(["never"])] });
  assert.match(list, /demo-greedy/);
  assert.match(list, /Never used in your last 40 session files/);
  assert.match(html({ files: 40, rows: Array.from({ length: 10 }, (_, i) => ({ ...row(["never"]), id: "x" + i })) }), /\+ 2 more/);
  console.log("Trigger panel wording and states pass.");
} finally {
  await vite.close();
}
