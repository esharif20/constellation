import { XIcon } from "lucide-react";
import { useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Pane } from "@/components/Motion";
import { absentAt, type HistoryEntry } from "@/graph/history";
import { day } from "@/graph/model";

// Time travel (#70): one step per scan day. Stars never move; the ones first seen after the date fade out in place.
export function Scrubber({ entries, nodes, firstSeen, date, onDate, onClose }: { entries: HistoryEntry[]; nodes: { id: string }[]; firstSeen: Record<string, string>; date: string; onDate: (d: string) => void; onClose: () => void }) {
  const range = useRef<HTMLInputElement>(null);
  useEffect(() => range.current?.focus({ preventScroll: true }), []);
  const i = Math.max(0, entries.findIndex((e) => e.date === date)), here = nodes.length - absentAt(nodes, firstSeen, date).size;
  const gone = Math.max(0, entries[i].items - here); // on that day but not in today's scan: counted, never drawn (their names are not kept)
  const text = `${here} of ${nodes.length} Items${gone ? ` · ${gone} since removed` : ""}`;
  return (
    <Pane as="section" from="bottom" aria-labelledby="scrub-title" onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); onClose(); } }}
      className="glass fixed bottom-4 left-4 z-10 flex h-14 w-[calc(100vw-2rem)] items-center gap-3 rounded-lg border border-line-1 px-4 sm:bottom-6 sm:left-1/2 sm:w-[min(560px,calc(100vw-2rem))] sm:-translate-x-1/2">
      <h2 id="scrub-title" className="sr-only">Time travel</h2>
      <span className="w-[88px] shrink-0 font-mono text-[12px] text-foreground tabular-nums">{day(date)}</span>
      <input ref={range} type="range" min={0} max={entries.length - 1} step={1} value={i} onChange={(e) => onDate(entries[+e.target.value].date)}
        aria-label="Scan day" aria-valuetext={`${day(date)}, ${entries[i].items} Items`} className="min-w-0 flex-1 accent-(--indigo-bright)" />
      <span className="hidden w-[216px] shrink-0 text-[13px] text-text-2 sm:inline" aria-hidden>{text}</span>
      <Button variant="ghost" size="icon" aria-label="Close time travel" onClick={onClose}><XIcon aria-hidden /></Button>
      <span className="sr-only" aria-live="polite">{text}</span>
    </Pane>
  );
}
