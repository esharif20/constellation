import { costRadius, kindName, relName, type Model } from "@/graph/model";
import { cn } from "@/lib/utils";

// Colour never carries identity alone: every kind is named here, with its count and the glyph the map uses.
export function Legend({ model, hidden, pack, onPack }: { model: Model; hidden: boolean; pack: string | null; onPack: (origin: string) => void }) {
  const counts = new Map<string, number>();
  for (const n of model.nodes) counts.set(n.kind, (counts.get(n.kind) ?? 0) + 1);
  const kinds = [...counts].sort((a, b) => b[1] - a[1]);
  const edges = [...new Set(model.links.map((l) => l.kind))];
  const hasOverlaps = model.overlaps.length > 0;
  const sizes = [model.costRef / 9, model.costRef / 4, model.costRef];
  return (
    <ul
      aria-label="Legend"
      className={cn(
        "pointer-events-none fixed bottom-4 left-4 flex max-w-[calc(100vw-2rem)] flex-wrap items-center gap-x-4 gap-y-2 text-xs text-text-2 transition-opacity duration-(--t) sm:bottom-6 sm:left-6 sm:gap-x-6 sm:text-[13px]",
        hidden && "opacity-0 sm:opacity-100",
      )}
    >
      {kinds.map(([kind, k]) => (
        <li key={kind} className="inline-flex items-center gap-2">
          <span className="glyph" data-kind={kind} />
          {kindName(kind)}
          <b className="font-mono text-xs font-normal text-foreground tabular-nums">{k}</b>
        </li>
      ))}
      {edges.length > 0 && <li aria-hidden className="hidden h-3.5 w-px bg-line-2 sm:block" />}
      {edges.map((kind) => (
        <li key={kind} className="hidden items-center gap-2 sm:inline-flex">
          <span className="edge-key" data-kind={kind} />
          {relName(kind, true).toLowerCase()}
        </li>
      ))}
      {model.packs.length > 0 && (
        <li className={cn("flex basis-full flex-wrap items-center gap-x-2 gap-y-1", hidden ? "pointer-events-none sm:pointer-events-auto" : "pointer-events-auto")}>
          <span>Packs</span>
          {model.packs.slice(0, 6).map((p, i) => (
            <button key={p.origin} type="button" aria-pressed={pack === p.origin} onClick={() => onPack(p.origin)} title={`Light up the ${p.members.length} Items from ${p.origin}`} className={cn("inline-flex h-6 cursor-pointer items-center gap-1.5 rounded-full border px-2 text-xs hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring", pack === p.origin ? "border-line-2 bg-card text-foreground" : "border-transparent text-text-2", i > 2 && "hidden sm:inline-flex")}>
              {p.origin}
              <b className="font-mono text-xs font-normal text-foreground tabular-nums">{p.members.length}</b>
            </button>
          ))}
        </li>
      )}
      <li aria-hidden className="hidden basis-full sm:block" />
      <li className="hidden items-center gap-2 sm:inline-flex">
        Size = always-on tokens
        {sizes.map((t) => (
          <span key={t} className="inline-flex items-center gap-1">
            <span className="size-dot" style={{ width: 2 * costRadius(t, model.costRef), height: 2 * costRadius(t, model.costRef) }} />
            <b className="font-mono text-xs font-normal text-foreground tabular-nums">{Math.round(t)}</b>
          </span>
        ))}
      </li>
      {model.nodes.some((n) => n.disabled) && (
        <li className="inline-flex items-center gap-2">
          <span className="glyph" data-kind="plugin" data-disabled />
          dimmed ring = plugin switched off
        </li>
      )}
      <li className="inline-flex items-center gap-2">
        <span className="size-dot" data-unknown style={{ width: 2 * costRadius(null, model.costRef), height: 2 * costRadius(null, model.costRef) }} />
        cost unknown
      </li>
      {hasOverlaps && (
        <>
          <li aria-hidden className="hidden h-3.5 w-px bg-line-2 sm:block" />
          <OverlapKey label="duplicate" dash={undefined} width={2} />
          <OverlapKey label="wraps" dash="5 3" width={1.5} arrow />
          <OverlapKey label="overlaps (on hover)" dash="0.1 3.5" width={1.2} round />
        </>
      )}
    </ul>
  );
}

// Same line styles as paint.ts overlapArc, in the same token.
function OverlapKey({ label, dash, width, arrow, round }: { label: string; dash?: string; width: number; arrow?: boolean; round?: boolean }) {
  return (
    <li className="hidden items-center gap-2 sm:inline-flex">
      <svg aria-hidden width="22" height="10" className="flex-none text-overlap" fill="none" stroke="currentColor" strokeWidth={width} strokeDasharray={dash} strokeLinecap={round ? "round" : "butt"}>
        <path d="M0 5H20" />
        {arrow && <path d="M16 2 20 5 16 8" strokeDasharray="none" strokeWidth="1.2" />}
      </svg>
      {label}
    </li>
  );
}
