// The Milky Way behind the map (docs/design/sky-pattern.md). Four image layers (band, star dust, bright stars, grain),
// each rendered once per window size (and band placement) into its own blob image on a fixed element under #root. A Sky
// setting change only sets a layer's CSS opacity: it never re-renders. Panning and zooming only move a CSS mask that
// dims the band behind the graph's live bounding box. The seed is fixed, so it is the same sky on every load.
// The renderers below are pure (numbers in, RGBA out), so scripts/sky-render.ts can draw them to PNG in Node.
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
// ridged multifractal: thin bright creases where the noise crosses 0.5, each octave weighted by the last, so the creases
// branch into finer ones (Musgrave). Used as dark dust filaments.
function ridged(x: number, y: number, oct: number) {
  let s = 0, amp = 0.5, norm = 0, prev = 1;
  for (let i = 0; i < oct; i++) {
    const r = (1 - Math.abs(2 * noise(x, y) - 1)) ** 2;
    s += amp * r * prev; norm += amp; prev = r; x = x * 2.1 + 5.3; y = y * 2.1 + 9.1; amp *= 0.55;
  }
  return s / norm;
}
const smooth = (a: number, b: number, x: number) => { const t = Math.max(0, Math.min(1, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
const rand = (seed: number) => () => { // mulberry32 for star placement
  seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};

export type RGB = [number, number, number];
export type Ink = { core: RGB; rose: RGB; arm: RGB; star: RGB; deep: RGB; band: number; lane: number; outside: number; haze: number; dust: number; anchor: number; grain: number };
const mix = (a: RGB, b: RGB, t: number): RGB => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];

// --- geometry: one galaxy frame for every layer -------------------------------------------------------------------
// u runs along the galactic plane, v across it. The plane is tilted along most of the screen diagonal (steeper on a
// phone). `side` puts the bulge at the lower left (1) or the upper right (-1); `shift` moves the plane across, in
// short-side units. Both are chosen to keep the bright parts away from the graph (placeFor).
export type Place = { side: 1 | -1; shift: number; far?: boolean };
export function frame(w: number, h: number, p: Place) {
  const S = Math.min(w, h), L = Math.hypot(w, h) / 2, a = Math.atan2(h, w) * 0.85;
  const ex = Math.cos(a), ey = -Math.sin(a), nx = -ey, ny = ex; // e: along (to the upper right), n: across (down right)
  const cx = w / 2 + nx * p.shift * S, cy = h / 2 + ny * p.shift * S;
  return { S, L, ex, ey, nx, ny, cx, cy, ub: -p.side * (p.far ? 0.55 : 0.32) };
}
// Where the band is bright at a point, in the galaxy frame: a narrow Gaussian across the plane (sigma ~12% of the short
// side), a brighter bulge at one end, gentle fall-off along it.
// Everything that varies only along the plane, sampled once per render into a 1-D table (u in [-1.2, 1.2] of L).
const AX = 512;
function axis(F: ReturnType<typeof frame>) {
  const t = { sigma: new Float32Array(AX), wob: new Float32Array(AX), bulge: new Float32Array(AX), along: new Float32Array(AX), rc: new Float32Array(AX), rw: new Float32Array(AX), rs: new Float32Array(AX) };
  for (let i = 0; i < AX; i++) {
    const un = (i / (AX - 1)) * 2.4 - 1.2, db = (un - F.ub) * Math.sign(-F.ub); // db: distance from the bulge, growing away from it
    t.sigma[i] = F.S * 0.12 * (0.8 + 0.5 * fbm(un * 2.2 + 4, 8.1, 2));
    t.wob[i] = (fbm(un * 1.7 + 3, 1.7, 3) - 0.5) * 0.9 * t.sigma[i]; // the plane wanders a little, so it is not a ruler line
    t.bulge[i] = Math.exp(-(((un - F.ub) / 0.2) ** 2));
    t.along[i] = 0.35 + 0.65 * Math.exp(-((db / 0.95) ** 2)); // the disk fades toward the far end
    // the Great Rift: centre (in sigma units, a little off the plane), width and depth along it; continuous, never cut
    t.rc[i] = 0.1 + 0.9 * (fbm(un * 2.6 + 11, 2.2, 3) - 0.5);
    t.rw[i] = 0.42 * (0.6 + 0.8 * fbm(un * 3.5 + 5, 6.6, 2)) * (1 + 0.5 * t.bulge[i]);
    t.rs[i] = 0.85 + 0.15 * smooth(0.3, 0.6, fbm(un * 4 + 1, 9.9, 3));
  }
  return t;
}
const look = (a: Float32Array, un: number) => a[Math.max(0, Math.min(AX - 1, Math.round(((un + 1.2) / 2.4) * (AX - 1))))];
export function bandAt(x: number, y: number, w: number, h: number, p: Place = { side: 1, shift: 0 }, F = frame(w, h, p), T = axis(F)) {
  const dx = x - F.cx, dy = y - F.cy, u = dx * F.ex + dy * F.ey, v = dx * F.nx + dy * F.ny, un = u / F.L;
  const sigma = look(T.sigma, un), vv = (v - look(T.wob, un)) / sigma;
  const core = Math.exp(-0.5 * vv * vv), halo = Math.exp(-0.5 * (vv / 2.6) ** 2);
  return { u, v, un, vv, sigma, bulge: look(T.bulge, un), along: look(T.along, un), rc: look(T.rc, un), rw: look(T.rw, un), rs: look(T.rs, un), core, halo, S: F.S };
}
// Pick the placement from the graph's screen box: the plane moves to the far side of the graph, the bulge to the far end.
export type Rect = { x: number; y: number; w: number; h: number };
export function placeFor(r: Rect | null, w: number, h: number): Place {
  if (!r) return { side: 1, shift: 0 };
  const F = frame(w, h, { side: 1, shift: 0 }), dx = r.x + r.w / 2 - F.cx, dy = r.y + r.h / 2 - F.cy;
  const u = (dx * F.ex + dy * F.ey) / F.L, v = (dx * F.nx + dy * F.ny) / F.S;
  const shift = Math.abs(v) < 0.12 ? 0 : -Math.sign(v) * 0.16;
  // coarse steps, so a small pan never re-renders; a graph over the middle pushes the bulge out to the corner
  return { side: u < -0.08 ? -1 : 1, shift, far: shift === 0 && Math.abs(u) < 0.2 };
}

// --- shared fields ---------------------------------------------------------------------------------------------------
const SCALE = 3; // fields are computed every 3 CSS px and interpolated; the fine texture comes from the haze and the stars

export function fields(w: number, h: number, p: Place) {
  const lw = Math.ceil(w / SCALE) + 1, lh = Math.ceil(h / SCALE) + 1, n = lw * lh;
  const glow = new Float32Array(n), dust = new Float32Array(n), warm = new Float32Array(n), edge = new Float32Array(n), dens = new Float32Array(n);
  const F = frame(w, h, p), T = axis(F);
  for (let j = 0; j < lh; j++) for (let i = 0; i < lw; i++) {
    const b = bandAt(i * SCALE, j * SCALE, w, h, p, F, T), k = j * lw + i;
    edge[k] = Math.min(1, Math.abs(b.vv) / 2.2);
    if (Math.abs(b.vv) > 4.5) { glow[k] = b.along * 0.16 * b.halo; dens[k] = glow[k]; continue; } // far off the plane: halo only
    // anisotropic coordinates: structure is stretched along the plane, as in a photo
    const A = b.u / (b.S * 0.2), B = b.v / (b.S * 0.075);
    const qx = fbm(A * 0.5, B * 0.5, 2), qy = fbm(A * 0.5 + 5.2, B * 0.5 + 1.3, 2);
    const clouds = fbm(A + 1.6 * qx, B + 1.6 * qy, 5); // star clouds
    const rag = fbm(A * 1.3 + 7, B * 1.3 + 2, 4) - 0.5; // ragged rift edges
    const rift = Math.exp(-(((b.vv - b.rc + 0.7 * rag) / b.rw) ** 2)) * b.rs;
    // fine branching dark filaments, densest next to the rift, and patchy dust; both on the band only
    const near = Math.exp(-0.5 * ((b.vv - b.rc) / 1.3) ** 2);
    const mn = fbm(A * 3.2 + 3 * qy, B * 2.6 + 3 * qx, 5);
    const fil = smooth(0.5, 0.8, ridged(A * 1.7 + 2 * qx, B * 1.4 + 2 * qy, 4)) * smooth(0.4, 0.6, mn) * (0.3 + 0.7 * near) * Math.exp(-0.5 * (b.vv / 1.8) ** 2);
    const mott = smooth(0.48, 0.72, mn) * (0.3 + 0.7 * near) * Math.exp(-0.5 * (b.vv / 1.3) ** 2);
    const D = 1 - (1 - 0.95 * rift) * (1 - 0.6 * fil) * (1 - 0.5 * mott);
    const cl = 0.15 + 1.5 * clouds ** 2.5 * 1.6;
    glow[k] = b.along * (0.8 * b.core * cl + 0.16 * b.halo) + 1.4 * b.bulge * Math.exp(-0.5 * (b.vv / 1.4) ** 2) * (0.55 + 0.6 * clouds);
    dust[k] = D;
    warm[k] = Math.min(1, b.bulge * 1.3) * Math.exp(-0.5 * (b.vv / 1.7) ** 2);
    dens[k] = Math.min(1, glow[k] * (1 - 0.85 * D));
  }
  const at = (a: Float32Array, x: number, y: number) => { // bilinear lookup in CSS px
    const fx = Math.min(lw - 1.001, Math.max(0, x / SCALE)), fy = Math.min(lh - 1.001, Math.max(0, y / SCALE)), i = fx | 0, j = fy | 0, u = fx - i, v = fy - j, k = j * lw + i;
    return a[k] * (1 - u) * (1 - v) + a[k + 1] * u * (1 - v) + a[k + lw] * (1 - u) * v + a[k + lw + 1] * u * v;
  };
  return { lw, lh, glow, dust, warm, edge, dens, at };
}
export type Fields = ReturnType<typeof fields>;

// --- pure layer renderers: straight-alpha RGBA ----------------------------------------------------------------------

// The band at CSS px: near-black navy outside it, the glow (salmon core, dusty rose, lavender-blue edges) cut by the dust,
// and the unresolved-star haze, fine grain weighted by the density (not a blur), which is what makes it read milky.
export function bandPixels(w: number, h: number, f: Fields, ink: Ink) {
  const out = new Uint8ClampedArray(w * h * 4), { lw } = f;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    // bilinear lookup of the four fields, inlined (this loop runs once per CSS px)
    const fx = x / SCALE, fy = y / SCALE, i = fx | 0, j = fy | 0, s = fx - i, q = fy - j, k = j * lw + i;
    const w00 = (1 - s) * (1 - q), w10 = s * (1 - q), w01 = (1 - s) * q, w11 = s * q;
    const k1 = k + 1, k2 = k + lw, k3 = k2 + 1, du = f.dust, gw = f.glow, wm = f.warm, eg = f.edge;
    const o = (y * w + x) * 4, D = du[k] * w00 + du[k1] * w10 + du[k2] * w01 + du[k3] * w11, gl = gw[k] * w00 + gw[k1] * w10 + gw[k2] * w01 + gw[k3] * w11;
    const wa = wm[k] * w00 + wm[k1] * w10 + wm[k2] * w01 + wm[k3] * w11, ed = eg[k] * w00 + eg[k1] * w10 + eg[k2] * w01 + eg[k3] * w11;
    const g = gl * (1 - 0.9 * D);
    let col = mix(ink.rose, ink.arm, smooth(0.2, 0.9, ed));
    col = mix(col, ink.core, wa);
    col = mix(col, mix(ink.rose, ink.core, 0.4), smooth(0.2, 0.55, D) * (1 - smooth(0.6, 0.95, D)) * 0.6); // dust reddens light at its edges (Gaia)
    const r = hash(x, y + 9999), hz = r * r * r * Math.min(1, gl * 1.2) * (1 - 0.8 * D) * ink.haze; // haze grain
    const la = Math.min(1, g * ink.band + hz);
    const da = 1 - (1 - ink.outside * ed) * (1 - ink.lane * D * Math.min(1, gl * 2)); // the dark: navy outside, dust lanes inside
    const a = la + da * (1 - la);
    if (a <= 0) continue;
    const t = la / a, hzT = la > 0 ? hz / la : 0;
    for (let c = 0; c < 3; c++) out[o + c] = ink.deep[c] + ((col[c] + (ink.star[c] - col[c]) * hzT) - ink.deep[c]) * t;
    out[o + 3] = a * 255;
  }
  return out;
}

// Star dust at device px: tens of thousands of tiny stars sampled from the band density by rejection, a power-law
// magnitude spread, warm stars in the bulge and cooler ones outside, dimmed behind the dust.
export function starPixels(w: number, h: number, dpr: number, f: Fields, ink: Ink) {
  const W = Math.round(w * dpr), H = Math.round(h * dpr), out = new Uint8ClampedArray(W * H * 4), r = rand(SEED);
  const put = (X: number, Y: number, c: RGB, a: number) => {
    if (X < 0 || Y < 0 || X >= W || Y >= H || a <= 0) return;
    const o = (Y * W + X) * 4, prev = out[o + 3] / 255;
    if (a <= prev) return;
    out[o] = c[0]; out[o + 1] = c[1]; out[o + 2] = c[2]; out[o + 3] = a * 255;
  };
  const n = Math.round((w * h) / 3.5);
  for (let i = 0; i < n; i++) {
    const x = r() * w, y = r() * h, d = f.at(f.dens, x, y), D = f.at(f.dust, x, y);
    if (r() > 0.012 + 0.988 * Math.min(1, (d * 1.6) ** 1.6)) continue; // rejection sampling from the band density
    const m = r() ** 5, k = r(), wa = f.at(f.warm, x, y), inBand = Math.min(1, d * 2); // brightness ~ u^5: most are faint
    const tone = k < 0.1 + 0.55 * wa ? mix(ink.star, ink.core, 0.55) : k > 0.7 - 0.3 * (1 - inBand) ? mix(ink.star, ink.arm, 0.65) : ink.star;
    // the band's own stars are many and faint (its texture); the field stars are few and a little brighter
    const a = Math.min(1, ink.dust * (0.14 + 0.86 * m) * (1 - 0.75 * D) * (1.15 - 0.35 * inBand));
    const X = Math.floor(x * dpr), Y = Math.floor(y * dpr);
    put(X, Y, tone, a);
    if (m > 0.3) { const s = a * 0.45; put(X + 1, Y, tone, s); put(X, Y + 1, tone, s); put(X - 1, Y, tone, s); put(X, Y - 1, tone, s); }
  }
  return { W, H, data: out };
}

// Bright stars: a dozen with a soft halo and no diffraction spikes, spread over the screen.
export function anchorPixels(w: number, h: number, dpr: number, ink: Ink) {
  const W = Math.round(w * dpr), H = Math.round(h * dpr), out = new Uint8ClampedArray(W * H * 4), r = rand(SEED + 2);
  for (let i = 0; i < 12; i++) {
    const x = r() * W, y = r() * H, tone = [ink.star, ink.arm, ink.core][i % 3], a = ink.anchor * (0.55 + r() * 0.45), R = (5 + r() * 5) * dpr;
    for (let Y = Math.max(0, Math.floor(y - R)); Y < Math.min(H, y + R); Y++) for (let X = Math.max(0, Math.floor(x - R)); X < Math.min(W, x + R); X++) {
      const q = Math.hypot(X + 0.5 - x, Y + 0.5 - y) / dpr, v = Math.min(1, a * (q < 0.9 ? 1 : 0.32 * Math.exp(-q * q / 6))), o = (Y * W + X) * 4;
      if (v * 255 > out[o + 3]) { out[o] = tone[0]; out[o + 1] = tone[1]; out[o + 2] = tone[2]; out[o + 3] = v * 255; }
    }
  }
  return { W, H, data: out };
}

// --- layers in the page ---------------------------------------------------------------------------------------------

function inks(): Ink {
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
function toCanvas(W: number, H: number, data: Uint8ClampedArray) {
  const c = document.createElement("canvas");
  c.width = W; c.height = H;
  c.getContext("2d")!.putImageData(new ImageData(data as Uint8ClampedArray<ArrayBuffer>, W, H), 0, 0);
  return c;
}
// Grain: a 128px tile of random specks in device px, repeated; it breaks the banding of the navy gradient.
function renderGrain(w: number, h: number, dpr: number, ink: Ink) {
  const c = document.createElement("canvas"), g = c.getContext("2d")!, T = 128, tile = new ImageData(T, T), r = rand(SEED + 1);
  c.width = Math.round(w * dpr); c.height = Math.round(h * dpr);
  for (let i = 0; i < T * T; i++) { tile.data.set(ink.star, i * 4); tile.data[i * 4 + 3] = r() * ink.grain * 255; }
  const tc = document.createElement("canvas"); tc.width = tc.height = T; tc.getContext("2d")!.putImageData(tile, 0, 0);
  g.fillStyle = g.createPattern(tc, "repeat")!; g.fillRect(0, 0, c.width, c.height);
  return c;
}

const els = {} as Record<ImageLayer, HTMLDivElement>;
const urls: Partial<Record<ImageLayer, string>> = {};
let root: HTMLDivElement | null = null, size = "", timer = 0, place: Place = { side: 1, shift: 0 }, graph: Rect | null = null;
export const sizeKey = (w: number, h: number, p: Place = { side: 1, shift: 0 }) => `${w}x${h}:${p.side}:${p.shift}:${p.far ? 1 : 0}`; // all a render depends on (the seed is fixed)

// opacity only: no render, no layout. Measured as "sky-apply".
export function apply() {
  const t0 = performance.now(), o = layerOpacity(getSky());
  for (const k of IMAGE_LAYERS) els[k].style.opacity = String(o[k]);
  performance.measure("sky-apply", { start: t0 });
}

// The graph's screen box, from the map on every camera move (throttled there). It only moves the CSS mask that dims the
// band behind the graph; when `settled` (the first fit, a resize) it may also move the band to the graph's far side.
export function skyGraph(r: Rect, settled: boolean) {
  graph = r;
  if (root) {
    const s = root.style, pad = 24; // the layers are inset -24px
    s.setProperty("--hole-x", `${r.x + r.w / 2 + pad}px`); s.setProperty("--hole-y", `${r.y + r.h / 2 + pad}px`);
    s.setProperty("--hole-rx", `${r.w * 0.7 + 60}px`); s.setProperty("--hole-ry", `${r.h * 0.7 + 60}px`);
  }
  if (settled) renderAll();
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

// Render every layer for the current size and placement, cheap ones first, the band in idle time; each step is its own
// task so the first frames of the map are never blocked by the whole sky.
function renderAll() {
  const w = innerWidth + 48, h = innerHeight + 48, p = placeFor(graph && { ...graph, x: graph.x + 24, y: graph.y + 24 }, w, h), key = sizeKey(w, h, p);
  if (key === size) return;
  const resized = !size.startsWith(`${w}x${h}:`);
  size = key; place = p;
  const ink = inks(), dpr = Math.min(2, window.devicePixelRatio || 1);
  if (resized) {
    show("grain", renderGrain(w, h, dpr, ink), key);
    const an = anchorPixels(w, h, dpr, ink);
    show("anchors", toCanvas(an.W, an.H, an.data), key);
  }
  idle(() => {
    if (key !== size) return;
    const t0 = performance.now(), f = fields(w, h, place), st = starPixels(w, h, dpr, f, ink);
    show("dust", toCanvas(st.W, st.H, st.data), key);
    performance.measure("sky-render-stars", { start: t0 });
    idle(() => {
      if (key !== size) return;
      const t1 = performance.now();
      show("band", toCanvas(w, h, bandPixels(w, h, f, ink)), key);
      performance.measure("sky-render-band", { start: t1 });
    });
  });
}

export function startSky() {
  root = document.createElement("div");
  root.className = "sky-layers";
  root.setAttribute("aria-hidden", "true");
  for (const k of ["band", "dust", "anchors", "grain"] as ImageLayer[]) { // paint order: band at the back
    const el = document.createElement("div");
    el.className = "sky-layer";
    el.dataset.layer = k;
    root.append((els[k] = el));
  }
  document.body.prepend(root);
  apply();
  onSky(apply);
  renderAll();
  addEventListener("resize", () => { clearTimeout(timer); timer = window.setTimeout(renderAll, 250); });
}
