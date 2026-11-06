// Replays the repro sequences of docs/plans/interaction-bugs.md (#49 stuck dimmed map, #50 cluster-name clicks).
// Demo data only: never point it at a real scan. The dev server must be `npm run dev` proxied to
// `constellation open docs/design/demo-250.json` (it needs the dev-only window.__cx hook); the chat case needs the BUILT
// server (the vite proxy answers chat with 403).
//   node scripts/interaction-check.mjs http://localhost:5199 http://127.0.0.1:8795
import { execFileSync } from "node:child_process";

const [dev, built] = process.argv.slice(2);
const loop = /^http:\/\/(127\.0\.0\.1|localhost):\d+\/?$/;
if (!loop.test(dev ?? "") || !loop.test(built ?? "")) throw new Error("Pass two loopback URLs: the vite dev server and the built demo-250 server");
const session = execFileSync("agent-browser", ["session", "id", "--scope", "worktree", "--prefix", "interaction"], { encoding: "utf8" }).trim();
const ab = (...args) => execFileSync("agent-browser", ["--session", session, ...args.map((a) => typeof a === "number" ? String(Math.round(a)) : a)], { encoding: "utf8", timeout: 120000 });
const ev = (js) => { const out = ab("eval", `(async () => JSON.stringify(await (async () => (${js}))()))()`).trim(); if (out === "undefined") return undefined; let r = JSON.parse(out); if (typeof r === "string") r = JSON.parse(r); return r; };
const settle = (ms = 1500) => ab("wait", String(ms));
const failures = [];
const report = (name, got, want, ok = got === want) => { console.log(`${ok ? "ok  " : "FAIL"} ${name}: ${got} (want ${want})`); if (!ok) failures.push(name); };

const dim = () => ev("__cx.model.nodes.filter((n) => n.a < 0.5).length");
const chip = () => ev('!!Array.from(document.querySelectorAll("p,div,span")).find((e) => /highlighted\\s·\\sfrom/.test(e.textContent) && e.children.length < 3)');
const wrap = 'document.querySelector("[role=application]")';
// a point clear of every star (30 px), every name box and the chrome, so a click there is a click on empty sky
const sky = () => ev(`(() => {
  const ns = __cx.model.nodes.map((n) => __cx.at(n)), cs = __cx.model.clusters;
  for (let y = 140; y < innerHeight - 40; y += 20) for (let x = 440; x < innerWidth - 40; x += 20) {
    if (ns.some((p) => Math.hypot(p.x - x, p.y - y) < 30) || cs.some((c) => c.hit && x > c.box[0] - 10 && x < c.box[2] + 10 && y > c.box[1] - 10 && y < c.box[3] + 10)) continue;
    if (${wrap}.contains(document.elementFromPoint(x, y))) return { x, y };
  }
})()`);
const open = (url, w = 1440) => { ab("set", "viewport", String(w), "900"); ab("open", url); settle(3000); };
const click = ({ x, y }) => { ab("mouse", "move", x, y); ab("mouse", "down"); ab("mouse", "up"); };
const center = (cond) => ev(`(() => { const c = __cx.model.clusters.find((c) => ${cond}); return { x: (c.box[0] + c.box[2]) / 2, y: (c.box[1] + c.box[3]) / 2 }; })()`);

const dev1 = dev.replace(/\/$/, "");
try {
  // A: search highlight, then a click on empty sky and Esc on the map
  const search = () => { ab("find", "role", "combobox", "click"); ab("keyboard", "type", "idle"); settle(); };
  open(dev1);
  search();
  report("A search dims", dim() > 100, true);
  click(sky());
  settle();
  report("A after click on empty sky: dimmed Items", dim(), 0);
  report("A after click on empty sky: chip", chip(), false);
  open(dev1);
  search();
  ev(`${wrap}.focus()`);
  // the first Esc may be taken by the open results popover (it prevents default); the map must clear by the second
  let presses = 0;
  while (presses < 2 && (presses++, ab("press", "Escape"), settle(700), dim() > 0));
  report(`A after Esc on the map (${presses} press${presses > 1 ? "es" : ""}): dimmed Items`, dim(), 0);

  // C: hover a hub, then jump straight onto the search box
  open(dev1);
  const hub = ev("(() => { const n = __cx.model.nodes.filter((n) => { const p = __cx.at(n); return p.x > 500 && p.y > 200 && p.y < 700; }).sort((a, b) => b.r - a.r)[0]; return __cx.at(n); })()");
  ab("mouse", "move", hub.x - 20, hub.y - 20);
  ab("mouse", "move", hub.x, hub.y, "--steps", "6");
  settle(600);
  report("C hovering a hub dims", dim() > 100, true);
  const box = ev('(() => { const r = document.querySelector("input").getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()');
  ab("mouse", "move", box.x, box.y); // one jump: the pointer never crosses empty canvas
  settle();
  report("C pointer on the search box: dimmed Items", dim(), 0);

  // D: enter a cluster, hover a card row, leave with Esc
  open(dev1);
  click(center("c.hit && c.box[0] > 480 && c.box[1] > 140"));
  try { ab("wait", "--fn", '!!document.querySelector(\'section[aria-labelledby="cluster-title"]\')'); } catch { report("D click on a name enters the cluster", false, true); }
  settle(1800);
  ab("eval", 'document.querySelector("section[aria-labelledby=cluster-title] details")?.setAttribute("open", "")');
  const row = ev('(() => { const b = document.querySelector("section[aria-labelledby=cluster-title] details li") ?? document.querySelector("input"); const r = b.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()');
  ab("mouse", "move", row.x, row.y, "--steps", "3");
  settle(600);
  report("D hovering a card row dims", dim() > 100, true);
  ab("press", "Escape");
  settle();
  report("D after Esc leaves the cluster: dimmed Items", dim(), 0);

  // B: chat highlight on the built server
  open(built);
  ab("find", "role", "button", "click", "--name", "Ask");
  ab("find", "placeholder", "Ask about this scan…", "fill", "What costs the most?");
  ab("press", "Enter");
  ab("wait", "--fn", "document.body.innerText.includes('from chat')");
  report("B chip shown after the question", chip(), true);
  // no __cx on the built server: take the first canvas point in the far corner (the fitted map leaves it empty)
  click(ev('(() => { for (let y = 150; y < 860; y += 10) { const e = document.elementFromPoint(1425, y); if (e?.tagName === "CANVAS") return { x: 1425, y }; } })()'));
  settle(800);
  report("B chip after click on empty sky", chip(), false);

  // #50: synthetic pointer events drive every name (fast); real mouse covers jitter, drag and a star below.
  const fire = (js) => ev(`(async () => {
    const w = ${wrap}, wait = (ms) => new Promise((r) => setTimeout(r, ms)), fc = __cx.painter.focus;
    const send = (type, x, y) => w.dispatchEvent(new PointerEvent(type, { bubbles: true, clientX: x, clientY: y, button: 0, buttons: type === "pointerup" ? 0 : 1, pointerType: "mouse", pointerId: 1 }));
    const idle = async () => { for (let i = 0; i < 60 && (fc.flying || fc.cluster); i++) { if (fc.cluster && !fc.flying) dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })); await wait(100); } await wait(300); };
    ${js}
  })()`);
  const sweep = (label, jitter) => {
    let ok = 0, tot = 0;
    const bad = [];
    for (const nm of ev("__cx.model.clusters.map((c) => c.name)")) {
      const r = fire(`
        await idle();
        const nm = ${JSON.stringify(nm)}, c = __cx.model.clusters.find((c) => c.name === nm);
        if (!c.hit || c.box[0] < 0 || c.box[2] > innerWidth || c.box[1] < 120 || c.box[3] > innerHeight) return null;
        const x = (c.box[0] + c.box[2]) / 2, y = (c.box[1] + c.box[3]) / 2;
        if (!w.contains(document.elementFromPoint(x, y))) return null;
        send("pointerdown", x, y);
        if (${jitter}) send("pointermove", x + ${jitter}, y);
        send("pointerup", x + ${jitter}, y);
        await wait(150);
        return !!fc.cluster && fc.cluster.name === nm;`);
      if (r === null) continue;
      tot++;
      if (r) ok++; else bad.push(nm);
    }
    report(`${label} name clicks${bad.length ? ` (missed: ${bad.slice(0, 3).join(", ")})` : ""}`, `${ok}/${tot}`, `${tot}/${tot}`, ok === tot && tot > 5);
  };
  for (const k of [1.0, 1.25, 1.4]) {
    open(dev1);
    if (k > 1) {
      ab("mouse", "move", "720", "450");
      ab("mouse", "wheel", String(Math.round(-Math.log(k) / 0.0015)));
      settle(1500);
    }
    sweep(`${k}x still`, 0);
    sweep(`${k}x 1 px move`, 1);
  }
  open(dev1);
  // a click on random points of a name's text (centre band of its box), fitted view
  let rok = 0, rtot = 0;
  for (const nm of ev("__cx.model.clusters.map((c) => c.name).slice(0, 24)")) {
    const r = fire(`
      await idle();
      const c = __cx.model.clusters.find((c) => c.name === ${JSON.stringify(nm)});
      if (!c.hit || c.box[0] < 0 || c.box[2] > innerWidth || c.box[1] < 120 || c.box[3] > innerHeight) return null;
      const x = c.box[0] + (c.box[2] - c.box[0]) * (0.3 + Math.random() * 0.4), y = (c.box[1] + c.box[3]) / 2 + (Math.random() - 0.5) * 12;
      if (!w.contains(document.elementFromPoint(x, y))) return null;
      send("pointerdown", x, y); send("pointerup", x, y);
      await wait(150);
      return !!fc.cluster && fc.cluster.name === ${JSON.stringify(nm)};`);
    if (r === null) continue;
    rtot++;
    if (r) rok++;
  }
  const rnd = { ok: rok, tot: rtot };
  report("random text points name clicks", `${rnd.ok}/${rnd.tot}`, `${rnd.tot}/${rnd.tot}`, rnd.ok === rnd.tot && rnd.tot > 5);
  // real mouse: 8 names, 1 px move between down and up
  const names = ev("__cx.model.clusters.filter((c) => c.hit && c.box[0] > 480 && c.box[2] < innerWidth - 40 && c.box[1] > 140).slice(0, 8).map((c) => c.name)");
  let real = 0;
  for (const nm of names) {
    fire("await idle()");
    const p = center(`c.name === ${JSON.stringify(nm)}`);
    ab("mouse", "move", p.x, p.y);
    ab("mouse", "down");
    ab("mouse", "move", p.x + 1, p.y);
    ab("mouse", "up");
    settle(300);
    if (ev(`__cx.painter.focus.cluster?.name === ${JSON.stringify(nm)}`)) real++;
  }
  report("real mouse, 1 px move between down and up", `${real}/${names.length}`, `${names.length}/${names.length}`, real === names.length);
  fire("await idle()");
  // a real 20 px drag from a name pans and does not enter
  const dn = center("c.hit && c.box[0] > 480 && c.box[2] < innerWidth - 80 && c.box[1] > 140");
  ab("mouse", "move", dn.x, dn.y);
  ab("mouse", "down");
  ab("mouse", "move", dn.x + 20, dn.y, "--steps", "5");
  ab("mouse", "up");
  settle(500);
  report("20 px drag from a name enters", ev("!!__cx.painter.focus.cluster"), false);
  // a still click on a star outside any name box still selects it
  const star = ev(`(() => {
    const cs = __cx.model.clusters, at = (n) => __cx.at(n);
    const n = __cx.model.nodes.find((n) => { const p = at(n); return p.x > 480 && p.x < innerWidth - 40 && p.y > 140 && p.y < innerHeight - 40 && n.a > 0.9
      && !cs.some((c) => c.hit && p.x > c.box[0] - 12 && p.x < c.box[2] + 12 && p.y > c.box[1] - 12 && p.y < c.box[3] + 12)
      && !__cx.model.nodes.some((m) => m !== n && Math.hypot(at(m).x - p.x, at(m).y - p.y) < 14); });
    return at(n);
  })()`);
  click(star);
  settle(500);
  report("still click on a star outside any name box selects it", ev("!!__cx.painter.focus.selected"), true);
} finally {
  try { ab("close"); } catch { /* the browser may already be gone */ }
}
if (failures.length) { console.error(`\n${failures.length} check(s) failed: ${failures.join("; ")}`); process.exit(1); }
console.log("\nAll interaction checks passed.");
