// Canvas painting for the star atlas. force-graph calls pre -> links -> nodes -> post every frame;
// all fades and focus live on the model objects (mutated in place), so React never re-renders per frame.
import { chooseSpot, type Box } from "./names";
import type { Cluster, GLink, GNode, Model } from "./model";

// Feel knobs, tuned by eye: change these, not the code below.
export const FEEL = {
  fadeMs: 110, // time constant of hover/focus fades
  glideMs: 750, // camera glide to a selected Item
  introMs: 900, // stars light up outward from the centre
  glow: 4.2, // glow sprite radius as a multiple of node radius
  hoverScale: 1.3,
  labelMs: 140, // cluster names ease to a new spot over about this long
};

export type Focus = { hover: GNode | null; preview: GNode | null; selected: GNode | null; matches: Set<GNode> | null; keyFocus: boolean };

function readInk() {
  const css = getComputedStyle(document.documentElement);
  const t = (name: string) => css.getPropertyValue(name).trim();
  const color = (kind: string) => t(`--k-${kind}`) || t("--k-other");
  return {
    color,
    fade: Number(t("--fade")) || 0.1,
    edge: t("--edge"), edgeAlt: t("--edge-alt"), halo: t("--halo"), haloName: t("--halo-name"), dust: t("--dust"),
    ring: t("--ring"), text: t("--text"), text2: t("--text-2"), night: t("--night"), serif: t("--font-serif-stack"), sans: t("--font-sans-stack"),
  };
}

const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
// Drawn radius in graph units: grows with zoom until k = 2.5, then sublinearly, so zooming in reads labels, not giant discs.
const radius = (n: GNode, k: number) => n.r * n.s * Math.min(1, Math.sqrt(2.5 / k));

export function makePainter(model: Model, reducedMotion: boolean) {
  const ink = readInk();
  const colorOf = new Map(model.nodes.map((n) => [n, ink.color(n.kind)]));
  const sprites = new Map<string, HTMLCanvasElement>();
  const focus: Focus = { hover: null, preview: null, selected: null, matches: null, keyFocus: false };
  // fitK: zoom at which the whole map fits (label levels are relative to it); top/bottom/right: px that the top bar,
  // legend and inspector cover, so canvas text keeps out from under them (measured by StarMap)
  const view = { fitK: 1, top: 76, bottom: 0, right: 0 };
  const dust = Array.from({ length: 260 }, () => ({ x: Math.random(), y: Math.random(), r: Math.random() * 0.9 + 0.3, a: Math.random() * 0.5 + 0.1 }));
  let last = 0, lit: Set<GNode> | null = null, f: GNode | null = null, fk = 1;
  // Every fade eases toward a target and snaps when close. `busy` says whether anything is still moving, so the
  // canvas can stop repainting once the map is at rest (StarMap wakes it again on any interaction).
  let moving = false, busy = true;
  const ease = (a: number, b: number, k: number) => {
    if (Math.abs(b - a) < 0.002) return b;
    moving = true;
    return a + (b - a) * k;
  };

  // stars light up outward from the centre, once
  const start = performance.now();
  let introEnd = start + FEEL.introMs * 1.4 + 400;
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
    moving = false;
    const dt = Math.min(64, now - (last || now));
    last = now;
    const k = (fk = reducedMotion ? 1 : 1 - Math.exp(-dt / FEEL.fadeMs));
    f = focus.preview ?? focus.hover ?? focus.selected;
    const m = focus.matches;
    // Search: every match stays lit while typing; the active result is only emphasised. Anything else under the
    // pointer or selected lights its own neighbourhood on top of the matches.
    const pure = !!(m && f && f === focus.preview && m.has(f));
    if (f && !pure) {
      lit = new Set([f, ...model.neighbours.get(f)!]);
      if (m) for (const x of m) lit.add(x);
    } else lit = m;
    for (const n of model.nodes) {
      n.a = ease(n.a, now < n.born ? 0 : !lit || lit.has(n) ? 1 : ink.fade, k);
      n.s = ease(n.s, n === f ? FEEL.hoverScale : 1, k);
    }
    for (const l of model.links) {
      const inc = !!f && (l.source === f || l.target === f);
      const on = f && !pure ? inc || (!!m && m.has(l.source) && m.has(l.target)) : !lit || (lit.has(l.source) && lit.has(l.target));
      l.hot = inc && on;
      l.a = ease(l.a, Math.min(l.source.a, l.target.a) > 0.05 ? (on ? 1 : ink.fade * 0.5) : 0, k);
    }
    for (const c of model.clusters) {
      let top = 0; // the circle itself is fixed (layout.ts); only its brightness follows its Items
      for (const n of c.members) top = Math.max(top, n.a);
      const on = f && !pure && !m ? f.cluster === c : !lit || c.members.some((n) => lit!.has(n));
      c.a = ease(c.a, top > 0.05 ? (on ? 1 : 0.22) : 0, k);
    }
  }

  function pre(ctx: CanvasRenderingContext2D) {
    update(performance.now());
    const sc = screen(ctx);
    const k = sc.k;
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
      const R = radius(n, k) * FEEL.glow;
      ctx.globalAlpha = n.a * (n === f ? 1 : 0.85);
      ctx.drawImage(sprite(colorOf.get(n)!), n.x! - R, n.y! - R, 2 * R, 2 * R);
    }
    ctx.globalCompositeOperation = "source-over";
    ctx.globalAlpha = 1;
  }

  function link(l: GLink, ctx: CanvasRenderingContext2D, k: number) {
    if (l.a < 0.01) return;
    const s = l.source, t = l.target, px = 1 / k;
    ctx.globalAlpha = l.a * (!l.hot && s.cluster !== t.cluster ? 0.45 : 1); // long links between clusters stay in the background
    if (l.hot) {
      const g = ctx.createLinearGradient(s.x!, s.y!, t.x!, t.y!);
      g.addColorStop(0, colorOf.get(s)!); g.addColorStop(1, colorOf.get(t)!);
      ctx.strokeStyle = g;
      ctx.lineWidth = 1.3 * px;
    } else {
      ctx.strokeStyle = l.kind === "contains" ? ink.edge : ink.edgeAlt;
      ctx.lineWidth = px;
    }
    ctx.setLineDash(l.kind === "contains" ? [] : l.kind === "triggers" ? [4 * px, 3 * px] : [1 * px, 3 * px]); // solid, dashed, dotted
    ctx.beginPath(); ctx.moveTo(s.x!, s.y!); ctx.lineTo(t.x!, t.y!); ctx.stroke();
    ctx.setLineDash([]);
    ctx.globalAlpha = 1;
  }

  function node(n: GNode, ctx: CanvasRenderingContext2D, k: number) {
    if (n.a < 0.01) return;
    const r = radius(n, k), px = 1 / k, x = n.x!, y = n.y!, c = colorOf.get(n)!;
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
    if (focus.matches?.has(n) && n !== focus.selected) { // a search match carries a ring, so it never relies on brightness alone
      ctx.strokeStyle = c;
      ctx.lineWidth = 1.2 * px;
      ctx.globalAlpha = n.a * 0.6;
      ctx.beginPath(); ctx.arc(x, y, r + 4.5 * px, 0, 2 * Math.PI); ctx.stroke();
    }
    if (n === focus.selected && focus.keyFocus) { // keyboard focus: a bright ring on the active star, not on the whole viewport
      ctx.strokeStyle = ink.ring;
      ctx.lineWidth = 2 * px;
      ctx.globalAlpha = 1;
      ctx.beginPath(); ctx.arc(x, y, r + 16 * px, 0, 2 * Math.PI); ctx.stroke();
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
    ctx.beginPath(); ctx.arc(n.x!, n.y!, radius(n, k) * 1.2 + slack, 0, 2 * Math.PI); ctx.fill();
  }

  // Semantic zoom: zoomed out you read cluster names like an atlas; zoomed in they give way to Item names.
  // Labels go down greedily by priority and are skipped when they would collide. A cluster name tries several
  // spots around its halo and takes the first that clears every star, every placed label and the chrome; when
  // none is free it fades out instead of sitting on a star.
  const widths = new Map<Cluster, { size: number; w: number; scale: number }>();
  // Canvas-only fonts are never fetched by the DOM: request them, then drop widths measured in the fallback face and repaint.
  void Promise.all([document.fonts.load("italic 400 13px Newsreader"), document.fonts.load("600 13px 'Inter Variable'")])
    .then(() => document.fonts.ready)
    .then(() => { widths.clear(); introEnd = performance.now() + 400; });

  function post(ctx: CanvasRenderingContext2D) {
    const sc = screen(ctx), z = sc.k / view.fitK;
    const W = ctx.canvas.clientWidth, H = ctx.canvas.clientHeight, phone = W <= 640;
    ctx.save();
    ctx.setTransform(sc.dpr, 0, 0, sc.dpr, 0, 0);
    const placed: Box[] = [[0, 0, W, view.top]];
    if (view.bottom > 0) placed.push([0, H - view.bottom, W, H]);
    if (view.right > 0) placed.push([W - view.right, 0, W, H]);
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
      const start = 1.3 - Math.min(0.9, Math.max(0, n.degree - 1) * 0.15); // hubs are named at the fitted view, leaves from 1.3x
      let a = clamp01((z - start) / 0.35) * n.a;
      if (lit?.has(n) && n.a > 0.5) a = Math.max(a, n === f ? 1 : 0.85);
      if (a > 0.03) named.push([n === f ? 0 : lit?.has(n) ? 1 : 2, n, a]);
    }
    named.sort((p, q) => p[0] - q[0] || q[1].degree - p[1].degree);

    const itemLabel = ([rank, n, a]: [number, GNode, number]) => {
      const size = rank === 0 ? 13 : 12;
      ctx.font = `${rank === 0 ? 600 : 450} ${size}px ${ink.sans}`;
      ctx.textBaseline = "top";
      const [sx, sy0] = sc.apply(n.x!, n.y!);
      const sy = sy0 + radius(n, sc.k) * sc.k + 5, w = ctx.measureText(n.name).width;
      if (!fits(sx - w / 2 - 2, sy, sx + w / 2 + 2, sy + size + 2)) return;
      ctx.globalAlpha = a;
      ctx.lineWidth = 3;
      ctx.strokeText(n.name, sx, sy);
      ctx.fillStyle = rank < 2 ? ink.text : ink.text2;
      ctx.fillText(n.name, sx, sy);
    };

    // stars and the names of hubs are what a cluster name must keep clear of
    const obstacles: Box[] = [];
    for (const n of model.nodes) {
      if (n.a < 0.15) continue;
      const [sx, sy] = sc.apply(n.x!, n.y!), R = radius(n, sc.k) * sc.k + 4;
      obstacles.push([sx - R, sy - R, sx + R, sy + R]);
      if (n.degree >= 4) obstacles.push([sx - 30, sy + R, sx + 30, sy + R + 16]);
    }

    const clusterLabel = (c: Cluster, zoomAlpha: number) => {
      const size = (phone ? 12 : 13) + 4 * clamp01((c.members.length - 3) / 20);
      ctx.font = `italic 400 ${size}px ${ink.serif}`;
      ctx.letterSpacing = "0.03em";
      ctx.textBaseline = "middle";
      let m = widths.get(c);
      if (!m || m.size !== size) widths.set(c, (m = { size, w: ctx.measureText(c.name).width, scale: 1 }));
      const w = m.w, h = size * 1.15;
      const [cx, cy] = sc.apply(c.x, c.y), focused = f?.cluster === c;
      // at the fitted view only clusters of 5 or more try for a name; smaller ones come in as you zoom, or when looked at
      const tries = c.members.length >= 5 || z >= 1.15 || focused;
      const spot = tries && zoomAlpha > 0.03 && c.a > 0.03
        ? chooseSpot({ cx, cy, r: c.r * sc.k, w, h, pick: c.pick, allowed: focused ? 2 : 0, W, H, top: view.top, bottom: view.bottom, right: view.right, placed, obstacles })
        : null;
      if (spot) {
        m.scale = spot.scale;
        placed.push(spot.box);
        c.pick = spot.i;
        const gx = (spot.x - sc.tx) / sc.k, gy = (spot.y - sc.ty) / sc.k, appearing = c.la < 0.05;
        c.lx = appearing ? gx : ease(c.lx, gx, fk);
        c.ly = appearing ? gy : ease(c.ly, gy, fk);
        c.la = ease(c.la, spot.crowded ? 0.7 : 1, fk);
      } else c.la = ease(c.la, 0, fk);
      if (c.la > 0.02 && zoomAlpha > 0.03) {
        ctx.font = `italic 400 ${size * m.scale}px ${ink.serif}`;
        const [sx, sy] = sc.apply(c.lx, c.ly);
        ctx.globalAlpha = zoomAlpha * c.la * c.a * 0.9;
        ctx.lineWidth = 4;
        ctx.strokeText(c.name, sx, sy);
        ctx.fillStyle = ink.haloName;
        ctx.fillText(c.name, sx, sy);
      }
      ctx.letterSpacing = "0px";
    };

    named.filter((x) => x[0] < 2).forEach(itemLabel); // the focused neighbourhood always wins its space
    const zoomAlpha = clamp01((1.8 - z) / 0.6);
    [...model.clusters].sort((a, b) => b.members.length - a.members.length).forEach((c) => clusterLabel(c, zoomAlpha));
    named.filter((x) => x[0] === 2).forEach(itemLabel);
    ctx.restore();
    busy = moving || performance.now() < introEnd;
  }

  return { focus, view, pre, link, node, pointer, post, busy: () => busy };
}
export type Painter = ReturnType<typeof makePainter>;
