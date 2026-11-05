import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { day, noun, type GNode, type GOverlap, type Model } from "@/graph/model";
import { MiniBar } from "./MiniBar";

const unknown = <i className="font-sans text-text-3">unknown</i>;
const tokens = (n: number) => `${n.toLocaleString()} tokens`;

function Chip({ label, wide, children }: { label: string; wide?: boolean; children: ReactNode }) {
  return (
    <div className={`rounded-lg border bg-surface-2 px-3 py-2 ${wide ? "col-span-full" : ""}`}>
      <dt className="text-xs text-text-3">{label}</dt>
      <dd className="mt-0.5 font-mono text-[13px] tabular-nums [overflow-wrap:anywhere]">{children}</dd>
    </div>
  );
}

// Top x% among Items with a known always-on cost; null when this one is unknown.
function rank(model: Model, item: GNode) {
  const v = item.cost?.always_on;
  if (v == null) return null;
  const known = model.nodes.flatMap((n) => n.cost?.always_on ?? []);
  return Math.max(1, Math.ceil(((known.filter((k) => k > v).length + 1) / known.length) * 100));
}

const role = (item: GNode, o: GOverlap) => (o.verdict === "duplicate" ? "duplicate" : o.verdict === "wrapper" ? (o.a === item ? "wraps" : "wrapped by") : "overlaps");

export function Facts({ model, item, onSelect, onPreview }: { model: Model; item: GNode; onSelect: (n: GNode) => void; onPreview: (n: GNode | null) => void }) {
  const c = item.cost, w = model.usageWindow, u = item.usage, hw = item.weight;
  const always = c?.always_on ?? null, onUse = c?.on_use ?? null, top = rank(model, item);
  const overlaps = model.overlapsOf.get(item) ?? [];
  const usage = u
    ? u.count > 0
      ? <>{noun(u.count, "use")}{u.last_used && <span className="text-text-3"> · last {day(u.last_used)}</span>}</>
      : w?.files ? <span className="font-sans">Never seen in {noun(w.files, "transcript")}</span> : <i className="font-sans text-text-3">No transcripts scanned</i>
    : <span className="font-sans text-text-2">{item.kind === "hook" ? "Not tracked for hooks" : item.kind === "plugin" ? "Not tracked for plugins" : "Not tracked"}</span>;
  return (
    <dl className="mt-4 grid animate-fade-in grid-cols-1 gap-2 min-[360px]:grid-cols-2">
      <Chip label="Always-on">
        {always == null ? unknown : <>
          {tokens(always)}
          <MiniBar value={always} max={model.costRef} off={item.disabled} label={`Always-on ${tokens(always)}${top ? `, top ${top}% of known costs` : ""}`} />
          {top && <span className="mt-1 block font-sans text-xs text-text-3">top {top}%</span>}
        </>}
      </Chip>
      <Chip label="On use">
        {onUse == null ? unknown : <>
          {tokens(onUse)}
          <MiniBar value={onUse} max={model.costRef} off={item.disabled} label={`On use ${tokens(onUse)}`} />
        </>}
        {onUse == null && <span className="mt-1 block font-sans text-xs text-text-3">{item.kind === "hook" ? "Known only when it runs." : <>Run <code className="font-mono">constellation scan --count-bodies</code> to measure.</>}</span>}
      </Chip>
      <Chip label="Usage" wide>
        {usage}
        {w?.first && w.last && u && <span className="mt-1 block font-sans text-xs text-text-3">Transcripts {day(w.first, false)} to {day(w.last, false)}</span>}
      </Chip>
      {hw && (
        <Chip label="Session-start weight" wide>
          {hw.bytes == null ? unknown : `${hw.bytes.toLocaleString()} bytes`}
          {hw.tokens != null ? <span className="block">{tokens(hw.tokens)}</span> : hw.bytes != null && <i className="block font-sans text-text-3">tokens not counted</i>}
        </Chip>
      )}
      <Chip label="Cluster" wide><span className="font-serif text-[17px] leading-tight tracking-[0.01em] italic">{item.cluster?.name ?? "Not clustered"}</span></Chip>
      {overlaps.length > 0 && (
        <div className="col-span-full flex flex-wrap gap-2">
          {overlaps.slice(0, 3).map((o) => {
            const other = o.a === item ? o.b : o.a;
            return (
              <button
                key={other.id} type="button" title={o.reason}
                onClick={() => onSelect(other)} onMouseEnter={() => onPreview(other)} onMouseLeave={() => onPreview(null)} onFocus={() => onPreview(other)} onBlur={() => onPreview(null)}
                className="inline-flex min-h-10 max-w-full items-center gap-2 rounded-lg border border-overlap/60 bg-surface-2 px-2.5 py-1 text-left text-[13px] outline-none hover:bg-surface-3 focus-visible:ring-[3px] focus-visible:ring-ring/50 max-sm:min-h-11"
              >
                <span className="glyph shrink-0" data-kind={other.kind} />
                <span className="min-w-0 [overflow-wrap:anywhere]">{other.name}</span>
                <Badge className="border-overlap/60 bg-transparent text-overlap">{role(item, o)}</Badge>
              </button>
            );
          })}
          {overlaps.length > 3 && <span className="self-center text-xs text-text-3">+{overlaps.length - 3} more</span>}
        </div>
      )}
    </dl>
  );
}
