// Panel-open cost on the demo-250 fixture: StarMap renders and frame times while panels open and close.
// Build with the counter, serve demo-250 on your own port, then:
//   VITE_RENDER_COUNT=1 npm run build && npm run motion:perf -- http://127.0.0.1:8800
import { execFileSync } from "node:child_process";

const url = process.argv[2];
if (!url || !/^http:\/\/(127\.0\.0\.1|localhost):\d+\/?$/.test(url)) throw new Error("Pass the loopback URL of the demo-250 fixture server");
const session = execFileSync("agent-browser", ["session", "id", "--scope", "worktree", "--prefix", "motion-perf"], { encoding: "utf8" }).trim();
const ab = (...a) => execFileSync("agent-browser", ["--session", session, ...a], { encoding: "utf8", timeout: 60000 });
const ev = (js) => ab("eval", js).trim();
const sampler = `(() => { const f = [], sm0 = window.__sm ?? 0, lt = []; try { new PerformanceObserver((l) => lt.push(...l.getEntries().map((e) => e.duration))).observe({ type: "longtask", buffered: false }); } catch {} let last = performance.now(), on = true; const t = (n) => { f.push(n - last); last = n; if (on) requestAnimationFrame(t); }; requestAnimationFrame(t); window.__stop = () => { on = false; const s = f.slice(1).sort((a, b) => a - b); return JSON.stringify({ frames: s.length, p50: +s[Math.floor(s.length / 2)].toFixed(1), p95: +s[Math.floor(s.length * 0.95)].toFixed(1), max: +s[s.length - 1].toFixed(1), over20: s.filter((x) => x > 20).length, longTasks: lt.length, starMapRenders: (window.__sm ?? 0) - sm0 }); }; })()`;
const press = (label) => `[...document.querySelectorAll("button")].find((b) => (b.getAttribute("aria-label") || b.textContent).trim().startsWith(${JSON.stringify(label)}))?.click()`;
const out = {};
try {
  ab("set", "viewport", "1440", "900");
  ab("open", url);
  ev('localStorage.setItem("constellation.brief", "closed")');
  ab("open", url);
  ab("wait", "--fn", "document.querySelectorAll('canvas').length > 0");
  ab("wait", "1500");
  const run = async (name, openJs, closeJs) => {
    ev(sampler);
    ev(openJs);
    ab("wait", "700");
    ev(closeJs);
    ab("wait", "500");
    out[name] = JSON.parse(JSON.parse(ev("window.__stop()")));
  };
  await run("brief", press("Cleanup brief"), press("Collapse cleanup brief"));
  await run("chat", press("Ask"), press("Collapse local chat"));
  await run("explain", press("Explain my setup"), `document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }))`);
  console.log(JSON.stringify(out, null, 1));
} finally {
  try { ab("close"); } catch { /* already closed */ }
}
