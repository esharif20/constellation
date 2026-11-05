import { useLayoutEffect, useRef } from "react";
import { Badge } from "@/components/ui/badge";
import { kindName, originTail, tipBadges, usageLine, type GNode, type Model } from "@/graph/model";
import { placeTip } from "@/graph/names";
import type { Painter } from "@/graph/paint";

// The hover tooltip (docs/design/labels.md 9): the full name and the cost of a star, in the DOM. Decorative (the Inspector and the
// live region are the accessible path), so aria-hidden and never focusable. `x, y, r` are the star's screen centre and radius, read once at show.
export type Tip = { n: GNode; x: number; y: number; r: number; touch: boolean };

const tokens = (v: number | null | undefined) => (v == null ? <i className="text-text-3">unknown</i> : <span className="font-mono tabular-nums text-foreground">{v.toLocaleString()} tokens</span>);

export function Hover({ tip, model, painter, wake }: { tip: Tip; model: Model; painter: Painter; wake: () => void }) {
  const box = useRef<HTMLDivElement>(null);
  const n = tip.n;

  // Measured once while hidden, placed, then shown; it also tells the canvas where it is, so names keep out of its box.
  useLayoutEffect(() => {
    const el = box.current!, w = el.offsetWidth, h = el.offsetHeight, v = painter.view;
    const p = placeTip({ x: tip.x, y: tip.y, r: tip.r }, { w, h }, { x0: v.left + 8, y0: v.top + 8, x1: innerWidth - v.right - 8, y1: innerHeight - v.bottom - 8 }, tip.touch);
    el.style.transform = `translate3d(${p.x}px, ${p.y}px, 0)`;
    el.style.visibility = "visible";
    painter.setTip([p.x, p.y, p.x + w, p.y + h], n);
    wake();
    return () => { painter.setTip(null, null); wake(); };
  }, [tip, n, painter, wake]);

  const badges = tipBadges(n, model), usage = usageLine(n, model.usageWindow), line = n.label || n.description, other = n.cluster?.name === "Other";
  return (
    <div ref={box} aria-hidden className="pointer-events-none fixed top-0 left-0 z-10 invisible">
      <div className="glass animate-tip-in w-max max-w-[300px] min-w-[200px] rounded-lg border border-line-1 px-3 py-2.5 shadow-(--shadow-float)">
        <p className="flex items-start gap-2 text-sm font-medium text-foreground">
          <span className="glyph mt-[5px]" data-kind={n.kind} />
          <span className="line-clamp-2 [overflow-wrap:anywhere]">{n.name}</span>
        </p>
        <p className="mt-0.5 text-xs text-text-3">
          {kindName(n.kind)}
          {n.cluster && !other && <> · <span className="font-serif text-[13px] tracking-[0.01em] text-text-2 italic">{n.cluster.name}</span></>}
          {n.origin && <> · {originTail(n.origin)}</>}
        </p>
        <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs">
          <dt className="text-text-3">Always on</dt>
          <dd>{tokens(n.cost?.always_on)}</dd>
          <dt className="text-text-3">On use</dt>
          <dd>{tokens(n.cost?.on_use)}</dd>
        </dl>
        {usage && <p className="mt-2 text-xs text-text-2">{usage}</p>}
        {(badges.disabled || badges.overlap) && (
          <p className="mt-2 flex flex-wrap gap-1.5">
            {badges.disabled && <Badge>Disabled</Badge>}
            {badges.overlap && <Badge><span className="size-1.5 rounded-full bg-overlap" />{badges.overlap}</Badge>}
          </p>
        )}
        {line && <p className="mt-2 truncate text-xs text-text-2">{line}</p>}
        {tip.touch && <p className="mt-2 text-xs text-text-3">Tap again to open</p>}
      </div>
    </div>
  );
}
