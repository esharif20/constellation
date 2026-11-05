import { HistoryIcon } from "lucide-react";
import { useId, useRef, useState, type KeyboardEvent } from "react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverHeader, PopoverTitle, PopoverTrigger } from "@/components/ui/popover";
import { chartPoints, changes, hoverLine, maxTokens, type Timeline } from "@/graph/history";
import { day } from "@/graph/model";

const W = 312, H = 150, BOX = { left: 44, right: W - 8, top: 10, bottom: 116 };

// Always-on cost over time, one point per scan day. Hidden until the server has at least one entry (Snapshots and old servers have none).
export function History({ timeline, onTimeTravel }: { timeline: Timeline | null; onTimeTravel?: () => void }) {
  if (!timeline?.entries.length) return null;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" className="pointer-events-auto h-11 rounded-lg px-3 text-[13px] text-text-2 sm:h-10 sm:order-last">
          <HistoryIcon data-icon="inline-start" aria-hidden />
          <span className="sm:max-lg:sr-only">History</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" sideOffset={8} className="glass w-[min(360px,calc(100vw-2rem))] gap-3 p-6">
        <Chart timeline={timeline} onTimeTravel={onTimeTravel} />
      </PopoverContent>
    </Popover>
  );
}

function Chart({ timeline, onTimeTravel }: { timeline: Timeline; onTimeTravel?: () => void }) {
  const { entries } = timeline, id = useId();
  const points = chartPoints(entries, BOX), last = entries[entries.length - 1], top = maxTokens(entries);
  const [active, setActive] = useState(points.length - 1);
  const [focused, setFocused] = useState(false);
  const refs = useRef<(SVGCircleElement | null)[]>([]);
  const shown = entries[active];
  const move = (e: KeyboardEvent, to: number) => { e.preventDefault(); const i = Math.max(0, Math.min(points.length - 1, to)); setActive(i); refs.current[i]?.focus(); };
  const onKey = (e: KeyboardEvent, i: number) => {
    if (e.key === "ArrowRight" || e.key === "ArrowUp") move(e, i + 1);
    else if (e.key === "ArrowLeft" || e.key === "ArrowDown") move(e, i - 1);
    else if (e.key === "Home") move(e, 0);
    else if (e.key === "End") move(e, points.length - 1);
  };
  return (
    <>
      <PopoverHeader>
        <PopoverTitle>Always-on cost over time</PopoverTitle>
        <p className="text-[13px] leading-[1.5] text-text-2">Tokens paid every session, one point per scan day. Unknown costs are left out.</p>
      </PopoverHeader>
      {entries.length === 1 ? (
        <p className="text-[13px] leading-[1.5] text-text-2">One scan so far. Scan again on another day to see the trend.</p>
      ) : (
        <div>
          <svg viewBox={`0 0 ${W} ${H}`} role="group" aria-labelledby={`${id}-t`} className="block w-full overflow-visible" onPointerLeave={() => !focused && setActive(points.length - 1)}>
            <title id={`${id}-t`}>Always-on tokens by scan day</title>
            {[BOX.top, BOX.bottom].map((y) => <line key={y} x1={BOX.left} x2={BOX.right} y1={y} y2={y} stroke="var(--line-1)" />)}
            <g className="fill-text-3 font-mono text-[11px]">
              <text x={BOX.left - 8} y={BOX.top + 4} textAnchor="end">{top.toLocaleString("en-US")}</text>
              <text x={BOX.left - 8} y={BOX.bottom + 4} textAnchor="end">0</text>
              <text x={BOX.left} y={H - 4}>{day(entries[0].date, false)}</text>
              <text x={BOX.right} y={H - 4} textAnchor="end">{day(last.date)}</text>
            </g>
            <polyline points={points.map((p) => `${p.x},${p.y}`).join(" ")} fill="none" stroke="var(--indigo-bright)" strokeWidth="1.5" strokeLinejoin="round" />
            {points.map((p, i) => p.marker && <line key={`m${i}`} x1={p.x} x2={p.x} y1={BOX.bottom + 2} y2={BOX.bottom + 6} stroke="var(--text-3)" strokeWidth="1.5" />)}
            {points.map((p, i) => (
              <g key={p.entry.date}>
                <circle cx={p.x} cy={p.y} r="2.5" fill="var(--indigo-bright)" aria-hidden />
                <circle ref={(el) => { refs.current[i] = el; }} cx={p.x} cy={p.y} r="9" fill="transparent" tabIndex={i === active ? 0 : -1} role="img" aria-label={hoverLine(p.entry)}
                  className="cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-ring"
                  onPointerEnter={() => setActive(i)} onFocus={() => { setActive(i); setFocused(true); }} onBlur={() => setFocused(false)} onKeyDown={(e) => onKey(e, i)} />
              </g>
            ))}
          </svg>
          <p className="mt-2 min-h-5 font-mono text-[12px] leading-5 text-text-2 tabular-nums">{hoverLine(shown)}</p>
          <table className="sr-only">
            <caption>Always-on tokens by scan day</caption>
            <thead><tr><th>Date</th><th>Tokens</th><th>Items</th><th>Changes</th></tr></thead>
            <tbody>{entries.map((e) => <tr key={e.date}><td>{day(e.date)}</td><td>{e.always_on}</td><td>{e.items}</td><td>{changes(e) || "none"}</td></tr>)}</tbody>
          </table>
        </div>
      )}
      {last.unknown > 0 && <p className="text-[13px] leading-[1.5] text-text-2">Plus {last.unknown} Items of unknown cost.</p>}
      {entries.length > 1 && onTimeTravel && <Button variant="outline" size="sm" className="self-start" onClick={onTimeTravel}>Time travel</Button>}
    </>
  );
}
