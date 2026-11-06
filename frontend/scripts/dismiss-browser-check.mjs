// Headless check that a click on the map canvas closes an open overlay and the end of a drag does not (docs/design/dismiss.md).
// Demo data only. Needs the BUILT server on demo-250: constellation open docs/design/demo-250.json --port 8812 --no-browser
//   node scripts/dismiss-browser-check.mjs http://127.0.0.1:8812
import { execFileSync } from "node:child_process";

const [url] = process.argv.slice(2);
if (!/^http:\/\/(127\.0\.0\.1|localhost):\d+\/?$/.test(url ?? "")) throw new Error("Pass one loopback URL: the built demo-250 server");
const session = execFileSync("agent-browser", ["session", "id", "--scope", "worktree", "--prefix", "dismiss"], { encoding: "utf8" }).trim();
const ab = (...args) => execFileSync("agent-browser", ["--session", session, ...args.map((a) => String(Math.round(+a) === +a && typeof a === "number" ? Math.round(a) : a))], { encoding: "utf8", timeout: 120000 });
const ev = (js) => { const out = ab("eval", `(async () => JSON.stringify(await (async () => (${js}))()))()`).trim(); let r = JSON.parse(out); if (typeof r === "string") { try { r = JSON.parse(r); } catch { /* plain string */ } } return r; };
const settle = (ms = 500) => ab("wait", String(ms));
const failures = [];
const report = (name, got, want) => { const ok = JSON.stringify(got) === JSON.stringify(want); console.log(`${ok ? "ok  " : "FAIL"} ${name}: ${JSON.stringify(got)} (want ${JSON.stringify(want)})`); if (!ok) failures.push(name); };
const popovers = () => ev('document.querySelectorAll("[data-slot=popover-content]:not([data-state=closed])").length');
const dialogs = () => ev('document.querySelectorAll("[role=dialog]:not([data-state=closed])").length');
const chat = () => ev('!!document.getElementById("chat-panel")');
const btn = (name) => ab("find", "role", "button", "click", "--name", name);
const click = ({ x, y }) => { ab("mouse", "move", x, y); ab("mouse", "down"); ab("mouse", "up"); settle(); };
const drag = ({ x, y }) => { ab("mouse", "move", x, y); ab("mouse", "down"); ab("mouse", "move", x - 60, y + 30, "--steps", "6"); ab("mouse", "up"); settle(); };
const reload = () => { ab("set", "viewport", "1440", "900"); ab("open", url); settle(2500); };

try {
  reload();
  const spot = ev('(() => { for (let y = 150; y < 860; y += 10) { const e = document.elementFromPoint(1425, y); if (e?.tagName === "CANVAS") return { x: 1425, y }; } })()');
  btn("Sky settings"); settle();
  report("Sky open", popovers(), 1);
  click(spot);
  report("click on canvas closes Sky", popovers(), 0);
  btn("Sky settings"); settle();
  drag(spot);
  report("end of a drag keeps Sky open", popovers(), 1);
  btn("Sky settings"); settle();
  report("trigger again closes Sky (toggle, no reopen)", popovers(), 0);
  btn("Sky settings"); settle();
  btn("History"); settle();
  report("opening History closes Sky", popovers(), 1);
  ab("press", "Escape"); settle();
  report("Escape closes History", popovers(), 0);
  report("Escape returns focus to the History button", ev("document.activeElement?.textContent?.trim()"), "History");
  btn("Sky settings"); settle();
  btn("Close"); settle();
  report("the X closes Sky", popovers(), 0);
  // touch: a tap on the canvas (pointerType touch) closes (a touch drag is covered in dismiss:check; synthetic moves are not a real force-graph pan)
  btn("Sky settings"); settle();
  const touch = (moves = false) => ev(`(() => { const c = document.elementFromPoint(${spot.x}, ${spot.y}), o = (type, x) => c.dispatchEvent(new PointerEvent(type, { bubbles: true, composed: true, clientX: x, clientY: ${spot.y}, pointerId: 7, pointerType: "touch", button: 0 })); o("pointerdown", ${spot.x}); ${moves ? `o("pointermove", ${spot.x - 50}); o("pointerup", ${spot.x - 50});` : `o("pointerup", ${spot.x});`} return true; })()`);
  touch(); settle(300);
  report("touch tap on canvas closes Sky", popovers(), 0);
  // Explain dialog: a click beside it closes it
  btn("Explain my setup"); settle(800);
  report("Explain open", dialogs(), 1);
  ab("mouse", "move", "20", "450"); ab("mouse", "down"); ab("mouse", "up"); settle(600);
  report("click beside Explain closes it", dialogs(), 0);
  // Ask: empty sky closes, a drag does not
  btn("Ask"); settle(600);
  report("Ask open", chat(), true);
  drag(spot);
  report("end of a drag keeps Ask open", chat(), true);
  click(spot);
  report("click on empty sky closes Ask", chat(), false);
} finally {
  try { ab("close"); } catch { /* already closed */ }
}
if (failures.length) { console.error(`FAILED: ${failures.join(", ")}`); process.exit(1); }
console.log("Dismiss browser check passes.");
