// Deep field behind the map (sky candidates b and c, docs/design/sky-pattern.md): a two-tone nebula band with a dark
// lane, specks whose density follows the band, and a few anchor stars. Rendered once per viewport size into a blob
// image that CSS shows on body::before, so panning, zooming and dragging never repaint it.

const rand = (seed: number) => () => { // mulberry32: the same sky on every load
  seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};

function render(w: number, h: number) {
  const css = getComputedStyle(document.documentElement);
  const t = (n: string) => css.getPropertyValue(n).trim();
  const num = (n: string, d: number) => Number(t(n)) || d;
  const nebula = num("--sky-nebula", 0.09), star = num("--sky-star", 0.34), anchor = num("--sky-anchor", 0.45);
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  const c = document.createElement("canvas");
  c.width = Math.round(w * dpr); c.height = Math.round(h * dpr);
  const g = c.getContext("2d")!;
  g.scale(dpr, dpr);
  const r = rand(60);
  const probe = document.createElement("canvas").getContext("2d")!;
  const rgba = (color: string, a: number) => {
    probe.fillStyle = color;
    const x = probe.fillStyle; // normalised #rrggbb
    return `rgba(${parseInt(x.slice(1, 3), 16)},${parseInt(x.slice(3, 5), 16)},${parseInt(x.slice(5, 7), 16)},${a})`;
  };
  const blob = (x: number, y: number, rad: number, color: string, a: number) => {
    const gr = g.createRadialGradient(x, y, 0, x, y, rad);
    gr.addColorStop(0, rgba(color, a)); gr.addColorStop(0.5, rgba(color, a * 0.45)); gr.addColorStop(1, rgba(color, 0));
    g.fillStyle = gr;
    g.fillRect(x - rad, y - rad, rad * 2, rad * 2);
  };
  // the band runs lower left to upper right, through the #60 nebula lobes; it bends a little so it is not a ruler line
  const band = (u: number) => ({ x: u * w, y: h * (0.86 - 0.74 * u) + Math.sin(u * Math.PI * 1.6) * h * 0.06 });
  const span = Math.hypot(w, h);
  for (let i = 0; i < 26; i++) { // outer tone: wide indigo clouds
    const p = band(r()), off = (r() - 0.5) * span * 0.12;
    blob(p.x + off * 0.55, p.y + off * 0.8, span * (0.1 + r() * 0.12), t("--indigo"), nebula * (0.45 + r() * 0.55));
  }
  for (let i = 0; i < 18; i++) { // inner tone: a paler, tighter core, so the band has depth instead of one wash
    const p = band(0.15 + r() * 0.7);
    blob(p.x, p.y, span * (0.03 + r() * 0.05), t("--halo-name"), nebula * 0.5 * (0.4 + r() * 0.6));
  }
  for (let i = 0; i < 14; i++) { // a dark lane along the core, as in a real band
    const p = band(0.2 + r() * 0.6);
    blob(p.x + span * 0.012, p.y + span * 0.012, span * (0.02 + r() * 0.03), t("--surface-0"), 0.35);
  }
  // specks: dense in the band, sparse away from it (gaussian across the band)
  const n = Math.round((w * h) / 1900);
  const ink = t("--text");
  for (let i = 0; i < n; i++) {
    let x: number, y: number, a: number;
    if (r() < 0.62) {
      const p = band(r()), d = (r() + r() + r() - 1.5) * span * 0.09;
      x = p.x + d * 0.55; y = p.y + d * 0.8; a = star * (0.25 + r() * 0.75);
    } else { x = r() * w; y = r() * h; a = star * (0.15 + r() * 0.5); }
    g.fillStyle = rgba(ink, a);
    const s = r() < 0.9 ? 0.6 + r() * 0.5 : 1.2;
    g.fillRect(x, y, s, s);
  }
  // anchors: a handful of brighter stars with a small cross glint, kept clear of the centre where the map sits
  for (let i = 0; i < 11; i++) {
    const x = r() * w, y = r() * h;
    if (Math.hypot(x / w - 0.5, y / h - 0.45) < 0.18) continue;
    const a = anchor * (0.6 + r() * 0.4);
    blob(x, y, 7, ink, a * 0.22);
    g.fillStyle = rgba(ink, a * 0.35);
    g.fillRect(x - 4, y - 0.25, 8, 0.5); g.fillRect(x - 0.25, y - 4, 0.5, 8);
    g.fillStyle = rgba(ink, a);
    g.beginPath(); g.arc(x, y, 1.1, 0, Math.PI * 2); g.fill();
  }
  return c;
}

let url = "", timer = 0;
export function startSky() {
  const paint = () => {
    const c = render(innerWidth + 48, innerHeight + 48); // the layer is inset -24px so the drift never shows an edge
    c.toBlob((b) => {
      if (!b) return;
      if (url) URL.revokeObjectURL(url);
      url = URL.createObjectURL(b);
      document.documentElement.style.setProperty("--sky-field", `url(${url})`);
    });
  };
  paint();
  addEventListener("resize", () => { clearTimeout(timer); timer = window.setTimeout(paint, 250); }); // only on a size change
}
