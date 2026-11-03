// Canvas painting for the star atlas. force-graph calls pre -> links -> nodes -> post every frame;
// all fades and focus live on the model objects (mutated in place), so React never re-renders per frame.
import type { Cluster, GLink, GNode, Model } from "./model";

// Feel knobs, tuned by eye: change these, not the code below.
export const FEEL = {
  fadeMs: 110, // time constant of hover/focus fades
  glideMs: 750, // camera glide to a selected Item
  introMs: 900, // stars light up outward from the centre
  glow: 4.2, // glow sprite radius as a multiple of node radius
  hoverScale: 1.3,
};

export type Focus = { hover: GNode | null; preview: GNode | null; selected: GNode | null; matches: Set<GNode> | null };

function readInk() {
  const css = getComputedStyle(document.documentElement);
  const t = (name: string) => css.getPropertyValue(name).trim();
  const color = (kind: string) => t(`--k-${kind}`) || t("--k-other");
  return {
    color,
    fade: Number(t("--fade")) || 0.1,
    edge: t("--edge"), edgeAlt: t("--edge-alt"), halo: t("--halo"), haloName: t("--halo-name"), dust: t("--dust"),
    text: t("--text"), text2: t("--text-2"), night: t("--night"), serif: t("--font-serif-stack"), sans: t("--font-sans-stack"),
  };
}

const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
const ease = (a: number, b: number, k: number) => a + (b - a) * k;

export function makePainter(model: Model, reducedMotion: boolean) {
  const ink = readInk();
  const colorOf = new Map(model.nodes.map((n) => [n, ink.color(n.kind)]));
  const sprites = new Map<string, HTMLCanvasElement>();
  const focus: Focus = { hover: null, preview: null, selected: null, matches: null };
  const dust = Array.from({ length: 260 }, () => ({ x: Math.random(), y: Math.random(), r: Math.random() * 0.9 + 0.3, a: Math.random() * 0.5 + 0.1 }));
  let last = 0, lit: Set<GNode> | null = null, f: GNode | null = null;

  // stars light up outward from the centre, once
  const start = performance.now();
  const far = Math.max(1, ...model.nodes.map((n) => Math.hypot(n.x ?? 0, n.y ?? 0)));
  for (const n of model.nodes) n.born = reducedMotion ? 0 : start + (Math.hypot(n.x ?? 0, n.y ?? 0) / far) * FEEL.introMs * 0.7 + Math.random() * 120;

  function sprite(color: string) {
    let s = sprites.get(color);
    if (s) return s;
    s = document.createElement("canvas");
    s.width = s.height = 128;
    const g = s.getContext("2d")!, grad = g.createRadialGradient(64, 64, 0, 64, 64, 64);
    const probe = document.createElement("canvas").getContext("2d")!;
    probe.fillStyle = color;
    const hex = probe.fillStyle; // normalised #rrggbb
    const rgba = (o: number) => `rgba(${parseInt(hex.slice(1, 3), 16)},${parseInt(hex.slice(3, 5), 16)},${parseInt(hex.slice(5, 7), 16)},${o})`;
    grad.addColorStop(0, rgba(0.5)); grad.addColorStop(0.22, rgba(0.16)); grad.addColorStop(0.55, rgba(0.04)); grad.addColorStop(1, rgba(0));
    g.fillStyle = grad;
    g.fillRect(0, 0, 128, 128);
    sprites.set(color, s);
    return s;
  }

  // screen-space helpers from the transform force-graph has applied to ctx
  const screen = (ctx: CanvasRenderingContext2D) => {
    const m = ctx.getTransform(), dpr = window.devicePixelRatio || 1;
    return { dpr, k: m.a / dpr, tx: m.e / dpr, ty: m.f / dpr, apply: (x: number, y: number) => [(m.a * x + m.e) / dpr, (m.d * y + m.f) / dpr] as const };
  };

  function update(now: number) {
    const dt = Math.min(64, now - (last || now));
    last = now;
    const k = 1 - Math.exp(-dt / FEEL.fadeMs);
    f = focus.preview ?? focus.hover ?? focus.selected;
    lit = f ? new Set([f, ...model.neighbours.get(f)!]) : focus.matches;
    for (const n of model.nodes) {
      n.a = ease(n.a, now < n.born ? 0 : !lit || lit.has(n) ? 1 : ink.fade, k);
      n.s = ease(n.s, n === f ? FEEL.hoverScale : 1, k);
    }
    for (const l of model.links) {
      const on = f ? l.source === f || l.target === f : !lit || (lit.has(l.source) && lit.has(l.target));
      l.hot = !!f && on;
      l.a = ease(l.a, Math.min(l.source.a, l.target.a) > 0.05 ? (on ? 1 : ink.fade * 0.5) : 0, k);
    }
    for (const c of model.clusters) {
      let x = 0, y = 0, d2 = 0, top = 0;
      for (const n of c.members) { x += n.x!; y += n.y!; top = Math.max(top, n.a); }
      c.x = x / c.members.length; c.y = y / c.members.length;
      for (const n of c.members) d2 += (n.x! - c.x) ** 2 + (n.y! - c.y) ** 2;
      c.r = Math.sqrt(d2 / c.members.length) * 1.5 + 18;
      const on = f ? f.cluster === c : !lit || c.members.some((n) => lit!.has(n));
      c.a = ease(c.a, top > 0.05 ? (on ? 1 : 0.22) : 0, k);
    }
  }

  function pre(ctx: CanvasRenderingContext2D) {
    update(performance.now());
    const sc = screen(ctx);
    // Faint dust at a slower parallax than the graph gives panning a sense of depth.
    ctx.save();
    ctx.setTransform(sc.dpr, 0, 0, sc.dpr, 0, 0);
    const w = ctx.canvas.width / sc.dpr, h = ctx.canvas.height / sc.dpr;
    ctx.fillStyle = ink.dust;
    for (const d of dust) {
      ctx.globalAlpha = d.a * 0.5;
      ctx.fillRect((((d.x * w + sc.tx * 0.06) % w) + w) % w, (((d.y * h + sc.ty * 0.06) % h) + h) % h, d.r, d.r);
    }
    ctx.restore();
    // cluster halos: soft nebulae, one neutral hue (27 clusters is far past what colour can encode)
    for (const c of model.clusters) {
      if (c.members.length < 3 || c.a < 0.01) continue;
      const g = ctx.createRadialGradient(c.x, c.y, 0, c.x, c.y, c.r);
      g.addColorStop(0, ink.halo); g.addColorStop(0.6, ink.halo); g.addColorStop(1, "rgba(0,0,0,0)");
      ctx.globalAlpha = c.a;
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(c.x, c.y, c.r, 0, 2 * Math.PI); ctx.fill();
    }
    // glows are additive so dense regions bloom
    ctx.globalCompositeOperation = "lighter";
    for (const n of model.nodes) {
      if (n.a < 0.01) continue;
      const R = n.r * n.s * FEEL.glow;
      ctx.globalAlpha = n.a * (n === f ? 1 : 0.85);
      ctx.drawImage(sprite(colorOf.get(n)!), n.x! - R, n.y! - R, 2 * R, 2 * R);
    }
    ctx.globalCompositeOperation = "source-over";
    ctx.globalAlpha = 1;
  }

  function link(l: GLink, ctx: CanvasRenderingContext2D, k: number) {
    if (l.a < 0.01) return;
    const s = l.source, t = l.target, px = 1 / k;
    ctx.globalAlpha = l.a;
    if (l.hot) {
      const g = ctx.createLinearGradient(s.x!, s.y!, t.x!, t.y!);
      g.addColorStop(0, colorOf.get(s)!); g.addColorStop(1, colorOf.get(t)!);
      ctx.strokeStyle = g;
      ctx.lineWidth = 1.3 * px;
    } else {
      ctx.strokeStyle = l.kind === "contains" ? ink.edge : ink.edgeAlt;
      ctx.lineWidth = px;
    }
    ctx.setLineDash(l.kind === "contains" ? [] : [3 * px, 3 * px]);
    ctx.beginPath(); ctx.moveTo(s.x!, s.y!); ctx.lineTo(t.x!, t.y!); ctx.stroke();
    ctx.setLineDash([]);
    ctx.globalAlpha = 1;
  }

  function node(n: GNode, ctx: CanvasRenderingContext2D, k: number) {
    if (n.a < 0.01) return;
    const r = n.r * n.s, px = 1 / k, x = n.x!, y = n.y!, c = colorOf.get(n)!;
    ctx.globalAlpha = n.a;
    ctx.fillStyle = ctx.strokeStyle = c;
    ctx.beginPath();
    if (n.shape === "ring") {
      ctx.lineWidth = Math.max(1.2 * px, r * 0.22);
      ctx.arc(x, y, r * 0.9, 0, 2 * Math.PI); ctx.stroke();
      ctx.beginPath(); ctx.arc(x, y, r * 0.32, 0, 2 * Math.PI); ctx.fill();
    } else if (n.shape === "diamond") {
      ctx.moveTo(x, y - r * 1.2); ctx.lineTo(x + r * 1.2, y); ctx.lineTo(x, y + r * 1.2); ctx.lineTo(x - r * 1.2, y); ctx.fill();
    } else if (n.shape === "square") {
      ctx.rect(x - r * 0.9, y - r * 0.9, r * 1.8, r * 1.8); ctx.fill();
    } else {
      ctx.arc(x, y, r, 0, 2 * Math.PI); ctx.fill();
      ctx.globalAlpha = n.a * 0.7; // a white-hot core makes a dot read as a star
      ctx.fillStyle = "#fff";
      ctx.beginPath(); ctx.arc(x, y, r * 0.38, 0, 2 * Math.PI); ctx.fill();
    }
    if (n === focus.selected) { // a fine double reticle marks the selection without adding a colour
      ctx.strokeStyle = c;
      ctx.lineWidth = 1.2 * px;
      ctx.globalAlpha = 0.9;
      ctx.beginPath(); ctx.arc(x, y, r + 5 * px, 0, 2 * Math.PI); ctx.stroke();
      ctx.globalAlpha = 0.3;
      ctx.beginPath(); ctx.arc(x, y, r + 10 * px, 0, 2 * Math.PI); ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }

  function pointer(n: GNode, color: string, ctx: CanvasRenderingContext2D, k: number) {
    const slack = (matchMedia("(pointer: coarse)").matches ? 14 : 6) / k;
    ctx.fillStyle = color;
    ctx.beginPath(); ctx.arc(n.x!, n.y!, n.r * n.s * 1.2 + slack, 0, 2 * Math.PI); ctx.fill();
  }

  // Semantic zoom: zoomed out you read cluster names like an atlas; zoomed in they give way to Item names.
  // Labels go down greedily by priority and are skipped when they would collide.
  function post(ctx: CanvasRenderingContext2D) {
    const sc = screen(ctx), z = sc.k;
    ctx.save();
    ctx.setTransform(sc.dpr, 0, 0, sc.dpr, 0, 0);
    const placed: number[][] = [];
    const fits = (x0: number, y0: number, x1: number, y1: number) => {
      if (placed.some((b) => x0 < b[2] && x1 > b[0] && y0 < b[3] && y1 > b[1])) return false;
      placed.push([x0, y0, x1, y1]);
      return true;
    };
    ctx.lineJoin = "round";
    ctx.strokeStyle = ink.night;
    ctx.textAlign = "center";

    const named: [number, GNode, number][] = [];
    for (const n of model.nodes) {
      const start = 1.6 - Math.min(1.1, Math.sqrt(n.degree) * 0.35);
      let a = clamp01((z - start) / 0.6) * n.a;
      if (lit?.has(n) && n.a > 0.5) a = Math.max(a, n === f ? 1 : 0.85);
      if (a > 0.03) named.push([n === f ? 0 : lit?.has(n) ? 1 : 2, n, a]);
    }
    named.sort((p, q) => p[0] - q[0] || q[1].degree - p[1].degree);

    const itemLabel = ([rank, n, a]: [number, GNode, number]) => {
      const size = rank === 0 ? 13 : 12;
      ctx.font = `${rank === 0 ? 600 : 450} ${size}px ${ink.sans}`;
      ctx.textBaseline = "top";
      const [sx, sy0] = sc.apply(n.x!, n.y!);
      const sy = sy0 + n.r * n.s * z + 5, w = ctx.measureText(n.name).width;
      if (!fits(sx - w / 2 - 2, sy, sx + w / 2 + 2, sy + size + 2)) return;
      ctx.globalAlpha = a;
      ctx.lineWidth = 3;
      ctx.strokeText(n.name, sx, sy);
      ctx.fillStyle = rank < 2 ? ink.text : ink.text2;
      ctx.fillText(n.name, sx, sy);
    };
    const clusterLabel = (c: Cluster, alpha: number) => {
      const size = 14 + Math.min(10, Math.sqrt(c.members.length) * 1.6);
      ctx.font = `italic 400 ${size}px ${ink.serif}`;
      ctx.letterSpacing = "0.03em";
      ctx.textBaseline = "middle";
      const [sx, sy] = sc.apply(c.x, c.y - c.r * 0.55), w = ctx.measureText(c.name).width;
      if (fits(sx - w / 2 - 6, sy - size / 2, sx + w / 2 + 6, sy + size / 2)) {
        ctx.globalAlpha = alpha * c.a * 0.9;
        ctx.lineWidth = 4;
        ctx.strokeText(c.name, sx, sy);
        ctx.fillStyle = ink.haloName;
        ctx.fillText(c.name, sx, sy);
      }
      ctx.letterSpacing = "0px";
    };

    named.filter((x) => x[0] < 2).forEach(itemLabel); // the focused neighbourhood always wins its space
    const clusterAlpha = clamp01((1.9 - z) / 0.7);
    if (clusterAlpha > 0.03) {
      model.clusters
        .filter((c) => c.members.length >= 3 && c.a > 0.03)
        .sort((a, b) => b.members.length - a.members.length)
        .forEach((c) => clusterLabel(c, clusterAlpha));
    }
    named.filter((x) => x[0] === 2).forEach(itemLabel);
    ctx.restore();
  }

  return { focus, pre, link, node, pointer, post };
}
export type Painter = ReturnType<typeof makePainter>;
