// Sky lab: render the Milky Way layers (src/graph/sky.ts, pure) to a PNG in Node, composited over the body gradient the
// way the page does, with the graph-box mask. For fast look-and-fix rounds; not a gate.
// Run: node scripts/sky-render.ts out.png [w] [h] [subtle|rich] [graph box x,y,w,h]
import { readFileSync, writeFileSync } from "node:fs";
import { deflateSync, crc32 } from "node:zlib";
import { anchorPixels, bandPixels, fields, placeFor, starPixels, type Ink, type RGB, type Rect } from "../src/graph/sky.ts";
import { gain } from "../src/graph/skySettings.ts";

const [out = "sky.png", W = "1488", H = "948", mode = "subtle", box] = process.argv.slice(2);
const w = +W, h = +H, o = gain(mode === "rich" ? 2 : 1) / gain(2);
const graph: Rect | null = box ? (([x, y, bw, bh]) => ({ x, y, w: bw, h: bh }))(box.split(",").map(Number)) : null;

const css = readFileSync(new URL("../src/index.css", import.meta.url), "utf8");
const tok = (n: string) => css.match(new RegExp(`${n}:\\s*([^;]+);`))![1].trim();
const hex = (n: string): RGB => { const x = tok(n); return [1, 3, 5].map((i) => parseInt(x.slice(i, i + 2), 16)) as RGB; };
const ink: Ink = {
  core: hex("--sky-core"), rose: hex("--sky-rose"), arm: hex("--sky-arm"), star: hex("--text"), deep: hex("--surface-0"),
  band: +tok("--sky-band"), lane: +tok("--sky-lane"), outside: +tok("--sky-outside"), haze: +tok("--sky-haze"),
  dust: +tok("--sky-star"), anchor: +tok("--sky-anchor"), grain: +tok("--sky-grain"),
};

const t0 = performance.now(), p = placeFor(graph, w, h), f = fields(w, h, p), t1 = performance.now();
const band = bandPixels(w, h, f, ink), t2 = performance.now();
const stars = starPixels(w, h, 1, f, ink), t3 = performance.now();
const anchors = anchorPixels(w, h, 1, ink);
console.log(`place ${JSON.stringify(p)}  fields ${(t1 - t0) | 0}ms  band ${(t2 - t1) | 0}ms  stars ${(t3 - t2) | 0}ms`);

// body: radial-gradient(120% 90% at 50% 38%, night-lift 0%, night 62%) (vignette and nebula left out: they are faint)
const night = hex("--night"), lift = hex("--night-lift"), img = new Float32Array(w * h * 3);
for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
  const d = Math.hypot((x / w - 0.5) / 0.6, (y / h - 0.38) / 0.45), t = Math.min(1, d / 0.62 / 1.41), k = (y * w + x) * 3;
  for (let c = 0; c < 3; c++) img[k + c] = lift[c] + (night[c] - lift[c]) * t;
}
// the mask that dims the band behind the graph (index.css .sky-layer[data-layer=band])
const hole = (x: number, y: number) => {
  if (!graph) return 1;
  const q = Math.hypot((x - graph.x - graph.w / 2) / (graph.w * 0.7 + 60), (y - graph.y - graph.h / 2) / (graph.h * 0.7 + 60));
  return 0.22 + 0.78 * Math.min(1, Math.max(0, (q - 0.55) / 0.45));
};
const over = (src: Uint8ClampedArray, m: (x: number, y: number) => number) => {
  for (let i = 0; i < w * h; i++) {
    const a = (src[i * 4 + 3] / 255) * o * m(i % w, (i / w) | 0);
    for (let c = 0; c < 3; c++) img[i * 3 + c] += (src[i * 4 + c] - img[i * 3 + c]) * a;
  }
};
over(band, hole); over(stars.data, (x, y) => 0.4 + 0.6 * hole(x, y) ** 0.5); over(anchors.data, () => 1);

// contrast behind the graph box against --night-lift
const lum = (r: number, g: number, b: number) => [r, g, b].map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }).reduce((s, v, i) => s + v * [0.2126, 0.7152, 0.0722][i], 0);
const L0 = lum(...lift), ratios = (inBox: boolean) => {
  const r: number[] = [];
  for (let y = 0; y < h; y += 2) for (let x = 0; x < w; x += 2) {
    const g = graph && x > graph.x && x < graph.x + graph.w && y > graph.y && y < graph.y + graph.h;
    if (inBox !== !!g) continue;
    const k = (y * w + x) * 3, L = lum(img[k], img[k + 1], img[k + 2]);
    r.push(L > L0 ? (L + 0.05) / (L0 + 0.05) : 1);
  }
  r.sort((a, b) => a - b);
  return r.length ? `p50 ${r[r.length >> 1].toFixed(2)} p95 ${r[Math.floor(r.length * 0.95)].toFixed(2)} p99 ${r[Math.floor(r.length * 0.99)].toFixed(2)}` : "-";
};
console.log(`outside graph: ${ratios(false)}   graph box: ${ratios(true)}`);
if (graph) for (let x = graph.x; x < graph.x + graph.w; x++) for (const y of [graph.y, graph.y + graph.h - 1]) { const k = (y * w + x) * 3; img[k] = img[k + 1] = 90; img[k + 2] = 140; }

// minimal PNG encoder (RGB, filter 0)
const raw = Buffer.alloc((w * 3 + 1) * h);
for (let y = 0; y < h; y++) for (let x = 0; x < w * 3; x++) raw[y * (w * 3 + 1) + 1 + x] = Math.max(0, Math.min(255, Math.round(img[y * w * 3 + x])));
const chunk = (t: string, d: Buffer) => { const b = Buffer.alloc(12 + d.length); b.writeUInt32BE(d.length); b.write(t, 4); d.copy(b, 8); b.writeUInt32BE(crc32(b.subarray(4, 8 + d.length)), 8 + d.length); return b; };
const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(w); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 2;
writeFileSync(out, Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", ihdr), chunk("IDAT", deflateSync(raw)), chunk("IEND", Buffer.alloc(0))]));
