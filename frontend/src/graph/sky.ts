// The deep field behind the map (docs/design/sky-pattern.md): a Milky Way band with a warm core bulge and cool arms,
// broken dust lanes, star density that follows the band, a few soft bright stars and a film grain. It is rendered once
// per viewport size and settings into a blob image that CSS shows on body::before, so panning, zooming and dragging
// never repaint it. The seed is fixed, so it is the same sky on every load.
import { fieldKey, gain, getSky, onSky, type SkySettings } from "./skySettings.ts";

const SEED = 60;
const hash = (x: number, y: number) => { // integer lattice to [0, 1)
  let h = Math.imul(x, 374761393) + Math.imul(y, 668265263) + SEED * 1442695041;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
};
function noise(x: number, y: number) { // value noise, smoothstep-interpolated
  const xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi;
  const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
  const a = hash(xi, yi), b = hash(xi + 1, yi), c = hash(xi, yi + 1), d = hash(xi + 1, yi + 1);
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
}
export function fbm(x: number, y: number, oct: number) {
  let s = 0, amp = 0.5, norm = 0;
  for (let i = 0; i < oct; i++) { s += amp * noise(x, y); norm += amp; x = x * 2.03 + 17.1; y = y * 2.03 + 3.7; amp *= 0.5; }
  return s / norm;
}
const ridge = (x: number, y: number) => 1 - Math.abs(2 * fbm(x, y, 4) - 1); // thin bright ridges where fbm crosses 0.5: filaments
const smooth = (a: number, b: number, x: number) => { const t = Math.max(0, Math.min(1, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
const rand = (seed: number) => () => { // mulberry32 for star placement
  seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};

type RGB = [number, number, number];
function inks() {
  const css = getComputedStyle(document.documentElement);
  const t = (n: string) => css.getPropertyValue(n).trim();
  const probe = document.createElement("canvas").getContext("2d")!;
  const rgb = (n: string): RGB => { probe.fillStyle = t(n); const x = probe.fillStyle; return [1, 3, 5].map((i) => parseInt(x.slice(i, i + 2), 16)) as RGB; };
  const num = (n: string, d: number) => Number(t(n)) || d;
  return {
    arm: rgb("--indigo"), cool: rgb("--halo-name"), warm: rgb("--k-plugin"), star: rgb("--text"), lane: rgb("--surface-0"),
    band: num("--sky-band", 0.13), dust: num("--sky-star", 0.34), anchor: num("--sky-anchor", 0.45), grain: num("--sky-grain", 0.03), laneA: num("--sky-lane", 0.3),
  };
}
const mix = (a: RGB, b: RGB, t: number): RGB => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
const css = (c: RGB, a: number) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a})`;

// Band geometry in screen px: the axis runs from the lower left to the upper right, its core bulge sits in the lower
// left (away from the map), and the band dims over the middle of the screen, where the stars and names are densest.
export function bandAt(x: number, y: number, w: number, h: number) {
  const span = Math.max(w, h), ax = { x: -0.04 * w, y: 0.9 * h }, bx = { x: 1.04 * w, y: 0.08 * h };
  const dx = bx.x - ax.x, dy = bx.y - ax.y, len = Math.hypot(dx, dy);
  const s = ((x - ax.x) * dx + (y - ax.y) * dy) / (len * len);
  const wob = (fbm(s * 3.1, 7.3, 3) - 0.5) * 0.09 * span; // the plane wanders a little, so it is not a ruler line
  const d = ((x - ax.x) * dy - (y - ax.y) * dx) / len - wob;
  const bulge = Math.exp(-(((s - 0.3) / 0.13) ** 2));
  const W = 0.07 * span * (1 + 0.9 * bulge);
  const core = Math.exp(-((d / W) ** 2)), halo = Math.exp(-((d / (2.4 * W)) ** 2));
  const cx = x / w - 0.56, cy = y / h - 0.48, map = 1 - 0.55 * Math.exp(-((cx / 0.3) ** 2 + (cy / 0.32) ** 2));
  return { s, d, W, bulge, core, halo, map };
}

const SCALE = 3; // the nebula is soft, so it is computed at a third of CSS px and smoothed up; stars are drawn at full res

function render(w: number, h: number, set: SkySettings) {
  const ink = inks(), g0 = gain(set.strength);
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  const c = document.createElement("canvas");
  c.width = Math.round(w * dpr); c.height = Math.round(h * dpr);
  const g = c.getContext("2d")!;
  g.scale(dpr, dpr);
  const lw = Math.ceil(w / SCALE), lh = Math.ceil(h / SCALE);
  const dens = new Float32Array(lw * lh); // star density per low-res cell, read when placing stars
  const neb = new ImageData(lw, lh), lane = new ImageData(lw, lh);
  for (let j = 0; j < lh; j++) for (let i = 0; i < lw; i++) {
    const x = i * SCALE, y = j * SCALE, b = bandAt(x, y, w, h);
    const clump = 0.35 + 0.95 * fbm(x / 70, y / 70, 5); // fine star-cloud texture, several octaves
    const fil = smooth(0.84, 0.97, ridge(x / 95 + b.s * 2, y / 95)) * Math.exp(-((b.d / (0.9 * b.W)) ** 2));
    const rift = Math.exp(-(((b.d + 0.18 * b.W) / (0.16 * b.W)) ** 2)) * smooth(0.38, 0.62, fbm(b.s * 9, 1.7, 3)); // the broken central rift
    const cut = Math.min(1, fil * 0.9 + rift);
    const lum = (b.core * (0.7 + 0.7 * b.bulge) + b.halo * 0.14) * clump * (1 - 0.8 * cut) * b.map;
    dens[j * lw + i] = lum * (1 - 0.6 * cut) + 0.04;
    const col = mix(mix(ink.arm, ink.cool, b.core), ink.warm, b.bulge * b.core * 0.85); // warm core, cool arms, indigo halo
    const k = (j * lw + i) * 4;
    neb.data[k] = col[0]; neb.data[k + 1] = col[1]; neb.data[k + 2] = col[2];
    neb.data[k + 3] = set.band ? Math.min(255, lum * ink.band * g0 * 255) : 0;
    lane.data[k] = ink.lane[0]; lane.data[k + 1] = ink.lane[1]; lane.data[k + 2] = ink.lane[2];
    lane.data[k + 3] = set.band ? cut * b.core * ink.laneA * Math.min(1, g0) * 255 : 0;
  }
  const up = (img: ImageData) => { const t = document.createElement("canvas"); t.width = lw; t.height = lh; t.getContext("2d")!.putImageData(img, 0, 0); return t; };
  g.imageSmoothingEnabled = true; g.imageSmoothingQuality = "high";
  g.drawImage(up(lane), 0, 0, lw * SCALE, lh * SCALE);
  g.drawImage(up(neb), 0, 0, lw * SCALE, lh * SCALE);

  const r = rand(SEED), at = (x: number, y: number) => dens[Math.min(lh - 1, Math.max(0, (y / SCALE) | 0)) * lw + Math.min(lw - 1, Math.max(0, (x / SCALE) | 0))];
  if (set.dust) {
    const n = Math.round((w * h) / 380); // candidates; density keeps about a quarter, far more in the band than outside
    for (let i = 0; i < n; i++) {
      const x = r() * w, y = r() * h, p = at(x, y), k = r();
      if (r() > Math.min(1, p * 1.6)) continue;
      const tone = k < 0.12 ? ink.warm : k < 0.3 ? ink.cool : ink.star;
      const a = ink.dust * g0 * (0.18 + 0.82 * r() ** 2.2); // mostly faint, a few brighter
      g.fillStyle = css(tone, Math.min(1, a));
      const s = r() < 0.92 ? 0.55 + r() * 0.45 : 1.15;
      g.fillRect(x, y, s, s);
    }
  }
  if (set.anchors) for (let i = 0, placed = 0; i < 80 && placed < 10; i++) {
    const x = r() * w, y = r() * h;
    if (Math.hypot((x / w - 0.56) / 0.62, (y / h - 0.48) / 0.7) < 0.5) continue; // not behind the map's dense middle
    placed++;
    const tone = [ink.star, ink.cool, ink.warm][placed % 3], a = Math.min(1, ink.anchor * g0 * (0.65 + r() * 0.35)), R = 5 + r() * 4;
    const gr = g.createRadialGradient(x, y, 0, x, y, R); // soft glow, no diffraction spikes
    gr.addColorStop(0, css(tone, a * 0.32)); gr.addColorStop(0.35, css(tone, a * 0.08)); gr.addColorStop(1, css(tone, 0));
    g.fillStyle = gr; g.fillRect(x - R, y - R, R * 2, R * 2);
    g.fillStyle = css(tone, a); g.beginPath(); g.arc(x, y, 0.9, 0, Math.PI * 2); g.fill();
  }
  if (set.grain) { // a 128px tile of random specks, repeated: breaks the gradient banding of the dark navy
    const T = 128, tile = new ImageData(T, T), rg = rand(SEED + 1);
    for (let i = 0; i < T * T; i++) { tile.data.set(ink.star, i * 4); tile.data[i * 4 + 3] = rg() * ink.grain * g0 * 255; }
    const tc = document.createElement("canvas"); tc.width = tc.height = T; tc.getContext("2d")!.putImageData(tile, 0, 0);
    g.setTransform(1, 0, 0, 1, 0, 0); // device px, so the grain stays one pixel fine on retina
    g.fillStyle = g.createPattern(tc, "repeat")!; g.fillRect(0, 0, c.width, c.height);
  }
  return c;
}

let url = "", timer = 0, last = "";
function paint() {
  const s = getSky(), key = `${innerWidth}x${innerHeight}:${fieldKey(s)}`;
  if (key === last) return; // only a size change or a field setting re-renders
  last = key;
  const on = s.strength > 0 && (s.band || s.dust || s.anchors || s.grain);
  if (on) document.documentElement.dataset.skyOn = ""; else delete document.documentElement.dataset.skyOn;
  if (!on) return;
  const t0 = performance.now(), c = render(innerWidth + 48, innerHeight + 48, s); // inset -24px, so the drift never shows an edge
  performance.measure("sky-render", { start: t0 }); // one entry per render, read by the screenshot harness
  c.toBlob((b) => {
    if (!b || last !== key) return;
    if (url) URL.revokeObjectURL(url);
    url = URL.createObjectURL(b);
    document.documentElement.style.setProperty("--sky-field", `url(${url})`);
  });
}
export function startSky() {
  paint();
  onSky(paint);
  addEventListener("resize", () => { clearTimeout(timer); timer = window.setTimeout(paint, 250); });
}
