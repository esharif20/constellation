import { ArrowLeftIcon, XIcon } from "lucide-react";
import { forwardRef, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { relName, withContents, type GNode, type GOverlap, type Model } from "@/graph/model";
import { verdictOf } from "@/lib/verdict";
import { Facts } from "./inspector/Facts";
import { Header } from "./inspector/Header";
import { VerdictBanner } from "./inspector/Verdict";

type Props = { model: Model; item: GNode; onSelect: (n: GNode) => void; onPreview: (n: GNode | null) => void; onClose: () => void; backTo?: string; whatIf?: ReadonlySet<GNode> | null; removed?: ReadonlySet<GNode> | null; onToggle?: (n: GNode) => void }; // backTo: the focused cluster's name, when the sheet replaces its card (narrow screens)

// Non-modal on purpose: the map stays live beside it. A side panel on desktop, a bottom sheet on phones.
export const Inspector = forwardRef<HTMLElement, Props>(function Inspector({ model, item, onSelect, onPreview, onClose, backTo, whatIf = null, removed = null, onToggle }, ref) {
  const scroll = useRef<HTMLDivElement>(null);
  useEffect(() => {
    scroll.current?.scrollTo({ top: 0 });
  }, [item]);

  const groups = new Map<string, GNode[]>();
  for (const l of model.links) {
    const out = l.source === item;
    if (!out && l.target !== item) continue;
    const key = relName(l.kind, out);
    groups.set(key, [...(groups.get(key) ?? []), out ? l.target : l.source]);
  }

  const verdict = verdictOf(item, model.overlapsOf.get(item) ?? [], model.links.filter((l) => l.source === item && l.kind === "contains").map((l) => l.target), model.usageWindow);
  return (
    <aside
      ref={ref}
      aria-labelledby="i-name"
      className="glass fixed inset-x-0 bottom-0 flex max-h-[58dvh] animate-sheet-in flex-col rounded-t-2xl border border-b-0 shadow-(--shadow-float) sm:inset-x-auto sm:top-[76px] sm:right-4 sm:bottom-4 sm:max-h-none sm:w-[380px] sm:animate-panel-in sm:rounded-xl sm:border-b"
    >
      <div aria-hidden className="mx-auto mt-2 h-1 w-9 rounded-full bg-line-2 sm:hidden" />
      <Button variant="ghost" size="icon-lg" onClick={onClose} aria-label="Close inspector" className="absolute top-3 right-3 rounded-md text-text-3 hover:text-foreground sm:top-2.5 sm:right-2.5">
        <XIcon />
      </Button>
      <div ref={scroll} className="overflow-y-auto overscroll-contain px-4 pt-3 pb-6 sm:px-6 sm:pt-6">
        {backTo && <Button variant="ghost" className="-mx-2 mb-1 h-10 max-w-[calc(100%-3rem)] justify-start gap-2 px-2 text-[13px] text-text-2" onClick={onClose}><ArrowLeftIcon aria-hidden /><span className="truncate">Back to {backTo}</span></Button>}
        <Header item={item} model={model} />
        <VerdictBanner verdict={verdict} />
        <Facts model={model} item={item} onSelect={onSelect} onPreview={onPreview} />
        {whatIf && onToggle && <WhatIfToggle model={model} item={item} whatIf={whatIf} removed={removed} onToggle={onToggle} />}

        <p className="mt-6 max-w-[65ch] text-sm leading-[1.55] text-text-2 whitespace-pre-wrap [overflow-wrap:anywhere]">{item.description || "No description."}</p>
        <p className="mt-3 font-mono text-xs leading-[1.45] text-text-3 [overflow-wrap:anywhere]">{item.source}</p>

        <Separator className="mt-6" />
        {groups.size === 0 && <p className="mt-4 text-[13px] text-text-3">No Relations to other Items.</p>}
        {[...groups].map(([title, others]) => (
          <section key={title} className="mt-4">
            <h3 className="mb-1 text-xs font-medium tracking-[0.02em] text-text-3">
              {title} <span className="ml-1 font-mono tabular-nums">{others.length}</span>
            </h3>
            <ul className="-mx-2 flex flex-col">
              {others.sort((a, b) => a.name.localeCompare(b.name)).map((o) => (
                <li key={o.id}>
                  <ItemButton item={o} onSelect={onSelect} onPreview={onPreview} />
                </li>
              ))}
            </ul>
          </section>
        ))}
        <Overlaps item={item} model={model} onSelect={onSelect} onPreview={onPreview} />
      </div>
    </aside>
  );
});

function WhatIfToggle({ model, item, whatIf, removed, onToggle }: { model: Model; item: GNode; whatIf: ReadonlySet<GNode>; removed: ReadonlySet<GNode> | null; onToggle: (n: GNode) => void }) {
  const ticked = whatIf.has(item), viaParent = !ticked && !!removed?.has(item), n = withContents(model, new Set([item])).size;
  return <div className="mt-4">
    <Button variant="outline" className="h-10" aria-pressed={ticked || viaParent} disabled={viaParent} onClick={() => onToggle(item)}>{viaParent ? "Removed with its plugin" : ticked ? "Put back" : "Remove in what-if"}</Button>
    {n > 1 && !ticked && <p className="mt-1 text-xs text-text-3">Removes {n} Items</p>}
  </div>;
}

type Rows = { title: string; rows: { other: GNode; reason: string }[] };
const GROUPS = ["Duplicate of", "Wraps", "Wrapped by", "Overlaps with"];

function Overlaps({ item, model, onSelect, onPreview }: Pick<Props, "model" | "item" | "onSelect" | "onPreview">) {
  const title = (o: GOverlap) => (o.verdict === "duplicate" ? GROUPS[0] : o.verdict === "wrapper" ? (o.a === item ? GROUPS[1] : GROUPS[2]) : GROUPS[3]);
  const groups: Rows[] = GROUPS.map((t) => ({
    title: t,
    rows: (model.overlapsOf.get(item) ?? []).filter((o) => title(o) === t).map((o) => ({ other: o.a === item ? o.b : o.a, reason: o.reason })),
  })).filter((g) => g.rows.length);
  if (!groups.length) return null;
  return (
    <>
      <Separator className="mt-6" />
      {groups.map((g) => (
        <section key={g.title} className="mt-4">
          <h3 className="mb-1 text-xs font-medium tracking-[0.02em] text-text-3">
            {g.title} <span className="ml-1 font-mono tabular-nums">{g.rows.length}</span>
          </h3>
          <ul className="-mx-2 flex flex-col">
            {g.rows.map(({ other, reason }) => (
              <li key={other.id}>
                <ItemButton item={other} onSelect={onSelect} onPreview={onPreview} />
                <p className="px-2 pb-1 pl-[34px] text-[13px] leading-[1.45] text-text-2 [overflow-wrap:anywhere]">{reason}</p>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </>
  );
}

// A partner Item: click glides to it, hover or focus previews it on the map.
function ItemButton({ item, onSelect, onPreview }: Pick<Props, "item" | "onSelect" | "onPreview">) {
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
