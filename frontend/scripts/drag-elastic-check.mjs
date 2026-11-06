// Headless check of the elastic drag over time, not just its end state. Demo data only. Needs the BUILT server on demo-250:
//   constellation open docs/design/demo-250.json --port 8813 --no-browser
//   node scripts/drag-elastic-check.mjs http://127.0.0.1:8813 [1440x900 390x844]
// While the pointer is held still the canvas must keep repainting (the neighbours chase the held star on springs), after release the
// star must overshoot its home before it rests, (the exact end position is drag-rest-check.mjs's job).
import { execFileSync } from "node:child_process";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [url, ...sizes] = process.argv.slice(2);
if (!/^http:\/\/(127\.0\.0\.1|localhost):\d+\/?$/.test(url ?? "")) throw new Error("Pass one loopback URL: the built demo-250 server");
const session = execFileSync("agent-browser", ["session", "id", "--scope", "worktree", "--prefix", "dragelastic"], { encoding: "utf8" }).trim();
const ab = (...a) => execFileSync("agent-browser", ["--session", session, ...a.map((v) => String(typeof v === "number" ? Math.round(v) : v))], { encoding: "utf8", timeout: 120000 });
const ev = (js) => JSON.parse(ab("eval", `JSON.stringify((()=>{${js}})())`).trim().replace(/^"|"$/g, "").replace(/\\"/g, '"'));
let failed = false;
const expect = (ok, msg) => { console.log(`${ok ? "ok  " : "FAIL"} ${msg}`); if (!ok) failed = true; };

// a leaf star of the demo-250 layout at load, per viewport (the layout and first camera are deterministic)
const STARS = { "1440x900": [1010, 540], "390x844": [234, 463] };

try {
  for (const size of sizes.length ? sizes : ["1440x900", "390x844"]) {
    const [w, h] = size.split("x").map(Number);
    ab("set", "viewport", w, h); ab("open", url); ab("wait", 3000); ab("mouse", "move", 5, h / 2); ab("wait", 800);
    const star = STARS[size];
    if (!star) throw new Error(`no star known for ${size}`);
    const [sx, sy] = star, dir = [(w / 2 - sx) / Math.hypot(w / 2 - sx, h / 2 - sy), (h / 2 - sy) / Math.hypot(w / 2 - sx, h / 2 - sy)];
    const far = Math.min(w, h) * 0.2, end = [sx + dir[0] * far, sy + dir[1] * far];
    // sampler: canvas hash per frame, and the pixel change inside a strip just past the star's home along its way back (overshoot)
    ab("eval", `(()=>{const c=document.querySelector('canvas'),g=c.getContext('2d'),r=c.width/innerWidth,hs=[],st=[];
      const strip=(a,b)=>{const px=${sx}-(${dir[0]})*(a+b)/2,py=${sy}-(${dir[1]})*(a+b)/2,s=Math.max(4,Math.round(10*r));return g.getImageData(Math.round(px*r-s/2),Math.round(py*r-s/2),s,s).data};
      const base=strip(6,20),diff=(d)=>{let t=0;for(let i=0;i<d.length;i++)t+=Math.abs(d[i]-base[i]);return t};
      const hash=()=>{const s=c.toDataURL();let h=0;for(let i=0;i<s.length;i+=7)h=(h*31+s.charCodeAt(i))|0;return h};
      window.__s={hs,st,on:true,tick(){hs.push(hash());st.push(diff(strip(6,20)))}};
      })();0`);
    ab("mouse", "move", sx, sy); ab("wait", 400); ab("mouse", "down"); // the hover pick needs a beat to land on the star
    ab("eval", "setInterval(() => { if (window.__s.on) window.__s.tick(); }, 40); 0"); // started only now: reading the canvas starves the hover pick
    for (let i = 1; i <= 4; i++) ab("mouse", "move", sx + (end[0] - sx) * i / 4, sy + (end[1] - sy) * i / 4);
    ab("eval", "window.__s.m1=window.__s.hs.length;0"); ab("wait", 600); ab("eval", "window.__s.m2=window.__s.hs.length;0"); ab("screenshot", join(tmpdir(), `drag-mid-${size}.png`));
    ab("mouse", "up"); ab("mouse", "move", 5, h / 2); ab("wait", 2500);
    const r = ev("const s=window.__s;s.on=false;const a=s.hs.slice(s.m1+2,s.m2),b=s.hs.slice(s.m2),q=s.st.slice(s.m2);return{hold:new Set(a).size,settle:new Set(b.slice(0,60)).size,peak:Math.max(...q)}");
    expect(r.hold >= 5, `${size}: canvas repaints while the pointer is held still (${r.hold} distinct frames): neighbours are being pulled`);
    expect(r.settle >= 8, `${size}: the settle after release animates (${r.settle} distinct frames)`);
    expect(r.peak > 400, `${size}: the star passes beyond its home (overshoot strip change ${r.peak})`);
  }
} finally { try { ab("close"); } catch { /* already closed */ } }
if (failed) process.exitCode = 1;
