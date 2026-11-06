import { ArrowLeftIcon, OrbitIcon, XIcon } from "lucide-react";
import { Pane } from "@/components/Motion";
import { forwardRef, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { withContents, type Assessment, type BriefData, type Habits, type Cluster, type GNode, type Model } from "@/graph/model";
import { richInstruction } from "@/lib/instruction";
import { verdictOf } from "@/lib/verdict";
import { nextStep } from "@/lib/yours";
import { Actions, briefRow } from "./inspector/Actions";
import { About } from "./inspector/About";
import { Facts } from "./inspector/Facts";
import { Header } from "./inspector/Header";
import { KindDetails } from "./inspector/KindDetails";
import { Related } from "./inspector/Related";
import { RemovalPreview } from "./inspector/Removal";
import { ToolsSection } from "./inspector/Tools";
import { WhatFor, Yours } from "./inspector/Yours";
import { VerdictBanner } from "./inspector/Verdict";

type Props = { model: Model; item: GNode; onSelect: (n: GNode) => void; onPreview: (n: GNode | null) => void; onClose: () => void; backTo?: string; whatIf?: ReadonlySet<GNode> | null; removed?: ReadonlySet<GNode> | null; onToggle?: (n: GNode) => void; brief?: BriefData; assessments?: Record<string, Assessment>; habits?: Habits | null; onFind?: (name: string) => void; onAsk?: (text: string) => void; onCluster?: (c: Cluster) => void }; // backTo: the focused cluster's name, when the sheet replaces its card (narrow screens)

// Non-modal on purpose: the map stays live beside it. A side panel on desktop, a bottom sheet on phones.
export const Inspector = forwardRef<HTMLElement, Props>(function Inspector({ model, item, onSelect, onPreview, onClose, backTo, whatIf = null, removed = null, onToggle, brief, assessments, habits = null, onFind, onAsk, onCluster }, ref) {
  const scroll = useRef<HTMLDivElement>(null);
  const fade = useRef<HTMLDivElement>(null); // toggled by hand: a state here re-rendered the panel on every scroll
  useEffect(() => {
    scroll.current?.scrollTo({ top: 0 });
  }, [item]);

  const verdict = verdictOf(item, assessments ?? model.assessments);
  const habit = habits?.items[item.id];
  const first = model.overlapsOf.get(item)?.[0], twinId = verdict.twin ?? (first && (first.a === item ? first.b : first.a).id);
  const twin = twinId ? model.nodes.find((n) => n.id === twinId) : undefined;
  const next = nextStep(verdict.action, verdict.tier, !!brief?.checklist && !!briefRow(brief, item), !!habit?.pinned);
  return (
    <Pane
      as="aside" from="right"
      ref={ref}
      aria-labelledby="i-name"
      className="glass fixed inset-x-0 bottom-0 flex max-h-[58dvh] flex-col rounded-t-2xl border border-b-0 shadow-(--shadow-float) sm:inset-x-auto sm:top-[76px] sm:right-4 sm:bottom-4 sm:max-h-none sm:w-[380px] sm:rounded-xl sm:border-b"
    >
      <div aria-hidden className="mx-auto mt-2 h-1 w-9 rounded-full bg-line-2 sm:hidden" />
      <div ref={fade} aria-hidden className="pointer-events-none absolute inset-x-0 top-0 h-14 rounded-t-xl bg-linear-to-b from-card from-60% to-transparent opacity-0 transition-opacity duration-(--t)" />
      <Button variant="ghost" size="icon-lg" onClick={onClose} aria-label="Close inspector" className="absolute top-3 right-3 rounded-md text-text-3 hover:text-foreground sm:top-2.5 sm:right-2.5">
        <XIcon />
      </Button>
      <div ref={scroll} onScroll={(e) => { if (fade.current) fade.current.style.opacity = e.currentTarget.scrollTop > 8 ? "1" : "0"; }} className="overflow-y-auto overscroll-contain px-4 pt-3 pb-6 sm:px-6 sm:pt-6">
        {backTo && <Button variant="ghost" className="-mx-2 mb-1 h-10 max-w-[calc(100%-3rem)] justify-start gap-2 px-2 text-[13px] text-text-2" onClick={onClose}><ArrowLeftIcon aria-hidden /><span className="truncate">Back to {backTo}</span></Button>}
        <Header item={item} model={model} />
        <WhatFor item={item} model={model} />
        <VerdictBanner verdict={verdict} item={item} model={model} />
        <Yours key={item.id} item={item} model={model} habits={habits} twin={twin} />
        <Facts model={model} item={item} onSelect={onSelect} onPreview={onPreview} />

        <About item={item} />
        <KindDetails item={item} model={model} />
        <ToolsSection key={item.id} item={item} />
        <RemovalPreview key={item.id} item={item} model={model} onSelect={onSelect} listed={new Set((model.overlapsOf.get(item) ?? []).map((o) => (o.a === item ? o.b : o.a).id))} />
        <Related key={item.id} item={item} model={model} onSelect={onSelect} onPreview={onPreview} />
        {onCluster && item.cluster && <Button variant="ghost" className="-mx-2 mt-3 h-11 max-w-full justify-start gap-2 px-2 text-[13px] text-text-2 sm:h-10" onClick={() => onCluster(item.cluster!)}><OrbitIcon aria-hidden /><span className="truncate">Fly to {item.cluster.name}</span></Button>}
        {whatIf && onToggle && <WhatIfToggle model={model} item={item} whatIf={whatIf} removed={removed} onToggle={onToggle} />}
      </div>
      <footer className="shrink-0 border-t border-line-1 px-4 pt-2 pb-[max(8px,env(safe-area-inset-bottom))] sm:px-6 sm:pt-3 sm:pb-4">
        <Actions key={item.id} item={item} instruction={richInstruction(item, model, verdict, { uses: item.usage?.count, activeDays: habits?.activeDays })} brief={brief} next={next} pinned={!!habit?.pinned} twin={twin} onSelect={onSelect} onFind={onFind} onAsk={onAsk} />
      </footer>
    </Pane>
  );
});

function WhatIfToggle({ model, item, whatIf, removed, onToggle }: { model: Model; item: GNode; whatIf: ReadonlySet<GNode>; removed: ReadonlySet<GNode> | null; onToggle: (n: GNode) => void }) {
  const ticked = whatIf.has(item), viaParent = !ticked && !!removed?.has(item), n = withContents(model, new Set([item])).size;
  return <div className="mt-4">
    <Button variant="outline" className="h-10" aria-pressed={ticked || viaParent} disabled={viaParent} onClick={() => onToggle(item)}>{viaParent ? "Removed with its plugin" : ticked ? "Put back" : "Remove in what-if"}</Button>
    {n > 1 && !ticked && <p className="mt-1 text-xs text-text-3">Removes {n} Items</p>}
  </div>;
}
