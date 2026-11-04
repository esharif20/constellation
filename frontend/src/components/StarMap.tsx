import { forceCollide, forceX, forceY, type ForceLink, type ForceManyBody } from "d3-force";
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState, type KeyboardEvent } from "react";
import ForceGraph2D, { type ForceGraphMethods } from "react-force-graph-2d";
import { step, type GLink, type GNode, type Model } from "@/graph/model";
import { FEEL, makePainter } from "@/graph/paint";

export type StarMapHandle = { glideTo: (n: GNode) => void; focusCanvas: () => void };
type Props = {
  model: Model;
  selected: GNode | null;
  preview: GNode | null; // an Item hovered in the inspector or search list
  matches: Set<GNode> | null;
  panelWidth: number; // px the inspector covers on the right (0 on phones, where it is a bottom sheet)
  onSelect: (n: GNode | null) => void;
};

const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

// Gently pulls each node toward its cluster centroid so clusters read as regions.
function clusterPull(model: Model, strength: number) {
  const force = (alpha: number) => {
    for (const c of model.clusters) {
      let x = 0, y = 0;
      for (const n of c.members) { x += n.x!; y += n.y!; }
      x /= c.members.length; y /= c.members.length;
      for (const n of c.members) { n.vx! += (x - n.x!) * strength * alpha; n.vy! += (y - n.y!) * strength * alpha; }
    }
  };
  force.initialize = () => {};
  return force;
}

export const StarMap = forwardRef<StarMapHandle, Props>(function StarMap({ model, selected, preview, matches, panelWidth, onSelect }, ref) {
  const fg = useRef<ForceGraphMethods<GNode, GLink> | undefined>(undefined);
  const wrap = useRef<HTMLDivElement>(null);
  const painter = useMemo(() => makePainter(model, reduced()), [model]);
  const [size, setSize] = useState({ w: innerWidth, h: innerHeight });
  const [data, setData] = useState<{ nodes: GNode[]; links: GLink[] }>({ nodes: [], links: [] });
  const zoomK = useRef(1);
  const focus = painter.focus;

  useEffect(() => {
    Object.assign(focus, { selected, preview, matches });
  }, [focus, selected, preview, matches]);

  useEffect(() => {
    const onResize = () => setSize({ w: innerWidth, h: innerHeight });
    addEventListener("resize", onResize);
    return () => removeEventListener("resize", onResize);
  }, []);

  // Forces go in before the data so the warm-up ticks run with them and the first paint is already settled.
  useEffect(() => {
    const g = fg.current!;
    (g.d3Force("link") as ForceLink<GNode, GLink>).distance((l) => (l.kind === "contains" ? 34 : 60)).strength(0.5);
    (g.d3Force("charge") as ForceManyBody<GNode>).strength(-55).distanceMax(320);
    g.d3Force("center", null);
    g.d3Force("collide", forceCollide<GNode>((n) => n.r + 3));
    g.d3Force("x", forceX<GNode>().strength(0.06));
    g.d3Force("y", forceY<GNode>().strength(0.06));
    g.d3Force("cluster", clusterPull(model, 0.12));
    setData({ nodes: model.nodes, links: model.links });
  }, [model]);

  useEffect(() => {
    if (!data.nodes.length) return;
    const id = requestAnimationFrame(() => {
      fg.current?.zoomToFit(0, innerWidth <= 640 ? 48 : 110); // room for the top bar and legend
      painter.view.fitK = fg.current?.zoom() ?? 1;
    });
    return () => cancelAnimationFrame(id);
  }, [data, painter]);

  useImperativeHandle(ref, () => ({
    glideTo(n) {
      const g = fg.current!, ms = reduced() ? 0 : FEEL.glideMs, k = Math.max(zoomK.current, 1.7);
      const phone = innerWidth <= 640;
      // keep the Item clear of the inspector: left of the panel on desktop, above the sheet on phones
      const dx = phone ? 0 : (panelWidth + 16) / 2 / k, dy = phone ? (innerHeight * 0.26) / k : 0;
      g.centerAt(n.x! + dx, n.y! + dy, ms);
      g.zoom(k, ms);
    },
    focusCanvas: () => wrap.current?.focus(),
  }), [panelWidth]);

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
      className="fixed inset-0 outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
    >
      <ForceGraph2D<GNode, GLink>
        ref={fg}
        graphData={data}
        width={size.w}
        height={size.h}
        backgroundColor="rgba(0,0,0,0)"
        nodeLabel={() => ""} // names are drawn on the canvas; no browser tooltip
        autoPauseRedraw={false} // fades are eased per frame, so keep painting
        warmupTicks={260}
        cooldownTicks={400}
        d3AlphaDecay={0.025}
        d3VelocityDecay={0.3}
        minZoom={0.15}
        maxZoom={8}
        nodeCanvasObjectMode={() => "replace"}
        nodeCanvasObject={painter.node}
        nodePointerAreaPaint={painter.pointer}
        linkCanvasObjectMode={() => "replace"}
        linkCanvasObject={painter.link}
        onRenderFramePre={painter.pre}
        onRenderFramePost={painter.post}
        onNodeHover={(n) => (focus.hover = n ?? null)}
        onNodeDrag={(n) => (focus.hover = n)}
        onNodeDragEnd={() => (focus.hover = null)}
        onNodeClick={(n) => onSelect(n)}
        onBackgroundClick={() => onSelect(null)}
        onZoom={(t) => (zoomK.current = t.k)}
      />
    </div>
  );
});
