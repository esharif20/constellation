import { kindName, relName, type Model } from "@/graph/model";
import { cn } from "@/lib/utils";

// Colour never carries identity alone: every kind is named here, with its count and the glyph the map uses.
export function Legend({ model, hidden }: { model: Model; hidden: boolean }) {
  const counts = new Map<string, number>();
  for (const n of model.nodes) counts.set(n.kind, (counts.get(n.kind) ?? 0) + 1);
  const kinds = [...counts].sort((a, b) => b[1] - a[1]);
  const edges = [...new Set(model.links.map((l) => l.kind))];
  return (
    <ul
      aria-label="Legend"
      className={cn(
        "pointer-events-none fixed bottom-4 left-4 flex max-w-[calc(100vw-2rem)] flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground transition-opacity duration-(--t) sm:bottom-6 sm:left-6 sm:gap-x-6 sm:text-[13px]",
        hidden && "opacity-0 sm:opacity-100",
      )}
    >
      {kinds.map(([kind, k]) => (
        <li key={kind} className="inline-flex items-center gap-2">
          <span className="glyph" data-kind={kind} />
          {kindName(kind)}
          <b className="font-medium text-foreground tabular-nums">{k}</b>
        </li>
      ))}
      {edges.length > 0 && <li aria-hidden className="hidden h-3.5 w-px bg-input sm:block" />}
      {edges.map((kind) => (
        <li key={kind} className="hidden items-center gap-2 sm:inline-flex">
          <span className="edge-key" data-kind={kind} />
          {relName(kind, true).toLowerCase()}
        </li>
      ))}
    </ul>
  );
}
