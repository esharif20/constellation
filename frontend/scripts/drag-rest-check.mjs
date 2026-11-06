// Headless check: after an elastic drag settles, the canvas (stars, links and cluster names) is pixel-identical to before the drag.
// Demo data only. Needs the BUILT server on demo-250: constellation open docs/design/demo-250.json --port 8813 --no-browser
//   node scripts/drag-rest-check.mjs http://127.0.0.1:8813
import { execFileSync } from "node:child_process";

const [url] = process.argv.slice(2);
if (!/^http:\/\/(127\.0\.0\.1|localhost):\d+\/?$/.test(url ?? "")) throw new Error("Pass one loopback URL: the built demo-250 server");
const session = execFileSync("agent-browser", ["session", "id", "--scope", "worktree", "--prefix", "dragrest"], { encoding: "utf8" }).trim();
const ab = (...a) => execFileSync("agent-browser", ["--session", session, ...a.map(String)], { encoding: "utf8", timeout: 120000 });
const shot = () => ab("eval", "(()=>{const s=document.querySelector('canvas').toDataURL();let h=0;for(let i=0;i<s.length;i++)h=(h*31+s.charCodeAt(i))|0;return h})()").trim();
try {
  ab("set", "viewport", "1440", "900"); ab("open", url); ab("wait", "3000"); ab("mouse", "move", "800", "600"); ab("wait", "1000");
  const before = shot();
  ab("mouse", "move", "1073", "333"); ab("mouse", "down");
  for (const [x, y] of [[1100, 360], [1150, 420], [1200, 480]]) ab("mouse", "move", x, y); // the first jump is far: the star's home must still be where it started
  ab("wait", "300"); ab("mouse", "up"); ab("mouse", "move", "800", "600"); ab("wait", "3500");
  const after = shot();
  console.log(before === after ? "ok   drag and release leaves the canvas as it was" : "FAIL canvas differs after settling");
  if (before !== after) process.exitCode = 1;
} finally { try { ab("close"); } catch { /* already closed */ } }
