import { easeCubicInOut } from "d3-ease";
import type { ForceLink } from "d3-force";
import { forwardRef, memo, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState, type FocusEvent, type KeyboardEvent, type PointerEvent } from "react";
import ForceGraph2D, { type ForceGraphMethods } from "react-force-graph-2d";
import { flightMs, flightPath } from "@/graph/flight";
import { applyForces, fitView, focusView, haloOf, type LLink, type LNode, type View } from "@/graph/layout";
import { step, type Cluster, type GLink, type GNode, type Model } from "@/graph/model";
import { hoverTarget } from "@/graph/hover";
import { FEEL, hoverRadius, makePainter, type Painter } from "@/graph/paint";
import { skyGraph } from "@/graph/sky";
import { onSky } from "@/graph/skySettings";
import { Hover, type Tip } from "@/components/Hover";
import { cn } from "@/lib/utils";

export type StarMapHandle = { glideTo: (n: GNode, other?: GNode) => void; focusCanvas: () => void; holdCamera: () => void }; // holdCamera: the next focus change leaves without its own flight (a glide follows)
type Props = {
  model: Model;
  selected: GNode | null;
  preview: GNode | null; // an Item hovered in the inspector or search list
  matches: Set<GNode> | null;
  removed?: Set<GNode> | null; // what-if ghosts
  absent?: Set<GNode> | null; // time travel: stars not yet scanned fade out in place
  scope: Set<GNode> | null; // the scope filter: stars outside it dim like out-of-cluster ones
  panelWidth: number; // px the inspector covers on the right (0 on phones, where it is a bottom sheet)
  leftPanel: "brief" | "chat" | null;
  cluster: Cluster | null; // the focused cluster: the camera flies to it, the rest of the sky dims
  onSelect: (n: GNode | null) => void;
  onCluster: (c: Cluster | null) => void; // a name was clicked (enter or hop), or the reader left by clicking away or zooming out
};

const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

// How far the top bar, legend and inspector reach into the viewport, read from the DOM (they are not part of the canvas).
function measureInsets(view: Painter["view"]) {
  const W = innerWidth, H = innerHeight;
  const edge = (sel: string) => document.querySelector(sel)?.getBoundingClientRect();
  view.top = Math.max(edge("header")?.bottom ?? 0, edge('div[role="status"].glass')?.bottom ?? 0) + 8; // the highlight chip counts too, when shown
  view.bottom = view.right = view.left = 0;
  const legend = document.querySelector('ul[aria-label="Legend"]');
  if (legend && parseFloat(getComputedStyle(legend).opacity) > 0.5) view.bottom = H - legend.getBoundingClientRect().top + 8;
  const panel = edge("aside");
  if (panel) {
    if (panel.width > W * 0.8) view.bottom = Math.max(view.bottom, H - panel.top + 8); // phone: a bottom sheet
    else view.right = W - panel.left + 8;
  }
  const brief = edge('section[aria-labelledby="brief-title"], section[aria-labelledby="chat-title"]');
  if (brief) {
    if (W <= 640) view.bottom = Math.max(view.bottom, H - brief.top + 8);
    else view.left = brief.right + 8;
  }
  // the cluster card: offset* ignore its enter slide, and a card on its way out no longer counts
  const card = document.querySelector<HTMLElement>('section[aria-labelledby="cluster-title"]');
  if (card && !card.dataset.leaving) {
    if (W <= 640) view.bottom = Math.max(view.bottom, H - card.offsetTop + 8);
    else view.left = card.offsetLeft + card.offsetWidth + 8;
  }
}

function fittedView(painter: Painter, model: Model): View {
  measureInsets(painter.view);
  return fitView(model.nodes, model.clusters, painter.view, innerWidth, innerHeight);
}

export const StarMap = memo(forwardRef<StarMapHandle, Props>(function StarMap({ model, selected, preview, matches, scope, panelWidth, leftPanel, cluster, onSelect, onCluster, removed = null, absent = null }, ref) {
  const fg = useRef<ForceGraphMethods<GNode, GLink> | undefined>(undefined);
  useEffect(() => { if (import.meta.env.VITE_RENDER_COUNT) { const w = window as { __sm?: number }; w.__sm = (w.__sm ?? 0) + 1; } }); // opt-in render counter for npm run motion:perf; compiled out otherwise
  const wrap = useRef<HTMLDivElement>(null);
  const painter = useMemo(() => makePainter(model, reduced()), [model]);
  useEffect(() => { if (import.meta.env.DEV) Object.assign(window, { __cx: { model, painter, zoom: () => fg.current?.zoom(), at: (n: GNode) => fg.current?.graph2ScreenCoords(n.x!, n.y!) } }); }, [model, painter]); // dev only: the screenshot harness reads it
  const [size, setSize] = useState({ w: innerWidth, h: innerHeight });
  const [ready, setReady] = useState(false); // the first fit is done: the camera may fly
  const [data, setData] = useState<{ nodes: GNode[]; links: GLink[] }>({ nodes: [], links: [] });
  const dragging = useRef(false); // a node drag keeps its star lit even when the pointer strays off the canvas
  const nameClick = useRef(false); // pointerup already entered a cluster; the rAF click force-graph fires after it must not act
  const onClusterRef = useRef(onCluster);
  useEffect(() => { onClusterRef.current = onCluster; });
  const zoomK = useRef(1);
  // The graph's screen box goes to the sky (sky.ts skyGraph) once the camera has rested; only a `settled` box (after a
  // fit) is used, to place the band, dim it behind the graph and render it, once per window size. A pan changes no sky.
  const skyT = useRef(0);
  const skyBox = useCallback((settled: boolean) => {
    const g = fg.current, ns = model.nodes;
    if (!g || !ns.length) return;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const n of ns) { if (n.x! < x0) x0 = n.x!; if (n.x! > x1) x1 = n.x!; if (n.y! < y0) y0 = n.y!; if (n.y! > y1) y1 = n.y!; }
    const a = g.graph2ScreenCoords(x0, y0), b = g.graph2ScreenCoords(x1, y1);
    skyGraph({ x: a.x, y: a.y, w: b.x - a.x, h: b.y - a.y }, settled);
  }, [model]);
  const aimRef = useRef<(instant?: boolean) => void>(() => {});
  const focus = painter.focus;

  // The canvas only repaints while something moves. wake() keeps it painting until every fade has settled
  // (painter.busy), poking force-graph's own redraw flag through a same-value zoom.
  const loop = useRef(0);
  // While a button is down, d3-zoom has a gesture open, so a same-value zoom() poke marks it a drag and force-graph drops the click
  const pressed = useRef(false);
  const wake = useCallback(() => {
    if (loop.current) return;
    let quiet = 2;
    const tick = () => {
      const g = fg.current;
      if (!g) return void (loop.current = 0);
      if (pressed.current) return void (loop.current = requestAnimationFrame(tick)); // repaint resumes on release
      g.zoom(g.zoom());
      quiet = painter.busy() ? 2 : quiet - 1;
      loop.current = quiet >= 0 ? requestAnimationFrame(tick) : 0;
    };
    loop.current = requestAnimationFrame(tick);
  }, [painter]);
  useEffect(() => () => { cancelAnimationFrame(loop.current); loop.current = 0; }, []); // zeroed too, or a StrictMode remount would never restart the loop
  // Webfonts arrive after the first paint; the map is at rest by then, so repaint once they land.
  useEffect(() => { void document.fonts.ready.then(wake); }, [wake]);
  useEffect(() => onSky(wake), [wake]); // a Sky setting change (chart rings) repaints the resting map

  // The layout is fully settled by the warm-up, so the engine does not run at load (cooldownTicks 0). A drag lets it run
  // while held and for 150 more ticks after release (the neighbours spring home), then it rests again.
  const [cool, setCool] = useState(0);
  // The warm-up runs on the first frame, after the data lands, so the first rest is when the final layout can be fitted
  // (the stars are still unlit then, so the camera move is never seen).
  const [fitted, setFitted] = useState<View | null>(null);
  const range = fitted ? [fitted.k * 0.6, fitted.k * 10] : [0.05, 40];
  const first = useRef(true);
  const onEngineStop = useCallback(() => {
    if (first.current && fg.current) {
      setFitted(fittedView(painter, model));
    }
    first.current = false;
    setCool(0);
    wake();
  }, [painter, model, wake]);

  // Hover tooltip (docs/design/labels.md 9). Hover lives in refs; React state changes only when the shown Item does.
  // n: the star whose tooltip is up; timer: dwell; warmUntil: a tooltip was up until now + 300 ms, so the next star's shows at once;
  // rest: re-show timer after the camera stops; touch: the last pointer was a finger; at: the last pointer position
  const [tip, setTip] = useState<Tip | null>(null);
  const tipRef = useRef({ want: null as GNode | null, raw: null as GNode | null, n: null as GNode | null, timer: 0, warmUntil: 0, rest: 0, touch: false, x: 0, y: 0, cam: { k: 0, x: 0, y: 0 } });
  const hideTip = useCallback(() => {
    const t = tipRef.current;
    clearTimeout(t.timer);
    t.want = null;
    if (!t.n) return;
    t.n = null;
    t.warmUntil = performance.now() + FEEL.tipWarm;
    if (t.touch) { focus.hover = null; wake(); }
    setTip(null);
  }, [focus, wake]);
  const showTip = useCallback((n: GNode, touch: boolean) => {
    const g = fg.current;
    if (!g || focus.flying || n === focus.selected || n.a < 0.3) return;
    measureInsets(painter.view); // the chip and panels may have moved since the last measure
    const c = g.graph2ScreenCoords(n.x!, n.y!);
    tipRef.current.n = n;
    setTip({ n, x: c.x, y: c.y, r: hoverRadius(n, g.zoom()), touch });
  }, [focus, painter]);
  // dwell 120 ms on a star, or at once when a tooltip was just up; leaving hides at once
  const hoverTip = useCallback((n: GNode | null) => {
    const t = tipRef.current;
    clearTimeout(t.timer);
    if (!n) return hideTip();
    if (t.n === n) return;
    t.timer = window.setTimeout(() => showTip(n, false), performance.now() < t.warmUntil ? FEEL.tipSwitch : FEEL.tipDelay);
  }, [hideTip, showTip]);
  // hover intent: the canvas reports the star under the pointer; hoverTarget decides whether the tooltip follows (hysteresis)
  const settle = useCallback((cand: GNode | null) => {
    const t = tipRef.current, g = fg.current;
    t.raw = cand;
    if (dragging.current || t.touch || !g) return;
    const target = hoverTarget(t.want, cand, t, (n) => { const c = g.graph2ScreenCoords(n.x!, n.y!); return { x: c.x, y: c.y, r: hoverRadius(n, g.zoom()) }; });
    focus.hover = target;
    if (target !== t.want) { t.want = target; hoverTip(target); }
    wake();
  }, [focus, hoverTip, wake]);
  useEffect(() => () => { clearTimeout(tipRef.current.timer); clearTimeout(tipRef.current.rest); }, []);

  useEffect(() => { focus.removed = removed; wake(); }, [focus, removed, wake]);
  useEffect(() => { focus.absent = absent; wake(); }, [focus, absent, wake]);

  useEffect(() => {
    Object.assign(focus, { selected, preview, matches, scope });
    measureInsets(painter.view); // a highlight chip appears with a new match set
    if (tipRef.current.n === selected) hideTip(); // the Inspector shows the selected star
    wake();
  }, [focus, painter, selected, preview, matches, scope, wake, hideTip]);

  // One camera owner. Everything that moves the camera by itself (enter, exit, hop, glide) goes through fly(), a single rAF
  // loop on d3's smooth zoom-and-pan path; force-graph's own zoom(k, ms) and centerAt(x, y, ms) are two uncoupled tweens
  // that would fight. A flight cancelled by the reader counts as landed: the focus state (dims, card) stays.
  const zoomTo = useRef({ kT: 1, sx: 0, sy: 0, raf: 0 });
  const cam = useRef({ raf: 0, kFocus: 0 });
  const land = useCallback(() => {
    cam.current.raf = 0;
    focus.flying = false;
    focus.landAt = performance.now();
    wake();
  }, [focus, wake]);
  const stopCamera = useCallback(() => {
    if (!cam.current.raf) return;
    cancelAnimationFrame(cam.current.raf);
    land();
  }, [land]);
  const fly = useCallback((to: View, instant = false) => {
    const g = fg.current;
    if (!g) return;
    cancelAnimationFrame(cam.current.raf);
    cancelAnimationFrame(zoomTo.current.raf);
    zoomTo.current.raf = 0;
    const c = g.centerAt(), W = innerWidth, path = flightPath({ x: c.x, y: c.y, k: g.zoom() }, to, W);
    const ms = instant || reduced() ? 0 : flightMs(path.duration), t0 = performance.now();
    focus.flying = true;
    focus.landAt = Infinity;
    const tick = (now: number) => {
      const t = ms ? Math.min(1, (now - t0) / ms) : 1, p = path(easeCubicInOut(t));
      g.zoom(W / p[2], 0);
      g.centerAt(p[0], p[1], 0);
      if (t < 1) { cam.current.raf = requestAnimationFrame(tick); wake(); return; }
      zoomTo.current.kT = to.k;
      land();
    };
    cam.current.raf = requestAnimationFrame(tick);
    wake();
  }, [focus, land, wake]);
  useEffect(() => () => cancelAnimationFrame(cam.current.raf), []);
  // Apply the fit after force-graph receives its new zoom bounds; every camera move still uses the single flight owner.
  useEffect(() => {
    if (!fitted) return;
    painter.view.fitK = fitted.k;
    fly(fitted, true);
    requestAnimationFrame(() => requestAnimationFrame(() => skyBox(true))); // after the instant flight has landed
    setReady(true);
  }, [fitted, fly, painter, skyBox]);

  // Focus a cluster (or leave it): dims start now, the card has mounted, so measure the insets a frame later and fly to the
  // framed halo (read once: the target is frozen, the camera does not chase a dragged member) or back to the fitted view.
  const aimed = useRef<Cluster | null | undefined>(undefined);
  const noFlight = useRef(false); // leaving by zooming out: the reader is already pulling back
  const aim = useCallback((instant = false) => {
    const g = fg.current;
    if (!g) return;
    measureInsets(painter.view);
    const W = innerWidth, H = innerHeight, ins = painter.view;
    const to = cluster ? focusView(haloOf(cluster), ins, W, H, ins.fitK) : fitView(model.nodes, model.clusters, ins, W, H);
    cam.current.kFocus = cluster ? to.k : 0;
    fly(to, instant);
  }, [cluster, fly, model, painter]);
  useEffect(() => { aimRef.current = aim; }, [aim]);
  useEffect(() => {
    focus.cluster = cluster;
    wake();
    if (!ready || cluster === aimed.current) return;
    const first = aimed.current === undefined;
    aimed.current = cluster;
    if (noFlight.current) { noFlight.current = false; return; }
    if (first && !cluster) return;
    focus.flying = true;
    focus.landAt = Infinity;
    const id = requestAnimationFrame(() => aim(first));
    return () => cancelAnimationFrame(id);
  }, [focus, cluster, ready, aim, wake]);

  // Wheel and trackpad pinch: an eased, damped zoom towards the cursor instead of d3-zoom's instant steps. The target zoom
  // moves with every wheel event; each frame the real zoom closes 1 - e^(-dt/90ms) of the gap, which is the soft tail.
  // Touch pinch and drag-pan stay with d3-zoom so they track the fingers 1:1.
  useEffect(() => {
    const el = wrap.current!, z = zoomTo.current;
    const tick = (last: number) => (now: number) => {
      const g = fg.current;
      if (!g) return void (z.raf = 0);
      const k = g.zoom(), tau = reduced() ? 0 : 90;
      let k2 = tau ? k + (z.kT - k) * (1 - Math.exp(-Math.min(64, now - last) / tau)) : z.kT;
      if (Math.abs(z.kT - k2) / k2 < 0.002) k2 = z.kT;
      const c = g.centerAt(), f = 1 / k - 1 / k2; // keep the graph point under the cursor still
      g.zoom(k2, 0);
      g.centerAt(c.x + (z.sx - innerWidth / 2) * f, c.y + (z.sy - innerHeight / 2) * f, 0);
      z.raf = k2 === z.kT ? 0 : requestAnimationFrame(tick(now));
    };
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      e.stopPropagation(); // d3-zoom never sees it
      stopCamera();
      const g = fg.current;
      if (!g) return;
      const rate = e.ctrlKey ? 0.01 : 0.0015 * (e.deltaMode === 1 ? 33 : 1);
      const fitK = painter.view.fitK;
      z.kT = Math.min(fitK * 10, Math.max(fitK * 0.6, (z.raf ? z.kT : g.zoom()) * Math.exp(-e.deltaY * rate)));
      z.sx = e.clientX;
      z.sy = e.clientY;
      if (!z.raf) z.raf = requestAnimationFrame(tick(performance.now()));
    };
    const stop = () => { cancelAnimationFrame(z.raf); z.raf = 0; };
    el.addEventListener("wheel", onWheel, { capture: true, passive: false });
    const down = () => { stop(); stopCamera(); };
    // A name click is owned here: force-graph drops any click that moved a pixel and lets a star under the 44 px box win.
    let start: { x: number; y: number; name: Cluster } | null = null;
    const pos = (e: globalThis.PointerEvent) => { const b = el.getBoundingClientRect(); return { x: e.clientX - b.left, y: e.clientY - b.top }; };
    const release = () => { pressed.current = false; };
    const pdown = (e: globalThis.PointerEvent) => {
      pressed.current = true;
      down();
      nameClick.current = false;
      const p = pos(e), name = e.button === 0 ? painter.clusterAt(p.x, p.y) : null;
      start = name ? { ...p, name } : null;
    };
    const pup = (e: globalThis.PointerEvent) => {
      const s = start;
      start = null;
      if (!s) return;
      const p = pos(e), tol = e.pointerType === "touch" || matchMedia("(pointer: coarse)").matches ? 10 : 6;
      if (Math.hypot(p.x - s.x, p.y - s.y) > tol || painter.clusterAt(p.x, p.y) !== s.name) return;
      nameClick.current = true;
      hideTip();
      onClusterRef.current(s.name);
    };
    el.addEventListener("pointerdown", pdown);
    el.addEventListener("pointerup", pup, true);
    addEventListener("pointerup", release, true);
    addEventListener("pointercancel", release, true);
    return () => { el.removeEventListener("wheel", onWheel, { capture: true }); el.removeEventListener("pointerdown", pdown); el.removeEventListener("pointerup", pup, true); removeEventListener("pointerup", release, true); removeEventListener("pointercancel", release, true); stop(); };
  }, [painter, stopCamera, hideTip]);

  // the chrome moves with the selection (the panel slides in), so measure again once it has settled
  useEffect(() => {
    measureInsets(painter.view);
    const id = setTimeout(() => {
      measureInsets(painter.view);
      if (!selected && !focus.cluster && !focus.flying && fg.current && Math.abs(zoomK.current / painter.view.fitK - 1) < 0.05) setFitted(fittedView(painter, model));
      wake();
    }, 460);
    return () => clearTimeout(id);
  }, [selected, leftPanel, focus, painter, model, wake]);

  useEffect(() => {
    const onResize = () => {
      setSize({ w: innerWidth, h: innerHeight });
      // a map still at its fitted view follows the window; one the reader has moved stays put
      requestAnimationFrame(() => {
        if (focus.cluster) { measureInsets(painter.view); aimRef.current(true); }
        else if (fg.current && Math.abs(zoomK.current / painter.view.fitK - 1) < 0.05) setFitted(fittedView(painter, model));
        wake();
      });
    };
    // a tab loaded in the background can be sized before its window is: re-check the size when it is shown
    const onShow = () => { if (!document.hidden) onResize(); };
    addEventListener("resize", onResize);
    document.addEventListener("visibilitychange", onShow);
    return () => { removeEventListener("resize", onResize); document.removeEventListener("visibilitychange", onShow); };
  }, [focus, painter, model, wake]);

  // Forces go in before the data so the warm-up ticks run with them and the first paint is already settled.
  useEffect(() => {
    const g = fg.current!;
    // the same forces the layout settled with (layout.ts), so a dragged Item springs back to its slot
    applyForces(g.d3Force("link") as unknown as ForceLink<LNode, LLink>, (name, f) => g.d3Force(name, f as never));
    g.d3Force("center", null);
    setData({ nodes: model.nodes, links: model.links });
  }, [model]);

  useImperativeHandle(ref, () => ({
    glideTo(n, other) {
      const g = fg.current!;
      measureInsets(painter.view);
      const phone = innerWidth <= 640;
      const left = phone ? 0 : painter.view.left, right = phone ? 0 : panelWidth + 16;
      const top = painter.view.top, bottom = phone ? innerHeight * 0.58 + 8 : painter.view.bottom;
      let k = Math.max(g.zoom(), painter.view.fitK * 1.6); // always closer than the fitted view, so neighbours get names
      if (other) k = Math.min(k, Math.max(80, innerWidth - left - right - 80) / Math.max(1, Math.abs(n.x! - other.x!)), Math.max(80, innerHeight - top - bottom - 64) / Math.max(1, Math.abs(n.y! - other.y!)));
      // keep the Item clear of the inspector: left of the panel on desktop, above the sheet on phones
      const dx = (right - left) / 2 / k, dy = (bottom - top) / 2 / k;
      fly({ x: (n.x! + (other?.x ?? n.x!)) / 2 + dx, y: (n.y! + (other?.y ?? n.y!)) / 2 + dy, k });
    },
    focusCanvas: () => wrap.current?.focus(),
    holdCamera: () => { noFlight.current = true; },
  }), [panelWidth, fly, painter]);

  // Arrow keys step to the nearest Item in that direction; with nothing selected they start nearest the centre.
  function onKeyDown(e: KeyboardEvent) {
    if (e.key !== "Escape") stopCamera();
    hideTip(); // keyboard: no tooltip; the live region carries the cost
    const dir = ({ ArrowRight: [1, 0], ArrowLeft: [-1, 0], ArrowDown: [0, 1], ArrowUp: [0, -1] } as Record<string, number[]>)[e.key];
    if (!dir) return;
    e.preventDefault();
    const pool = cluster ? cluster.members : model.nodes; // in focus the arrows stay among the cluster's members
    if (!selected) {
      const c = cluster ? haloOf(cluster) : fg.current!.centerAt();
      let best = pool[0];
      for (const n of pool) if (Math.hypot(n.x! - c.x, n.y! - c.y) < Math.hypot(best.x! - c.x, best.y! - c.y)) best = n;
      return onSelect(best);
    }
    const next = step(pool, selected, dir[0], dir[1]);
    if (next) onSelect(next);
  }

  // Names of clusters are the other way in: a click on one enters (or hops); a click clear of the focused halo leaves
  const onBackground = (e: MouseEvent) => {
    const g = fg.current, box = wrap.current?.getBoundingClientRect();
    if (!g || !box) return;
    if (nameClick.current) { nameClick.current = false; return; }
    hideTip();
    const x = e.clientX - box.left, y = e.clientY - box.top, named = painter.clusterAt(x, y);
    if (named) return onCluster(named);
    if (cluster && !selected) {
      const h = haloOf(cluster), p = g.graph2ScreenCoords(h.x, h.y);
      if (Math.hypot(x - p.x, y - p.y) > h.r * g.zoom()) return onCluster(null);
    }
    onSelect(null);
  };
  const hoverRaf = useRef(0);
  const onPointerMove = (e: PointerEvent) => {
    tipRef.current.touch = e.pointerType === "touch";
    tipRef.current.x = e.clientX;
    tipRef.current.y = e.clientY;
    if (e.buttons === 0 && (tipRef.current.want || tipRef.current.raw)) settle(tipRef.current.raw);
    if (hoverRaf.current || e.pointerType === "touch") return;
    const x = e.clientX, y = e.clientY;
    hoverRaf.current = requestAnimationFrame(() => {
      hoverRaf.current = 0;
      const c = focus.hover ? null : painter.clusterAt(x, y);
      if (focus.nameHover === c) return;
      focus.nameHover = c;
      if (wrap.current) wrap.current.style.cursor = c ? "pointer" : "";
      wake();
    });
  };

  return (
    <>
    <div
      ref={wrap}
      onPointerMove={onPointerMove}
      onPointerLeave={() => { // the chrome sits above the canvas, so force-graph never hears the pointer go (hoverObj stays on the star)
        if (dragging.current) return;
        focus.hover = null;
        tipRef.current.raw = null;
        focus.nameHover = null;
        if (wrap.current) wrap.current.style.cursor = "";
        hideTip();
        wake();
      }}
      onPointerDown={(e) => { tipRef.current.touch = e.pointerType === "touch"; }}
      tabIndex={0}
      role="application"
      aria-label="Constellation graph. Arrow keys move between Items, slash searches, Escape closes the inspector."
      onKeyDown={onKeyDown}
      onFocus={(e: FocusEvent<HTMLDivElement>) => { focus.keyFocus = e.currentTarget.matches(":focus-visible"); wake(); }}
      onBlur={() => { focus.keyFocus = false; wake(); }}
      // with a star selected the focus ring sits on that star (paint.ts); otherwise it frames the viewport
      className={cn("fixed inset-0 outline-none", !selected && "focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset")}
    >
      <ForceGraph2D<GNode, GLink>
        ref={fg}
        graphData={data}
        width={size.w}
        height={size.h}
        backgroundColor="rgba(0,0,0,0)"
        nodeLabel={() => ""} // names are drawn on the canvas; no browser tooltip
        onEngineStop={onEngineStop}
        warmupTicks={0} // the layout is settled before the first paint (layout.ts)
        cooldownTicks={cool}
        d3AlphaDecay={0.05}
        d3VelocityDecay={0.3}
        minZoom={range[0]}
        maxZoom={range[1]}
        nodeCanvasObjectMode={() => "replace"}
        nodeCanvasObject={painter.node}
        nodePointerAreaPaint={painter.pointer}
        linkCanvasObjectMode={() => "replace"}
        linkCanvasObject={painter.link}
        linkPointerAreaPaint={() => {}} // links are not interactive: one under a cluster name would swallow the click that enters it
        onRenderFramePre={painter.pre}
        onRenderFramePost={painter.post}
        onNodeHover={(n) => {
          if (tipRef.current.touch) { focus.hover = n ?? null; tipRef.current.raw = n ?? null; wake(); return; } // a finger's tooltip comes from its taps (onNodeClick)
          settle(n ?? null);
        }}
        onNodeDrag={(n) => { dragging.current = true; focus.hover = n; hideTip(); setCool(Infinity); }}
        onNodeDragEnd={() => { dragging.current = false; focus.hover = null; setCool(150); wake(); }}
        onNodeClick={(n) => {
          if (nameClick.current) { nameClick.current = false; return; }
          const t = tipRef.current;
          if (t.touch && n !== selected && t.n !== n) { // first tap: light its neighbours and show the tooltip; the second tap opens it
            focus.hover = n;
            wake();
            showTip(n, true);
            return;
          }
          hideTip();
          onSelect(n);
        }}
        onBackgroundClick={onBackground}
        onZoom={(t) => {
          const c = tipRef.current.cam;
          if (Math.abs(t.k - c.k) > 1e-6 || Math.abs(t.x - c.x) > 0.01 || Math.abs(t.y - c.y) > 0.01) { // the camera really moved (wake() re-sets the same zoom)
            c.k = t.k; c.x = t.x; c.y = t.y;
            hideTip();
            clearTimeout(tipRef.current.rest); // 150 ms after it rests, a pointer still on the star gets the tooltip again, placed afresh
            tipRef.current.rest = window.setTimeout(() => {
              const h = focus.hover, g = fg.current, r = tipRef.current;
              if (!h || !g || r.touch || r.n || focus.flying) return;
              const p = g.graph2ScreenCoords(h.x!, h.y!);
              if (Math.hypot(p.x - r.x, p.y - r.y) <= hoverRadius(h, g.zoom()) + 6) showTip(h, false);
            }, 150);
          }
          zoomK.current = t.k;
          clearTimeout(skyT.current); skyT.current = window.setTimeout(() => skyBox(false), 200);
          wake(); // names ease in and out over time now, so a zoom that has stopped may still have a fade to finish
          // pulling back past half the focus zoom leaves focus where the reader already is (no flight)
          if (cluster && !focus.flying && cam.current.kFocus && t.k < 0.5 * cam.current.kFocus) { noFlight.current = true; onCluster(null); }
        }}
      />
    </div>
    {tip && <Hover key={tip.n.id} tip={tip} model={model} painter={painter} wake={wake} />}
    </>
  );
}));
