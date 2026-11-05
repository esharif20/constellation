// Canvas painting for the star atlas. force-graph calls pre -> links -> nodes -> post every frame;
// all fades and focus live on the model objects (mutated in place), so React never re-renders per frame.
import { FOCUS_FILL, haloOf } from "./layout";
import { badgeY } from "./badge";
import { chooseSpot, cutName, labelStart, type Box } from "./names";
import { clusterHealth, rankMembers, type Cluster, type GLink, type GNode, type GOverlap, type Model } from "./model";

// Feel knobs, tuned by eye: change these, not the code below.
export const FEEL = {
  fadeMs: 110, // time constant of hover/focus fades
  introMs: 900, // stars light up outward from the centre
  glow: 4.2, // glow sprite radius as a multiple of node radius
  hoverScale: 1.3,
  labelMs: 140, // cluster names ease to a new spot, and every canvas name eases in or out on its zoom threshold, over about this long
  tipDelay: 120, // ms a pointer dwells on a star before its tooltip shows (docs/design/labels.md 9)
  tipWarm: 300, // while a tooltip was visible this recently, the next star's shows at once
  // cluster focus (docs/design/cluster-focus.md); the flight itself is FLIGHT in layout.ts
  focusDim: 0.12, // stars outside the focused cluster (above --fade, so the map stays legible as context)
  focusHalo: 0.2, // halos outside it
  focusFadeMs: 240, // time constant of the dim, 140 under reduced motion (the dim still eases then)
  focusFadeReducedMs: 140,
  labelStagger: 25, // ms between member names appearing after landing, by cost rank (rank capped at 16)
  focusFill: FOCUS_FILL,
};

// cluster: the focused cluster; flying: the camera is on its way (labels wait); landAt: when it landed (Infinity until then);
// nameHover: the cluster whose name is under the pointer; tip: the star whose tooltip is showing (its canvas name is hidden then)
export type Focus = { hover: GNode | null; preview: GNode | null; selected: GNode | null; matches: Set<GNode> | null; scope: Set<GNode> | null; keyFocus: boolean; cluster: Cluster | null; flying: boolean; landAt: number; nameHover: Cluster | null; tip: GNode | null; removed: Set<GNode> | null; absent: Set<GNode> | null }; // removed: what-if ghosts; absent: not yet scanned at the time-travel date

// Colours added after the first look. Each is read from a CSS variable when the stylesheet defines it, else the fallback.
const PALETTE = { overlap: "#ff5fd2" }; // hot magenta: Overlap links are one family apart from the recessive Relation hairlines

function readInk() {
  const css = getComputedStyle(document.documentElement);
  const t = (name: string) => css.getPropertyValue(name).trim();
  const color = (kind: string) => t(`--k-${kind}`) || t("--k-other");
  return {
    color,
    overlap: t("--overlap") || PALETTE.overlap,
    fade: Number(t("--fade")) || 0.1,
    skyRing: Number(t("--sky-ring")) || 0.05,
    edge: t("--edge"), edgeAlt: t("--edge-alt"), halo: t("--halo"), haloName: t("--halo-name"), dust: t("--dust"),
    ring: t("--ring"), text: t("--text"), text2: t("--text-2"), text3: t("--text-3"), warn: t("--warn"), mono: t("--font-mono-stack"), night: t("--night"), serif: t("--font-serif-stack"), sans: t("--font-sans-stack"),
  };
}

const clamp01 = (v: number) => Math.max(0, Math.min(1, v));
// Drawn radius in graph units: grows with zoom until k = 2.5, then sublinearly, so zooming in reads labels, not giant discs.
export const radius = (n: GNode, k: number) => n.r * n.s * Math.min(1, Math.sqrt(2.5 / k));
// the radius in screen px that a hovered star will have once grown (the tooltip anchors to this)
export const hoverRadius = (n: GNode, k: number) => n.r * FEEL.hoverScale * Math.min(1, Math.sqrt(2.5 / k)) * k;

export function makePainter(model: Model, reducedMotion: boolean) {
  const ink = readInk();
  const colorOf = new Map(model.nodes.map((n) => [n, ink.color(n.kind)]));
  const sprites = new Map<string, HTMLCanvasElement>();
  const focus: Focus = { hover: null, preview: null, selected: null, matches: null, scope: null, keyFocus: false, cluster: null, flying: false, landAt: Infinity, nameHover: null, tip: null, removed: null, absent: null };
  // fitK: zoom at which the whole map fits (label levels are relative to it); top/bottom/right: px that the top bar,
  // legend and inspector cover, so canvas text keeps out from under them (measured by StarMap)
  // tip: the open tooltip's screen box (names keep out of it)
  const view = { fitK: 1, top: 76, bottom: 0, right: 0, left: 0, tip: null as Box | null };
  const dust = Array.from({ length: 260 }, () => ({ x: Math.random(), y: Math.random(), r: Math.random() * 0.9 + 0.3, a: Math.random() * 0.5 + 0.1 }));
  let last = 0, lk = 1, zoomOn = true, zoomA = 1, lit: Set<GNode> | null = null, f: GNode | null = null, fk = 1, fcPrev: Cluster | null = null, fcAt = -1e9;
  const rank = new Map<GNode, number>(); // focus rank of each member of the focused cluster, built once on enter
  const hubFirst = (a: GNode, b: GNode) => (rank.get(a) ?? 1e9) - (rank.get(b) ?? 1e9);
  // Every fade eases toward a target and snaps when close. `busy` says whether anything is still moving, so the
  // canvas can stop repainting once the map is at rest (StarMap wakes it again on any interaction).
  const halos = new Map<Cluster, { x: number; y: number; r: number }>();
  let healthFor: Set<GNode> | null | undefined, health = clusterHealth(model); // recomputed only when what-if's removed set changes
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
  // shortcut: sky candidate switch (?sky=a|b|c|none, docs/design/sky-pattern.md); remove once the owner picks one
  const graticule = document.documentElement.dataset.sky === "a";
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
    const m = focus.matches, fc = focus.cluster;
    if (fc !== fcPrev) { // focus entered, left or hopped: rank the members once and restart the slow fade
      fcPrev = fc; fcAt = now;
      rank.clear();
      if (fc) rankMembers(fc).forEach((n, i) => rank.set(n, i));
    }
    // the dim eases slower than hover, and still eases under reduced motion
    const kf = 1 - Math.exp(-dt / (reducedMotion ? FEEL.focusFadeReducedMs : FEEL.focusFadeMs));
    const slow = !!fc || now - fcAt < 1500;
    // Search: every match stays lit while typing; the active result is only emphasised. Anything else under the
    // pointer or selected lights its own neighbourhood on top of the matches.
    const pure = !!(m && f && f === focus.preview && m.has(f));
    if (f && !pure) {
      lit = new Set([f, ...model.neighbours.get(f)!]);
      for (const o of model.overlapsOf.get(f)!) lit.add(o.a === f ? o.b : o.a); // Overlap partners stay lit and named
      if (m) for (const x of m) lit.add(x);
    } else lit = m;
    for (const n of model.nodes) {
      // in focus a lit neighbour outside the cluster only rises to 0.6, so the cluster stays the subject (search matches stay at 1)
      const base = (fc && n.cluster !== fc) || (focus.scope && !focus.scope.has(n)) ? FEEL.focusDim : 1, up = fc && n.cluster !== fc && !m?.has(n) ? 0.6 : 1;
      n.a = ease(n.a, (now < n.born || focus.absent?.has(n) ? 0 : lit ? (lit.has(n) ? up : ink.fade) : base) * (focus.removed?.has(n) ? 0.35 : 1), lit || !slow ? k : kf);
      n.s = ease(n.s, n === f ? FEEL.hoverScale : 1, k);
    }
    for (const l of model.links) {
      const inc = !!f && (l.source === f || l.target === f);
      const on = f && !pure ? inc || (!!m && m.has(l.source) && m.has(l.target)) : !lit || (lit.has(l.source) && lit.has(l.target));
      l.hot = inc && on;
      const rest = !fc || lit ? 1 : l.source.cluster === fc && l.target.cluster === fc ? 1 : l.source.cluster === fc || l.target.cluster === fc ? 0.35 : 0.06;
      l.a = ease(l.a, Math.min(l.source.a, l.target.a) > 0.05 && !focus.removed?.has(l.source) && !focus.removed?.has(l.target) ? (on ? rest : ink.fade * 0.5) : 0, lit || !slow ? k : kf);
    }
    for (const o of model.overlaps) {
      // at rest only the actionable verdicts show; any focus shows its own Overlaps and hides the rest; a search hides all
      const rest = o.verdict === "overlap" ? 0 : o.a.cluster === o.b.cluster ? 0.55 : 0.28;
      const inside = fc ? (o.a.cluster === fc ? 1 : 0) + (o.b.cluster === fc ? 1 : 0) : 0; // in focus every verdict of the cluster shows, "overlap" included
      const target = f ? (o.a === f || o.b === f ? 1 : 0) : m ? 0 : fc ? [0, 0.15, 0.7][inside] : rest;
      o.alpha = ease(o.alpha, focus.removed?.has(o.a) || focus.removed?.has(o.b) ? 0 : target, f || m || !slow ? k : kf);
    }
    const hk = lk = reducedMotion ? 1 : 1 - Math.exp(-dt / FEEL.labelMs);
    for (const c of model.clusters) {
      // the halo follows its members' live position, eased (exactly the home circle at rest); brightness follows its Items
      const t = haloOf(c), h = halos.get(c);
      if (!h) halos.set(c, t);
      else { h.x = ease(h.x, t.x, hk); h.y = ease(h.y, t.y, hk); h.r = ease(h.r, t.r, hk); }
      let top = 0;
      for (const n of c.members) top = Math.max(top, n.a);
      const on = f && !pure && !m ? f.cluster === c : !lit || c.members.some((n) => lit!.has(n));
      c.a = ease(c.a, top > 0.05 ? (on ? (!lit && fc && c !== fc ? FEEL.focusHalo : 1) : 0.22) : 0, lit || !slow ? k : kf);
    }
  }

  function pre(ctx: CanvasRenderingContext2D) {
    if (import.meta.env.DEV) performance.mark("cx-pre"); // dev only: frame time, pre to post (read by the screenshot harness)
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
    // Sky candidate A: a star-chart graticule anchored to the map (5 rings, 12 meridians, one stroke), gone by 4x the fitted zoom
    const ga = graticule ? ink.skyRing * clamp01((4 - k / view.fitK) / 2.5) : 0;
    if (ga > 0.003) {
      const step = far / 4;
      ctx.save();
      ctx.globalAlpha = ga; ctx.strokeStyle = ink.haloName; ctx.lineWidth = 1 / k;
      ctx.beginPath();
      for (let i = 1; i <= 5; i++) { ctx.moveTo(step * i, 0); ctx.arc(0, 0, step * i, 0, Math.PI * 2); }
      for (let j = 0; j < 12; j++) {
        const c = Math.cos((j * Math.PI) / 6), s = Math.sin((j * Math.PI) / 6);
        ctx.moveTo(c * step, s * step); ctx.lineTo(c * step * 5, s * step * 5); // the inner ring keeps the centre clear
      }
      ctx.stroke();
      ctx.restore();
    }
    // cluster halos: soft nebulae, one neutral hue (27 clusters is far past what colour can encode)
    for (const c of model.clusters) {
      if (c.members.length < 3 || c.a < 0.01) continue;
      const h = halos.get(c)!;
      const g = ctx.createRadialGradient(h.x, h.y, 0, h.x, h.y, h.r);
      g.addColorStop(0, ink.halo); g.addColorStop(0.6, ink.halo); g.addColorStop(1, "rgba(0,0,0,0)");
      ctx.globalAlpha = c.a;
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(h.x, h.y, h.r, 0, 2 * Math.PI); ctx.fill();
    }
    // glows are additive so dense regions bloom
    ctx.globalCompositeOperation = "lighter";
    for (const n of model.nodes) {
      if (n.a < 0.01 || (focus.flying && n.a < 0.15) || focus.removed?.has(n)) continue; // a ghost has no glow
      const R = radius(n, k) * FEEL.glow;
      ctx.globalAlpha = n.a * (n === f ? 1 : 0.85) * (n.unknown ? 0.4 : 1);
      ctx.drawImage(sprite(colorOf.get(n)!), n.x! - R, n.y! - R, 2 * R, 2 * R);
    }
    ctx.globalCompositeOperation = "source-over";
    ctx.globalAlpha = 1;
    for (const o of model.overlaps) overlapArc(o, ctx, k);
  }

  // Overlap links: a quadratic arc bowing 0.2 x length to one side, so it never hides under a straight Relation between the
  // same pair. Verdict is carried by pattern and width (solid, dashed with an arrowhead at the wrapped Item, dotted), not hue.
  function arc(o: GOverlap) {
    const ax = o.a.x!, ay = o.a.y!, bx = o.b.x!, by = o.b.y!, dx = bx - ax, dy = by - ay;
    return { ax, ay, bx, by, cx: (ax + bx) / 2 - dy * 0.2, cy: (ay + by) / 2 + dx * 0.2 };
  }
  function overlapArc(o: GOverlap, ctx: CanvasRenderingContext2D, k: number) {
    const alpha = o.alpha * Math.min(o.a.a, o.b.a);
    if (alpha < 0.01) return;
    const px = 1 / k, { ax, ay, bx, by, cx, cy } = arc(o), hot = o.alpha > 0.95 || (!!f && (o.a === f || o.b === f));
    ctx.globalAlpha = alpha;
    ctx.strokeStyle = ink.overlap;
    ctx.lineCap = o.verdict === "overlap" ? "round" : "butt";
    ctx.lineWidth = ({ duplicate: 2, wrapper: 1.5, overlap: 1.2 }[o.verdict] + (hot ? 0.5 : 0)) * px;
    ctx.setLineDash(o.verdict === "duplicate" ? [] : o.verdict === "wrapper" ? [6 * px, 3 * px] : [0.1 * px, 3.5 * px]);
    ctx.beginPath(); ctx.moveTo(ax, ay); ctx.quadraticCurveTo(cx, cy, bx, by); ctx.stroke();
    ctx.setLineDash([]);
    if (o.verdict === "wrapper") { // open arrowhead just outside the wrapped Item
      const dx = bx - cx, dy = by - cy, len = Math.hypot(dx, dy) || 1, ux = dx / len, uy = dy / len, back = radius(o.b, k) + 2 * px;
      const tx = bx - ux * back, ty = by - uy * back, h = 5 * px, c = Math.cos(0.5), sn = Math.sin(0.5);
      ctx.beginPath();
      ctx.moveTo(tx - (ux * c - uy * sn) * h, ty - (uy * c + ux * sn) * h); ctx.lineTo(tx, ty);
      ctx.lineTo(tx - (ux * c + uy * sn) * h, ty - (uy * c - ux * sn) * h);
      ctx.stroke();
    }
    ctx.lineCap = "butt";
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
    ctx.globalAlpha = n.a * (n.disabled ? 0.4 : 1); // a disabled plugin and its contents: dimmed, with a hollow ring below
    ctx.fillStyle = ctx.strokeStyle = c;
    // Unknown cost is a dashed outline with no fill and no white core (zero is a filled star at the floor size), so the
    // difference survives colour-blindness and greyscale. A plugin ring just turns dashed and keeps its centre dot.
    const unk = n.unknown || !!focus.removed?.has(n), line = unk ? 1.3 * px : 0;
    if (unk) ctx.setLineDash([2 * px, 2 * px]);
    ctx.beginPath();
    if (n.shape === "ring") {
      ctx.lineWidth = Math.max(1.2 * px, r * 0.22);
      ctx.arc(x, y, r * 0.9, 0, 2 * Math.PI); ctx.stroke();
      ctx.setLineDash([]);
      ctx.beginPath(); ctx.arc(x, y, r * 0.32, 0, 2 * Math.PI); ctx.fill();
    } else if (n.shape === "diamond") {
      ctx.moveTo(x, y - r * 1.2); ctx.lineTo(x + r * 1.2, y); ctx.lineTo(x, y + r * 1.2); ctx.lineTo(x - r * 1.2, y);
      if (unk) { ctx.closePath(); ctx.lineWidth = line; ctx.stroke(); } else ctx.fill();
    } else if (n.shape === "square") {
      ctx.rect(x - r * 0.9, y - r * 0.9, r * 1.8, r * 1.8);
      if (unk) { ctx.lineWidth = line; ctx.stroke(); } else ctx.fill();
    } else if (n.shape === "triangle") {
      ctx.moveTo(x, y - r * 1.15); ctx.lineTo(x + r, y + r * 0.85); ctx.lineTo(x - r, y + r * 0.85);
      if (unk) { ctx.closePath(); ctx.lineWidth = line; ctx.stroke(); } else ctx.fill();
    } else if (unk) {
      ctx.arc(x, y, r, 0, 2 * Math.PI); ctx.lineWidth = line; ctx.stroke();
    } else {
      ctx.arc(x, y, r, 0, 2 * Math.PI); ctx.fill();
      ctx.globalAlpha = n.a * 0.7; // a white-hot core makes a dot read as a star
      ctx.fillStyle = "#fff";
      ctx.beginPath(); ctx.arc(x, y, r * 0.38, 0, 2 * Math.PI); ctx.fill();
    }
    ctx.setLineDash([]);
    if (n.disabled) {
      ctx.lineWidth = 1.2 * px;
      ctx.beginPath(); ctx.arc(x, y, r + 3 * px, 0, 2 * Math.PI); ctx.stroke();
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
    if (focus.absent?.has(n)) return; // an unborn star cannot be hovered, dragged or clicked
    const slack = (matchMedia("(pointer: coarse)").matches ? 14 : 6) / k;
    ctx.fillStyle = color;
    ctx.beginPath(); ctx.arc(n.x!, n.y!, radius(n, k) * 1.2 + slack, 0, 2 * Math.PI); ctx.fill();
  }

  // Semantic zoom: zoomed out you read cluster names like an atlas; zoomed in they give way to Item names.
  // Labels go down greedily by priority and are skipped when they would collide. A cluster name tries several
  // spots around its halo and takes the first that clears every star, every placed label and the chrome; when
  // none is free it fades out instead of sitting on a star.
  const widths = new Map<Cluster, { size: number; w: number; scale: number }>();
  const cuts = new Map(model.nodes.map((n) => [n, cutName(n.name)])); // canvas Item names, cut once
  const titles = new Map(model.clusters.map((c) => [c, model.offline ? cutName(c.name, 28) : c.name])); // offline names are a first Item's name and can be long
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
    if (view.left > 0) placed.push([0, 0, view.left, H]);
    if (view.tip) placed.push(view.tip);
    const fits = (x0: number, y0: number, x1: number, y1: number) => {
      if (placed.some((b) => x0 < b[2] && x1 > b[0] && y0 < b[3] && y1 > b[1])) return false;
      placed.push([x0, y0, x1, y1]);
      return true;
    };
    ctx.lineJoin = "round";
    ctx.miterLimit = 2;
    ctx.strokeStyle = ink.night;
    ctx.textAlign = "center";

    const fc = focus.cluster, now = performance.now();
    // Item names (labels.md 1, 3, 6). rank: 0 hovered or previewed, 1 selected, 2 search/chat match, 3 lit neighbour, 4 the rest.
    // `la` eases toward 1 once z passes the Item's start (and back below start - 0.05), so a name is never left half faded.
    const named: [number, GNode, number, number][] = [];
    const sel = focus.selected, cost = (n: GNode) => n.cost?.always_on ?? -1;
    for (const n of model.nodes) {
      const isSel = n === sel;
      if (focus.removed?.has(n) && !isSel) { n.la = 0; continue; } // a ghost has no canvas name
      if ((lit && !lit.has(n) && !isSel) || (fc && n.cluster !== fc && !lit && !isSel) || (n === f && focus.tip === f)) { n.la = 0; continue; } // dimmed names are noise; a hovered star's name is its tooltip
      const start = labelStart(n.degree, n.r, n.unknown, model.heavyR); // hubs at the fitted view, leaves from 1.3x (names.ts)
      const litOn = !!lit?.has(n) && n.a > 0.5;
      let a: number;
      if (fc && n.cluster === fc) { // every member is a candidate whatever the zoom; names stagger in by cost rank once landed
        a = focus.flying ? 0 : (reducedMotion ? 1 : clamp01((now - focus.landAt - FEEL.labelStagger * Math.min(rank.get(n) ?? 0, 16)) / 140)) * n.a;
        if (a < 1 && !focus.flying) moving = true;
        if (litOn) a = 1;
        n.la = a;
      } else {
        const target = litOn || isSel ? 1 : z >= start ? 1 : z < start - 0.05 ? 0 : n.la > 0.5 ? 1 : 0;
        n.la = ease(n.la, target, lk);
        a = litOn || isSel ? n.la : n.la * n.a;
      }
      if (a > 0.03) named.push([n === f ? 0 : isSel ? 1 : focus.matches?.has(n) ? 2 : litOn ? 3 : 4, n, a, start]);
    }
    named.sort((p, q) => p[0] - q[0] || (fc ? hubFirst(p[1], q[1]) : p[0] < 4 ? cost(q[1]) - cost(p[1]) : p[3] - q[3] || q[1].degree - p[1].degree || cost(q[1]) - cost(p[1]) || (p[1].name < q[1].name ? -1 : 1)));
    const costLine = (n: GNode) => (n.unknown ? "unknown" : n.cost!.always_on!.toLocaleString()) + (model.usageWindow && n.usage?.count === 0 ? " · not seen" : "");

    const clearOfStars = (x0: number, y0: number, x1: number, y1: number, self: GNode) => {
      for (const o of model.nodes) {
        if (o === self || o.a < 0.15) continue;
        const R = radius(o, sc.k) * sc.k + 2, ox = o.x! * sc.k + sc.tx, oy = o.y! * sc.k + sc.ty;
        if (x0 < ox + R && x1 > ox - R && y0 < oy + R && y1 > oy - R) return false;
      }
      return true;
    };
    const itemLabel = ([rk, n, a]: [number, GNode, number, number]) => {
      const size = rk < 4 || fc || z >= 1.6 ? 12 : 11;
      ctx.font = `${rk < 2 ? 550 : 450} ${size}px ${ink.sans}`;
      ctx.textBaseline = "top";
      const [sx, sy0] = sc.apply(n.x!, n.y!);
      const sy = sy0 + radius(n, sc.k) * sc.k + 5, text = cuts.get(n)!, w = ctx.measureText(text).width;
      if (rk >= 2 && !clearOfStars(sx - w / 2 - 2, sy, sx + w / 2 + 2, sy + size + 2, n)) return; // a name never sits on another star
      if (!fits(sx - w / 2 - 2, sy, sx + w / 2 + 2, sy + size + 2)) return;
      ctx.globalAlpha = a;
      ctx.lineWidth = 4;
      ctx.strokeText(text, sx, sy);
      ctx.fillStyle = rk < 4 ? ink.text : ink.text2;
      ctx.fillText(text, sx, sy);
      // cost under the name: only in focus, for members, where there is room (a big on-screen cluster or a small one)
      if (fc && n.cluster === fc && (halos.get(fc)!.r * sc.k >= 160 || fc.members.length <= 12)) {
        const line = costLine(n), y2 = sy + size + 2;
        ctx.font = n.unknown ? `italic 400 10px ${ink.sans}` : `400 10px ${ink.mono}`;
        const w2 = ctx.measureText(line).width;
        if (!fits(sx - w2 / 2 - 2, y2, sx + w2 / 2 + 2, y2 + 12)) return;
        ctx.lineWidth = 4;
        ctx.strokeText(line, sx, y2);
        ctx.fillStyle = ink.text3;
        ctx.fillText(line, sx, y2);
      }
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
      if (focus.flying && fc) { c.hit = false; return; }
      const size = (phone ? 12 : 13) + 4 * clamp01((c.members.length - 3) / 20);
      ctx.font = `italic 400 ${size}px ${ink.serif}`;
      ctx.letterSpacing = "0.03em";
      ctx.textBaseline = "middle";
      const title = titles.get(c)!;
      let m = widths.get(c);
      if (!m || m.size !== size) widths.set(c, (m = { size, w: ctx.measureText(title).width, scale: 1 }));
      const w = m.w, lh = size * 1.15;
      const h = halos.get(c)!, [cx, cy] = sc.apply(h.x, h.y), focused = f?.cluster === c;
      // at the fitted view only clusters of 5 or more try for a name; smaller ones come in as you zoom, or when looked at
      const tries = c.members.length >= 5 || z >= 1.15 || focused;
      const mine = fc === c, hidden = (fc && (mine || focus.flying)) || false; // the focused name lives in the card; no names while flying in
      if (fc) zoomAlpha = hidden ? 0 : 0.4; // other names stay as quiet, clickable context, at any zoom
      else if (focused) zoomAlpha = 1; // the hovered or selected Item's cluster keeps its name at any depth
      const spot = !hidden && tries && zoomAlpha > 0.03 && (c.a > 0.03 || !!fc)
        ? chooseSpot({ cx, cy, r: h.r * sc.k, w, h: lh, pick: c.pick, allowed: focused ? 2 : 0, W, H, top: view.top, bottom: view.bottom, right: view.right, placed, obstacles })
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
        const over = focus.nameHover === c;
        ctx.globalAlpha = over ? 1 : zoomAlpha * c.la * (fc ? 1 : c.a) * 0.9;
        ctx.lineWidth = 4;
        ctx.strokeText(title, sx, sy);
        ctx.fillStyle = over ? ink.text : ink.haloName;
        ctx.fillText(title, sx, sy);
        // the hit box: the text padded 6 px (10 on touch), at least 44 px tall; only a name drawn clearly can be clicked
        const pad = coarse ? 10 : 6, hw = w * m.scale / 2 + pad, hh = Math.max(22, size * m.scale / 2 + pad);
        c.box[0] = sx - hw; c.box[1] = sy - hh; c.box[2] = sx + hw; c.box[3] = sy + hh;
        c.hit = over || zoomAlpha * c.la >= 0.25;
      } else c.hit = false;
      ctx.letterSpacing = "0px";
    };

    named.filter((x) => x[0] < 4).forEach(itemLabel); // the lit neighbourhood always wins its space
    if (f) { // verdict text at the apex of each of the focused Item's Overlap arcs, text ink (never the magenta), skipped on collision
      ctx.font = `450 11px ${ink.sans}`;
      ctx.textBaseline = "middle";
      ctx.lineWidth = 4;
      for (const o of model.overlapsOf.get(f)!.slice(0, 8)) {
        if (o.alpha < 0.3) continue;
        const { ax, ay, bx, by, cx, cy } = arc(o), text = o.verdict === "wrapper" ? (o.a === f ? "wraps" : "wrapped by") : o.verdict === "overlap" ? "overlaps" : o.verdict;
        const [sx, sy] = sc.apply(0.25 * ax + 0.5 * cx + 0.25 * bx, 0.25 * ay + 0.5 * cy + 0.25 * by), w = ctx.measureText(text).width;
        if (!fits(sx - w / 2 - 2, sy - 8, sx + w / 2 + 2, sy + 8)) continue;
        ctx.globalAlpha = o.alpha;
        ctx.strokeText(text, sx, sy);
        ctx.fillStyle = ink.text2;
        ctx.fillText(text, sx, sy);
      }
    }
    // cluster names: on below 1.45x, off above 1.55x, eased over time (a half-faded name fails AA, so no scrubbing by zoom)
    zoomOn = z < 1.45 ? true : z > 1.55 ? false : zoomOn;
    const zoomAlpha = (zoomA = ease(zoomA, zoomOn ? 1 : 0, lk)), coarse = matchMedia("(pointer: coarse)").matches;
    [...model.clusters].sort((a, b) => b.members.length - a.members.length).forEach((c) => clusterLabel(c, zoomAlpha));
    named.filter((x) => x[0] === 4).forEach(itemLabel);
    if (!phone && !fc) { // health badge (#71): one line under each drawn cluster name, after every name so it can only be skipped, never move one
      if (healthFor !== focus.removed) { healthFor = focus.removed; health = clusterHealth(model, focus.removed); }
      ctx.font = `450 11px ${ink.sans}`;
      ctx.textAlign = "left";
      ctx.lineWidth = 4;
      for (const c of model.clusters) {
        const m = widths.get(c), h = health.get(c);
        if (!c.hit || !m || !h) continue;
        const [sx, sy] = sc.apply(c.lx, c.ly);
        const cost = h.known == null ? "cost unknown" : `${h.known.toLocaleString()} tok`;
        const rest = [h.useShare == null ? "" : ` · ${h.useShare > 0 && h.useShare < 0.01 ? "<1" : Math.round(h.useShare * 100)}% of uses`, ` · ${h.overlaps === 0 ? "no overlaps" : h.overlaps === 1 ? "1 overlap" : `${h.overlaps} overlaps`}`].join("");
        const w = ctx.measureText(cost + rest).width, x = sx - w / 2;
        const discs = c.members.filter((n) => n.a > 0.05).map((n) => ({ x: n.x! * sc.k + sc.tx, y: n.y! * sc.k + sc.ty, r: radius(n, sc.k) * sc.k }));
        const y = badgeY({ x: sx, y: sy, h: m.size * m.scale }, w, 16, discs);
        if (!fits(x - 2, y - 8, x + w + 2, y + 8)) continue;
        ctx.globalAlpha = (zoomAlpha * c.la * c.a) * 0.9;
        ctx.save(); ctx.globalAlpha *= 0.55; ctx.fillStyle = ink.night; // subtle backing so the text reads over glow and edges
        ctx.beginPath(); ctx.roundRect(x - 6, y - 8, w + 12, 16, 8); ctx.fill(); ctx.restore();
        ctx.strokeText(cost + rest, x, y);
        ctx.fillStyle = h.rank != null && h.rank <= 3 ? ink.warn : ink.text3;
        ctx.fillText(cost, x, y);
        ctx.fillStyle = ink.text3;
        ctx.fillText(rest, x + ctx.measureText(cost).width, y);
      }
      ctx.textAlign = "center";
    }
    ctx.restore();
    busy = moving || focus.flying || now < introEnd;
    if (import.meta.env.DEV) performance.measure("cx-frame", "cx-pre");
  }

  // The cluster whose drawn name is under (x, y) in screen px: what a background click enters or hops to.
  // overlapping boxes: the one whose centre is nearest wins, so a pixel of travel cannot swap the answer
  const clusterAt = (x: number, y: number) => {
    let best: (typeof model.clusters)[number] | null = null, bd = Infinity;
    for (const c of model.clusters) {
      if (!c.hit || x < c.box[0] || x > c.box[2] || y < c.box[1] || y > c.box[3]) continue;
      const d = Math.hypot(x - (c.box[0] + c.box[2]) / 2, y - (c.box[1] + c.box[3]) / 2);
      if (d < bd) { bd = d; best = c; }
    }
    return best;
  };
  // the open tooltip's box and star (a method, so React components do not assign to painter fields)
  const setTip = (box: Box | null, n: GNode | null) => { view.tip = box; focus.tip = n; };
  return { focus, view, setTip, pre, link, node, pointer, post, clusterAt, busy: () => busy };
}
export type Painter = ReturnType<typeof makePainter>;
