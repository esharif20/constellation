// Stress check for Presence/Pane (src/components/Motion.tsx) in a real browser, invented data only: node scripts/presence-check.mjs  (npm run presence:check)
// Serves scripts/presence-harness.html with vite and drives it with agent-browser: re-render during enter, re-render during exit,
// re-enter during exit, rapid toggle 20x, unmount mid-animation, reduced motion, plus the real "If you remove this" and "Tools"
// disclosures under the same stress.
import { execFile, execFileSync } from "node:child_process";
import { promisify } from "node:util";
import { createServer } from "vite";

const server = await createServer({ server: { port: 0, host: "127.0.0.1", watch: null, ws: false }, appType: "spa", logLevel: "error" });
await server.listen();
const base = `http://127.0.0.1:${server.httpServer.address().port}/scripts/presence-harness.html`;
const session = execFileSync("agent-browser", ["session", "id", "--scope", "worktree", "--prefix", "presence"], { encoding: "utf8" }).trim();
// Async: vite runs in this process, so a blocking exec would starve the page of its own server.
const ab = async (...a) => (await promisify(execFile)("agent-browser", ["--session", session, ...a], { encoding: "utf8", timeout: 120000 })).stdout;

// Runs in the page. Returns [name, got, want] rows.
const scenarios = `(async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const errors = []; addEventListener("error", (e) => errors.push(String(e.message)));
  while (!window.harnessReady) await sleep(50);
  const q = (s) => document.querySelectorAll(s).length;
  const bare = () => q('[data-probe="bare"]');
  const real = () => q("#real [data-pane]");
  const tools = () => q("#tools [data-pane]");
  const verdicts = () => (document.getElementById("real").textContent.match(/Safe to remove/g) || []).length;
  const expanded = (sec) => document.querySelector("#" + sec + " button[aria-expanded]").getAttribute("aria-expanded") === "true";
  const click = (sec) => document.querySelector("#" + sec + " button[aria-expanded]").click();
  const to = (sec, want) => { if (expanded(sec) !== want) click(sec); };
  const A = () => window.h.api, rows = [], row = (n, g, w) => rows.push([n, g, w]);
  const reduced = location.search.includes("reduced");
  const leave = reduced ? 120 : 180;
  const probe = () => document.querySelector('[data-probe="bare"]');

  // Enter, with re-renders (state change in the parent) while it plays and while it rests.
  A().set(true); to("real", true); to("tools", true);
  for (let i = 0; i < 6; i++) { await sleep(15); A().tick(); }
  await sleep(300);
  row("re-render during enter: panes", [bare(), real(), tools(), verdicts()], [1, 1, 1, 1]);

  // Exit with re-renders during it: still leaving and inert, then gone; never a second copy.
  A().set(false); to("real", false); to("tools", false);
  await sleep(20); A().tick(); await sleep(20); A().tick();
  row("re-render during exit: one pane, leaving and inert", [bare(), probe()?.hasAttribute("data-leaving"), !!probe()?.inert], [1, true, true]);
  await sleep(leave + 40);
  row("re-render during exit: all gone", [bare(), real(), tools()], [0, 0, 0]);

  // Re-enter in the middle of an exit: no duplicate, no longer leaving.
  A().set(true); to("real", true); await sleep(300); A().set(false); to("real", false); await sleep(40); A().set(true); to("real", true); A().tick();
  await sleep(300);
  row("re-enter during exit: one pane, not leaving, not inert", [bare(), real(), probe()?.hasAttribute("data-leaving"), !!probe()?.inert], [1, 1, false, false]);
  A().set(false); to("real", false); await sleep(leave + 40);

  // Rapid toggle 20 times with a re-render each time; never two copies, always settles to the last request.
  for (const end of [false, true]) {
    let dup = 0;
    for (let i = 0; i < 20; i++) { A().toggle(); click("real"); click("tools"); A().tick(); await sleep(i % 3 ? 5 : 25); if (bare() > 1 || real() > 1 || tools() > 1) dup++; }
    A().set(end); to("real", end); to("tools", end);
    await sleep(400);
    row("rapid toggle x20 ending " + (end ? "open" : "closed"), [dup, bare(), real(), tools(), verdicts()], end ? [0, 1, 1, 1, 1] : [0, 0, 0, 0, 0]);
  }

  // Unmount mid-animation (enter and exit): no errors, nothing left behind, and a fresh mount works.
  A().set(false); to("real", false); to("tools", false); await sleep(leave + 40);
  A().set(true); await sleep(30); A().unmount(); await sleep(400);
  row("unmount mid-enter: nothing left", [q("[data-pane]"), q("#gone")], [0, 1]);
  A().mount(); await sleep(100); A().set(true); await sleep(300); A().set(false); await sleep(40); A().unmount(); await sleep(400);
  row("unmount mid-exit: nothing left", [q("[data-pane]"), q("#gone")], [0, 1]);
  A().mount(); await sleep(100);
  row("remount: closed", bare(), 0);
  A().set(true); await sleep(300);
  row("remount: opens once", bare(), 1);

  // Like the Inspector: state inside the pane changing (a scroll fade) while a disclosure inside it opens, and while the pane leaves and returns.
  const nested = () => q('[data-probe="nested"]'), nv = () => (document.getElementById("nested").textContent.match(/Safe to remove/g) || []).length;
  A().nest(true); await sleep(300);
  click("nested"); for (let i = 0; i < 8; i++) { A().bump(); await sleep(10); }
  await sleep(300); A().bump();
  row("state change inside the pane while a disclosure opens", [nested(), q("#nested [data-pane]"), nv()], [1, 2, 1]);
  A().nest(false); for (let i = 0; i < 5; i++) { A().bump(); await sleep(10); }
  A().nest(true); A().bump(); await sleep(300);
  row("pane leaves and returns during state changes", [nested(), nv()], [1, 1]);
  A().nest(false); await sleep(leave + 60);
  row("nested pane gone", [nested(), q("#nested [data-pane]")], [0, 0]);

  // A child with no Pane (like the Suspense skeleton) still unmounts after its exit.
  A().set(true); await sleep(100); row("pane-less child shows", q('[data-probe="plain"]'), 1);
  A().set(false); await sleep(leave + 60); row("pane-less child leaves, never stuck open", q('[data-probe="plain"]'), 0);
  A().set(true); await sleep(300);

  // Timing: full motion keeps the leaving pane about 180 ms, reduced motion about 120 ms.
  A().set(false); await sleep(reduced ? 60 : 100);
  row(reduced ? "reduced: still fading at 60ms" : "full: still leaving at 100ms", bare(), 1);
  await sleep(reduced ? 100 : 140);
  row(reduced ? "reduced: gone by 160ms" : "full: gone by 240ms", bare(), 0);
  row("no uncaught errors", errors, []);
  return JSON.stringify(rows);
})()`;

const failures = [];
try {
  for (const q of ["", "?reduced"]) {
    await ab("open", base + q);
    let rows = JSON.parse((await ab("eval", scenarios)).trim());
    if (typeof rows === "string") rows = JSON.parse(rows);
    for (const [name, got, want] of rows) {
      const ok = JSON.stringify(got) === JSON.stringify(want);
      console.log(`${ok ? "ok  " : "FAIL"} ${q ? "[reduced] " : ""}${name}: ${JSON.stringify(got)}${ok ? "" : ` (want ${JSON.stringify(want)})`}`);
      if (!ok) failures.push(name);
    }
  }
} finally {
  try { await ab("close"); } catch { /* already closed */ }
  await server.close();
}
if (failures.length) { console.error(`\n${failures.length} presence check(s) failed.`); process.exit(1); }
console.log("Presence stress passes.");
