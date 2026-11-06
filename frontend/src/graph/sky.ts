// The Milky Way behind the map (docs/design/sky-pattern.md). Four image layers (band, star dust, bright stars, grain),
// each rendered once per window size into its own blob image on a fixed element under #root. A Sky setting change only
// sets a layer's CSS opacity (a 240ms fade, instant under reduced motion): it never re-renders. Panning, zooming and
// dragging never touch these layers. The seed is fixed, so it is the same sky on every load.
import { IMAGE_LAYERS, getSky, layerOpacity, onSky, type ImageLayer } from "./skySettings.ts";

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
    core: rgb("--sky-core"), rose: rgb("--sky-rose"), arm: rgb("--sky-arm"), star: rgb("--text"), deep: rgb("--surface-0"),
    band: num("--sky-band", 0.2), lane: num("--sky-lane", 0.5), outside: num("--sky-outside", 0.3), haze: num("--sky-haze", 0.12),
    dust: num("--sky-star", 0.5), anchor: num("--sky-anchor", 0.7), grain: num("--sky-grain", 0.045),
  };
}
const mix = (a: RGB, b: RGB, t: number): RGB => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
const rgba = (c: RGB, a: number) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a})`;

// Band geometry in screen px: the plane runs from the lower left to the upper right, the core bulge sits in the lower
// left (away from the map), and the band dims by up to 65% over the middle of the screen, where the graph is densest.
// shortcut: the dimming is a fixed screen ellipse, not the map's live bounding box; follow the map if panning makes it matter
export function bandAt(x: number, y: number, w: number, h: number) {
  const span = Math.max(w, h), ax = -0.04 * w, ay = 0.9 * h, dx = 1.08 * w, dy = -0.82 * h, len = Math.hypot(dx, dy);
  const s = ((x - ax) * dx + (y - ay) * dy) / (len * len);
  const wob = (fbm(s * 2.6, 7.3, 3) - 0.5) * 0.08 * span; // the plane wanders a little, so it is not a ruler line
  const d = ((x - ax) * dy - (y - ay) * dx) / len - wob;
  const bulge = Math.exp(-(((s - 0.33) / 0.12) ** 2));
  const W = 0.075 * span * (1 + 0.7 * bulge);
  const core = Math.exp(-((d / W) ** 2)), halo = Math.exp(-((d / (2.6 * W)) ** 2));
  const glow = bulge * Math.exp(-((d / (1.5 * W)) ** 2)); // the luminous bulge
  const cx = x / w - 0.56, cy = y / h - 0.48, map = 1 - 0.65 * Math.exp(-((cx / 0.34) ** 2 + (cy / 0.38) ** 2));
  return { s, d, W, bulge, core, halo, glow, map };
}

const SCALE = 4; // glow and dust are soft, so they are computed at a quarter of CSS px and smoothed up

// Shared fields, computed once per size: glow brightness, dust density (blurred, so lanes have feathered edges) and the
// star density that both other layers read.
function fields(w: number, h: number) {
  const lw = Math.ceil(w / SCALE) + 1, lh = Math.ceil(h / SCALE) + 1, n = lw * lh;
  const glow = new Float32Array(n), dust = new Float32Array(n), warm = new Float32Array(n), hue = new Float32Array(n), halo = new Float32Array(n), map = new Float32Array(n);
  for (let j = 0; j < lh; j++) for (let i = 0; i < lw; i++) {
    const x = i * SCALE, y = j * SCALE, b = bandAt(x, y, w, h), k = j * lw + i;
    // domain warping (Inigo Quilez): fbm of fbm, so clouds fold instead of looking like plain noise
    const px = x / 240, py = y / 240, qx = fbm(px, py, 3), qy = fbm(px + 5.2, py + 1.3, 3);
    const D = fbm(px * 1.4 + 3 * qx, py * 1.4 + 3 * qy, 4);
    // dust lies on the plane, a little below it, thickest in the core
    const plane = Math.exp(-(((b.d + 0.15 * b.W) / (1.1 * b.W)) ** 2));
    const rift = Math.exp(-(((b.d + 0.08 * b.W) / (0.3 * b.W)) ** 2)) * smooth(0.3, 0.6, fbm(b.s * 6 + qx, 3.3, 3)); // the broken Great Rift along the plane
    dust[k] = Math.min(1, smooth(0.36, 0.62, D) * plane + 0.75 * rift);
    const clouds = 0.45 + 0.85 * fbm(x / 90 + 2 * qx, y / 90 + 2 * qy, 5); // star clouds
    glow[k] = ((0.75 * b.core + 0.22 * b.halo) * clouds + 1.25 * b.glow * (0.75 + 0.4 * clouds)) * b.map;
    warm[k] = Math.min(1, b.glow * 1.3);
    hue[k] = fbm(x / 400 + 9, y / 400, 2); // slow magenta to violet drift along the arms
    halo[k] = b.halo; map[k] = b.map;
  }
  // feather the lanes: two separable box-blur passes (radius 2 cells, 8 CSS px)
  const tmp = new Float32Array(n);
  for (let pass = 0; pass < 2; pass++) {
    for (let j = 0; j < lh; j++) for (let i = 0; i < lw; i++) { let s = 0, c = 0; for (let o = -2; o <= 2; o++) { const ii = i + o; if (ii >= 0 && ii < lw) { s += dust[j * lw + ii]; c++; } } tmp[j * lw + i] = s / c; }
    for (let j = 0; j < lh; j++) for (let i = 0; i < lw; i++) { let s = 0, c = 0; for (let o = -2; o <= 2; o++) { const jj = j + o; if (jj >= 0 && jj < lh) { s += tmp[jj * lw + i]; c++; } } dust[j * lw + i] = s / c; }
  }
  const at = (a: Float32Array, x: number, y: number) => { // bilinear lookup in CSS px
    const fx = Math.min(lw - 1.001, Math.max(0, x / SCALE)), fy = Math.min(lh - 1.001, Math.max(0, y / SCALE)), i = fx | 0, j = fy | 0, u = fx - i, v = fy - j, k = j * lw + i;
    return a[k] * (1 - u) * (1 - v) + a[k + 1] * u * (1 - v) + a[k + lw] * (1 - u) * v + a[k + lw + 1] * u * v;
  };
  return { lw, lh, glow, dust, warm, hue, halo, map, at };
}
type Fields = ReturnType<typeof fields>;

function canvas(w: number, h: number) {
  const dpr = Math.min(2, window.devicePixelRatio || 1), c = document.createElement("canvas");
  c.width = Math.round(w * dpr); c.height = Math.round(h * dpr);
  return { c, g: c.getContext("2d")!, dpr };
}

// The band: near-black navy outside it, feathered dust over it, the glow (warm core, rose, lavender arms) and the
// unresolved-star haze, which is what makes the core read milky. All at the Rich strength; CSS opacity scales it down.
function renderBand(w: number, h: number, f: Fields, ink: ReturnType<typeof inks>) {
  const { c, g } = canvas(w, h), { lw, lh } = f;
  const dark = new ImageData(lw, lh), lit = new ImageData(lw, lh);
  for (let k = 0; k < lw * lh; k++) {
    const D = f.dust[k], o = k * 4;
    dark.data.set(ink.deep, o);
    dark.data[o + 3] = Math.min(1, 1 - (1 - ink.outside * (1 - f.halo[k])) * (1 - ink.lane * D)) * 255;
    let col = mix(ink.arm, ink.rose, 0.25 + 0.45 * f.hue[k]);
    col = mix(col, ink.core, f.warm[k]);
    col = mix(col, ink.rose, smooth(0.15, 0.5, D) * (1 - smooth(0.5, 0.9, D)) * 0.5); // dust reddens light at its edges, as in Gaia's colour map
    lit.data.set(col.map((v) => v | 0), o);
    lit.data[o + 3] = Math.min(1, f.glow[k] * (1 - 0.9 * D) * ink.band) * 255;
  }
  const up = (img: ImageData) => { const t = document.createElement("canvas"); t.width = lw; t.height = lh; t.getContext("2d")!.putImageData(img, 0, 0); return t; };
  g.imageSmoothingEnabled = true; g.imageSmoothingQuality = "high";
  g.drawImage(up(dark), 0, 0, lw * SCALE * (c.width / w), lh * SCALE * (c.height / h));
  g.drawImage(up(lit), 0, 0, lw * SCALE * (c.width / w), lh * SCALE * (c.height / h));
  // haze: per-pixel white noise weighted by the glow, at device px; cubed so it is mostly dark with fine bright grains
  const W = c.width, H = c.height, s = w / W, hz = g.getImageData(0, 0, W, H), d = hz.data;
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const cx = x * s, cy = y * s, gl = f.at(f.glow, cx, cy) * (1 - 0.85 * f.at(f.dust, cx, cy)) * f.at(f.map, cx, cy); // the haze thins twice behind the map
    if (gl < 0.04) continue;
    const r = hash(x, y + 9999), a = r * r * r * gl * ink.haze * 255, o = (y * W + x) * 4, t = a / 255;
    d[o] += (ink.star[0] - d[o]) * t; d[o + 1] += (ink.star[1] - d[o + 1]) * t; d[o + 2] += (ink.star[2] - d[o + 2]) * t; d[o + 3] = Math.min(255, d[o + 3] + a);
  }
  g.putImageData(hz, 0, 0);
  return c;
}

// Star dust: thousands of tiny stars, a power-law magnitude spread (many faint, few bright), dense in the band, thinned
// by dust, a few warm and cool ones.
function renderDust(w: number, h: number, f: Fields, ink: ReturnType<typeof inks>) {
  const { c, g, dpr } = canvas(w, h), r = rand(SEED), n = Math.round((w * h) / 45);
  g.scale(dpr, dpr);
  for (let i = 0; i < n; i++) {
    const x = r() * w, y = r() * h, gl = f.at(f.glow, x, y), D = f.at(f.dust, x, y);
    if (r() > (0.1 + 0.9 * Math.min(1, gl * 1.3)) * (1 - 0.75 * D)) continue;
    const m = r() ** 4.5, k = r(); // magnitude: brightness ~ u^4.5
    const tone = k < 0.1 ? ink.core : k < 0.28 ? ink.arm : ink.star;
    g.fillStyle = rgba(tone, Math.min(1, ink.dust * (0.12 + 0.88 * m) * (0.5 + 0.5 * f.at(f.map, x, y))));
    const sz = m > 0.6 ? 1.3 : m > 0.25 ? 0.9 : 0.6;
    g.fillRect(x, y, sz, sz);
  }
  return c;
}

// Bright stars: a dozen with a soft halo and no diffraction spikes, kept out of the map's dense middle.
function renderAnchors(w: number, h: number, f: Fields, ink: ReturnType<typeof inks>) {
  const { c, g, dpr } = canvas(w, h), r = rand(SEED + 2);
  g.scale(dpr, dpr);
  for (let i = 0, placed = 0; i < 120 && placed < 12; i++) {
    const x = r() * w, y = r() * h;
    if (f.at(f.map, x, y) < 0.8) continue;
    placed++;
    const tone = [ink.star, ink.arm, ink.core][placed % 3], a = Math.min(1, ink.anchor * (0.55 + r() * 0.45)), R = 6 + r() * 6;
    const gr = g.createRadialGradient(x, y, 0, x, y, R);
    gr.addColorStop(0, rgba(tone, a * 0.35)); gr.addColorStop(0.3, rgba(tone, a * 0.09)); gr.addColorStop(1, rgba(tone, 0));
    g.fillStyle = gr; g.fillRect(x - R, y - R, R * 2, R * 2);
    g.fillStyle = rgba(tone, a); g.beginPath(); g.arc(x, y, 0.95, 0, Math.PI * 2); g.fill();
  }
  return c;
}

// Grain: a 128px tile of random specks in device px, repeated; it breaks the banding of the navy gradient.
function renderGrain(w: number, h: number, ink: ReturnType<typeof inks>) {
  const { c, g } = canvas(w, h), T = 128, tile = new ImageData(T, T), r = rand(SEED + 1);
  for (let i = 0; i < T * T; i++) { tile.data.set(ink.star, i * 4); tile.data[i * 4 + 3] = r() * ink.grain * 255; }
  const tc = document.createElement("canvas"); tc.width = tc.height = T; tc.getContext("2d")!.putImageData(tile, 0, 0);
  g.fillStyle = g.createPattern(tc, "repeat")!; g.fillRect(0, 0, c.width, c.height);
  return c;
}

// --- layers in the page ---------------------------------------------------------------------------------------------

const els = {} as Record<ImageLayer, HTMLDivElement>;
const urls: Partial<Record<ImageLayer, string>> = {};
let size = "", timer = 0;
export const sizeKey = (w: number, h: number) => `${w}x${h}`; // the only thing a render depends on (the seed is fixed)

// opacity only: no render, no layout. Measured as "sky-apply".
export function apply() {
  const t0 = performance.now(), o = layerOpacity(getSky());
  for (const k of IMAGE_LAYERS) els[k].style.opacity = String(o[k]);
  performance.measure("sky-apply", { start: t0 });
}

const idle = (f: () => void) => ("requestIdleCallback" in window ? requestIdleCallback(f, { timeout: 600 }) : setTimeout(f, 30));
function show(k: ImageLayer, c: HTMLCanvasElement, key: string) {
  c.toBlob((b) => {
    if (!b || key !== size) return;
    if (urls[k]) URL.revokeObjectURL(urls[k]!);
    urls[k] = URL.createObjectURL(b);
    els[k].style.backgroundImage = `url(${urls[k]})`;
  });
}

// Render every layer for the current size, cheap ones first, the band in idle time; each step is its own task so the
// first frames of the map are never blocked by the whole sky.
function renderAll() {
  const w = innerWidth + 48, h = innerHeight + 48, key = sizeKey(w, h); // the layers are inset -24px, so the drift never shows an edge
  if (key === size) return;
  size = key;
  const ink = inks();
  show("grain", renderGrain(w, h, ink), key);
  idle(() => {
    if (key !== size) return;
    const t0 = performance.now(), f = fields(w, h);
    show("anchors", renderAnchors(w, h, f, ink), key);
    show("dust", renderDust(w, h, f, ink), key);
    performance.measure("sky-render-stars", { start: t0 });
    idle(() => {
      if (key !== size) return;
      const t1 = performance.now();
      show("band", renderBand(w, h, f, ink), key);
      performance.measure("sky-render-band", { start: t1 });
    });
  });
}

export function startSky() {
  const root = document.createElement("div");
  root.className = "sky-layers";
  root.setAttribute("aria-hidden", "true");
  for (const k of ["band", "dust", "anchors", "grain"] as ImageLayer[]) { // paint order: band at the back
    const el = document.createElement("div");
    el.className = "sky-layer";
    root.append((els[k] = el));
  }
  document.body.prepend(root);
  apply();
  onSky(apply);
  renderAll();
  addEventListener("resize", () => { clearTimeout(timer); timer = window.setTimeout(renderAll, 250); });
}
