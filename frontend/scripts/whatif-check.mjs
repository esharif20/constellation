// Self-check for what-if (docs/plans/whatif.md): the chip text and controls, on invented values only.
import { strict as assert } from "node:assert";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

const vite = await createServer({ server: { middlewareMode: true, watch: null, ws: false }, appType: "custom" });
try {
  const { WhatIfChip } = await vite.ssrLoadModule("/src/components/WhatIfChip.tsx");
  const chip = renderToStaticMarkup(createElement(WhatIfChip, { count: 3, saved: 1234, onReset() {}, onExit() {} }));
  assert.match(chip, /What-if: 3 removed/);
  assert.match(chip, /−1,234/);
  assert.match(chip, /aria-label="Exit what-if"/);
  assert.match(chip, />Reset</);
  console.log("What-if chip text and controls pass.");
} finally {
  await vite.close();
}
