import { useState } from "react";
import { Separator } from "@/components/ui/separator";
import { Button } from "@/components/ui/button";
import type { GNode, Model } from "@/graph/model";
import { CAP, relatedGroups, type RelatedGroup } from "@/lib/related";

type Pick = { onSelect: (n: GNode) => void; onPreview: (n: GNode | null) => void };

function Group({ g, onSelect, onPreview }: { g: RelatedGroup } & Pick) {
  const [all, setAll] = useState(false);
  const rows = all ? g.rows : g.rows.slice(0, CAP);
  return (
    <section className="mt-4">
      <h3 className="mb-1 text-xs font-medium tracking-[0.02em] text-text-3">{g.title} <span className="ml-1 font-mono tabular-nums">{g.rows.length}</span></h3>
      <ul className="-mx-2 flex flex-col">
        {rows.map(({ other, reason }) => (
          <li key={other.id}>
            <ItemButton item={other} onSelect={onSelect} onPreview={onPreview} />
            {reason && <p className="px-2 pb-1 pl-[34px] text-[13px] leading-[1.45] text-text-2 [overflow-wrap:anywhere]">{reason}</p>}
          </li>
        ))}
      </ul>
      {g.rows.length > CAP && (
        <button type="button" aria-expanded={all} onClick={() => setAll(!all)} className="mt-0.5 inline-flex min-h-10 items-center rounded-md text-[13px] text-indigo-bright outline-none hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/50 max-sm:min-h-11">
          {all ? "Show fewer" : `Show all ${g.rows.length}`}
        </button>
      )}
    </section>
  );
}

export function Related({ item, model, onSelect, onPreview }: { item: GNode; model: Model } & Pick) {
  const groups = relatedGroups(item, model);
  return (
    <>
      <Separator className="mt-6" />
      {groups.length === 0 && <p className="mt-4 text-[13px] text-text-3">No Relations to other Items.</p>}
      {groups.map((g) => <Group key={`${item.id}/${g.title}`} g={g} onSelect={onSelect} onPreview={onPreview} />)}
    </>
  );
}

// A partner Item: click glides to it, hover or focus previews it on the map.
function ItemButton({ item, onSelect, onPreview }: { item: GNode } & Pick) {
  return (
    <Button
      variant="ghost"
      onClick={() => onSelect(item)}
      onMouseEnter={() => onPreview(item)}
      onMouseLeave={() => onPreview(null)}
      onFocus={() => onPreview(item)}
      onBlur={() => onPreview(null)}
      className="h-auto min-h-10 w-full justify-start gap-3 rounded-md px-2 py-1 text-left text-sm font-normal text-foreground whitespace-normal"
    >
      <span className="glyph" data-kind={item.kind} />
      <span className="[overflow-wrap:anywhere]">{item.name}</span>
    </Button>
  );
}
