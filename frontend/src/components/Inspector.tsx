import { ArrowLeftIcon, XIcon } from "lucide-react";
import { forwardRef, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { withContents, type GNode, type Model } from "@/graph/model";
import { verdictOf } from "@/lib/verdict";
import { About } from "./inspector/About";
import { Facts } from "./inspector/Facts";
import { Header } from "./inspector/Header";
import { KindDetails } from "./inspector/KindDetails";
import { Related } from "./inspector/Related";
import { VerdictBanner } from "./inspector/Verdict";

type Props = { model: Model; item: GNode; onSelect: (n: GNode) => void; onPreview: (n: GNode | null) => void; onClose: () => void; backTo?: string; whatIf?: ReadonlySet<GNode> | null; removed?: ReadonlySet<GNode> | null; onToggle?: (n: GNode) => void }; // backTo: the focused cluster's name, when the sheet replaces its card (narrow screens)

// Non-modal on purpose: the map stays live beside it. A side panel on desktop, a bottom sheet on phones.
export const Inspector = forwardRef<HTMLElement, Props>(function Inspector({ model, item, onSelect, onPreview, onClose, backTo, whatIf = null, removed = null, onToggle }, ref) {
  const scroll = useRef<HTMLDivElement>(null);
  useEffect(() => {
    scroll.current?.scrollTo({ top: 0 });
  }, [item]);

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

        <About item={item} />
        <KindDetails item={item} model={model} />
        <Related key={item.id} item={item} model={model} onSelect={onSelect} onPreview={onPreview} />
        {whatIf && onToggle && <WhatIfToggle model={model} item={item} whatIf={whatIf} removed={removed} onToggle={onToggle} />}
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
