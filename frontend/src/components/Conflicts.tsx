import { Button } from "@/components/ui/button";
import type { Conflict } from "@/graph/lenses";

type Named = { id: string; name: string; kind: string };

export const conflictTitle = (c: Conflict): string => {
  if (c.kind === "trigger") return `Both claim "${c.key}"`;
  if (c.kind === "mcp_name") return `Two servers named ${c.key}`;
  const [event, , matcher] = c.key.split(/(:)/);
  return matcher ? `Hooks on ${event} (${matcher})` : `Hooks on ${event}`;
};

// Group order: the ones that silently change behaviour first.
const ORDER: Conflict["kind"][] = ["trigger", "mcp_name", "hook"];
export const sortConflicts = (rows: Conflict[]): Conflict[] => [...rows].sort((a, b) => ORDER.indexOf(a.kind) - ORDER.indexOf(b.kind));

export function Conflicts({ rows, nodes, onItem }: { rows: Conflict[]; nodes: Named[]; onItem: (id: string) => void }) {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  return <section aria-label="Clashes">
    <h3 className="text-sm font-medium">Clashes</h3>
    {rows.length === 0 ? <p className="mt-2 text-[13px] leading-[1.4] text-text-2">No clashes found. Nothing in your setup fights over the same hook, name or trigger phrase.</p> : <ul className="mt-2 flex flex-col gap-3">
      {sortConflicts(rows).map((c) => <li key={`${c.kind}:${c.key}`}>
        <p className="text-sm font-medium">{conflictTitle(c)}</p>
        <p className="mt-1 text-[13px] leading-[1.4] text-text-2">{c.reason}</p>
        <ul className="-mx-2 mt-1 flex flex-col gap-1">
          {c.item_ids.map((id) => {
            const n = byId.get(id);
            const body = <><span aria-hidden className="glyph" data-kind={n?.kind ?? "skill"} /><span className="min-w-0 flex-1 truncate text-sm">{n?.name ?? id}</span></>;
            return <li key={id}>{n
              ? <Button variant="ghost" className="h-auto min-h-10 w-full min-w-0 justify-start gap-3 px-2 py-2 text-left font-normal whitespace-normal" onClick={() => onItem(id)}>{body}</Button>
              : <div className="flex min-h-10 items-center gap-3 px-2 py-2">{body}</div>}</li>;
          })}
        </ul>
      </li>)}
    </ul>}
  </section>;
}
