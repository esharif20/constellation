import type { ForceLink } from "d3-force";
import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState, type FocusEvent, type KeyboardEvent } from "react";
import ForceGraph2D, { type ForceGraphMethods } from "react-force-graph-2d";
import { applyForces, type LLink, type LNode } from "@/graph/layout";
import { step, type GLink, type GNode, type Model } from "@/graph/model";
import { FEEL, makePainter, type Painter } from "@/graph/paint";
import { cn } from "@/lib/utils";

export type StarMapHandle = { glideTo: (n: GNode, other?: GNode) => void; focusCanvas: () => void };
type Props = {
  model: Model;
  selected: GNode | null;
  preview: GNode | null; // an Item hovered in the inspector or search list
  matches: Set<GNode> | null;
  panelWidth: number; // px the inspector covers on the right (0 on phones, where it is a bottom sheet)
  briefOpen: boolean;
  onSelect: (n: GNode | null) => void;
};

const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

// How far the top bar, legend and inspector reach into the viewport, read from the DOM (they are not part of the canvas).
function measureInsets(view: Painter["view"]) {
  const W = innerWidth, H = innerHeight;
  const edge = (sel: string) => document.querySelector(sel)?.getBoundingClientRect();
  view.top = (edge("header")?.bottom ?? 0) + 8;
  view.bottom = view.right = view.left = 0;
  const legend = document.querySelector('ul[aria-label="Legend"]');
  if (legend && parseFloat(getComputedStyle(legend).opacity) > 0.5) view.bottom = H - legend.getBoundingClientRect().top + 8;
  const panel = edge("aside");
  if (panel) {
    if (panel.width > W * 0.8) view.bottom = Math.max(view.bottom, H - panel.top + 8); // phone: a bottom sheet
    else view.right = W - panel.left + 8;
  }
  const brief = edge('section[aria-labelledby="brief-title"]');
  if (brief) {
    if (W <= 640) view.bottom = Math.max(view.bottom, H - brief.top + 8);
    else view.left = brief.right + 8;
  }
}

// Fit every star into the sky left free by the chrome, so a phone gets a tall, full map rather than empty bands.
function fit(g: ForceGraphMethods<GNode, GLink>, painter: Painter, model: Model) {
  measureInsets(painter.view);
  const { top, bottom, right, left } = painter.view, W = innerWidth, H = innerHeight, pad = W <= 640 ? 14 : 36;
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  // the circles' bounds (not just the stars), so halos are not clipped
  for (const n of model.nodes) {
    x0 = Math.min(x0, n.x! - n.r - 8); x1 = Math.max(x1, n.x! + n.r + 8);
    y0 = Math.min(y0, n.y! - n.r - 8); y1 = Math.max(y1, n.y! + n.r + 8);
  }
  for (const c of model.clusters) {
    x0 = Math.min(x0, c.x - c.r); x1 = Math.max(x1, c.x + c.r);
    y0 = Math.min(y0, c.y - c.r); y1 = Math.max(y1, c.y + c.r);
  }
  const L = left + pad, R = W - right - pad, T = top + pad / 2, B = H - bottom - pad / 2;
  const k = Math.min(3, (R - L) / Math.max(1, x1 - x0), (B - T) / Math.max(1, y1 - y0));
  g.zoom(k, 0);
  g.centerAt((x0 + x1) / 2 - ((L + R) / 2 - W / 2) / k, (y0 + y1) / 2 - ((T + B) / 2 - H / 2) / k, 0);
  painter.view.fitK = k;
}

export const StarMap = forwardRef<StarMapHandle, Props>(function StarMap({ model, selected, preview, matches, panelWidth, briefOpen, onSelect }, ref) {
  const fg = useRef<ForceGraphMethods<GNode, GLink> | undefined>(undefined);
  const wrap = useRef<HTMLDivElement>(null);
  const painter = useMemo(() => makePainter(model, reduced()), [model]);
  const [size, setSize] = useState({ w: innerWidth, h: innerHeight });
  const [data, setData] = useState<{ nodes: GNode[]; links: GLink[] }>({ nodes: [], links: [] });
  const zoomK = useRef(1);
  const focus = painter.focus;

  // The canvas only repaints while something moves. wake() keeps it painting until every fade has settled
  // (painter.busy), poking force-graph's own redraw flag through a same-value zoom.
  const loop = useRef(0);
  const wake = useCallback(() => {
    if (loop.current) return;
    let quiet = 2;
    const tick = () => {
      const g = fg.current;
      if (!g) return void (loop.current = 0);
      g.zoom(g.zoom());
      quiet = painter.busy() ? 2 : quiet - 1;
      loop.current = quiet >= 0 ? requestAnimationFrame(tick) : 0;
    };
    loop.current = requestAnimationFrame(tick);
  }, [painter]);
  useEffect(() => () => cancelAnimationFrame(loop.current), []);
  // Webfonts arrive after the first paint; the map is at rest by then, so repaint once they land.
  useEffect(() => { void document.fonts.ready.then(wake); }, [wake]);

  // The layout is fully settled by the warm-up, so the engine does not run at load (cooldownTicks 0). A drag lets it run
  // while held and for 150 more ticks after release (the neighbours spring home), then it rests again.
  const [cool, setCool] = useState(0);
  // The warm-up runs on the first frame, after the data lands, so the first rest is when the final layout can be fitted
  // (the stars are still unlit then, so the camera move is never seen).
  const [range, setRange] = useState<[number, number]>([0.05, 40]); // zoom limits, relative to the fitted zoom once known
  const first = useRef(true);
  const onEngineStop = useCallback(() => {
    if (first.current && fg.current) {
      fit(fg.current, painter, model);
      setRange([painter.view.fitK * 0.6, painter.view.fitK * 10]);
    }
    first.current = false;
    setCool(0);
    wake();
  }, [painter, model, wake]);

  useEffect(() => {
    Object.assign(focus, { selected, preview, matches });
    wake();
  }, [focus, selected, preview, matches, wake]);

  // Wheel and trackpad pinch: an eased, damped zoom towards the cursor instead of d3-zoom's instant steps. The target zoom
  // moves with every wheel event; each frame the real zoom closes 1 - e^(-dt/90ms) of the gap, which is the soft tail.
  // Touch pinch and drag-pan stay with d3-zoom so they track the fingers 1:1.
  const zoomTo = useRef({ kT: 1, sx: 0, sy: 0, raf: 0 });
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
    el.addEventListener("pointerdown", stop);
    return () => { el.removeEventListener("wheel", onWheel, { capture: true }); el.removeEventListener("pointerdown", stop); stop(); };
  }, [painter]);

  // the chrome moves with the selection (the panel slides in), so measure again once it has settled
  useEffect(() => {
    measureInsets(painter.view);
    const id = setTimeout(() => {
      measureInsets(painter.view);
      if (!selected && fg.current && Math.abs(zoomK.current / painter.view.fitK - 1) < 0.05) fit(fg.current, painter, model);
      wake();
    }, 460);
    return () => clearTimeout(id);
  }, [selected, briefOpen, painter, model, wake]);

  useEffect(() => {
    const onResize = () => {
      setSize({ w: innerWidth, h: innerHeight });
      // a map still at its fitted view follows the window; one the reader has moved stays put
      requestAnimationFrame(() => {
        if (fg.current && Math.abs(zoomK.current / painter.view.fitK - 1) < 0.05) fit(fg.current, painter, model);
        wake();
      });
    };
    addEventListener("resize", onResize);
    return () => removeEventListener("resize", onResize);
  }, [painter, model, wake]);

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
      const g = fg.current!, ms = reduced() ? 0 : FEEL.glideMs;
      measureInsets(painter.view);
      const phone = innerWidth <= 640;
      const left = phone ? 0 : painter.view.left, right = phone ? 0 : panelWidth + 16;
      const top = painter.view.top, bottom = phone ? innerHeight * 0.58 + 8 : painter.view.bottom;
      let k = Math.max(zoomK.current, painter.view.fitK * 1.6); // always closer than the fitted view, so neighbours get names
      if (other) k = Math.min(k, Math.max(80, innerWidth - left - right - 80) / Math.max(1, Math.abs(n.x! - other.x!)), Math.max(80, innerHeight - top - bottom - 64) / Math.max(1, Math.abs(n.y! - other.y!)));
      // keep the Item clear of the inspector: left of the panel on desktop, above the sheet on phones
      const dx = (right - left) / 2 / k, dy = (bottom - top) / 2 / k;
      g.centerAt((n.x! + (other?.x ?? n.x!)) / 2 + dx, (n.y! + (other?.y ?? n.y!)) / 2 + dy, ms);
      g.zoom(k, ms);
      wake();
    },
    focusCanvas: () => wrap.current?.focus(),
  }), [panelWidth, wake, painter]);

  // Arrow keys step to the nearest Item in that direction; with nothing selected they start nearest the centre.
  function onKeyDown(e: KeyboardEvent) {
    const dir = ({ ArrowRight: [1, 0], ArrowLeft: [-1, 0], ArrowDown: [0, 1], ArrowUp: [0, -1] } as Record<string, number[]>)[e.key];
    if (!dir) return;
    e.preventDefault();
    if (!selected) {
      const c = fg.current!.centerAt();
      let best = model.nodes[0];
      for (const n of model.nodes) if (Math.hypot(n.x! - c.x, n.y! - c.y) < Math.hypot(best.x! - c.x, best.y! - c.y)) best = n;
      return onSelect(best);
    }
    const next = step(model.nodes, selected, dir[0], dir[1]);
    if (next) onSelect(next);
  }

  return (
    <div
      ref={wrap}
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
        onRenderFramePre={painter.pre}
        onRenderFramePost={painter.post}
        onNodeHover={(n) => { focus.hover = n ?? null; wake(); }}
        onNodeDrag={(n) => { focus.hover = n; setCool(Infinity); }}
        onNodeDragEnd={() => { focus.hover = null; setCool(150); wake(); }}
        onNodeClick={(n) => onSelect(n)}
        onBackgroundClick={() => onSelect(null)}
        onZoom={(t) => (zoomK.current = t.k)}
      />
    </div>
  );
});
