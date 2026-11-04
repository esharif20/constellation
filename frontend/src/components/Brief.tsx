import { CheckIcon, PlusIcon, TriangleAlertIcon, XIcon } from "lucide-react";
import { useEffect, useRef, useState, type CSSProperties, type RefObject } from "react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { kindName, type BriefData, type BriefGroup, type BriefRow, type Checklist, type Model } from "@/graph/model";
import { cn } from "@/lib/utils";

type Props = {
  data: BriefData;
  model: Model;
  open: boolean;
  hidden: boolean;
  footerInset?: number;
  pill: RefObject<HTMLButtonElement | null>;
  onOpen: (open: boolean) => void;
  onItem: (id: string) => void;
  onPair: (row: BriefRow) => void;
};

export function Brief({ data, model, open, hidden, footerInset = 0, pill, onOpen, onItem, onPair }: Props) {
  const [checklist, setChecklist] = useState(data.checklist);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [announcement, setAnnouncement] = useState("");
  const [bottom, setBottom] = useState(96);
  const busy = useRef(false);
  const byId = new Map(model.nodes.map((n) => [n.id, n]));
  const added = new Set(checklist?.ids ?? []);
  const maxCost = Math.max(1, ...data.cost.rows.flatMap((row) => row.tokens_saved == null ? [] : [row.tokens_saved]));

  useEffect(() => {
    const legend = document.querySelector('ul[aria-label="Legend"]');
    if (!legend) return;
    const measure = () => setBottom(innerHeight - legend.getBoundingClientRect().top + 8);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(legend);
    addEventListener("resize", measure);
    return () => { observer.disconnect(); removeEventListener("resize", measure); };
  }, []);

  const nameOf = (row: BriefRow) => row.item_ids.map((id) => byId.get(id)?.name ?? id).join(row.kind === "use_underlying" ? " wraps " : " and ");

  async function add(row: BriefRow) {
    if (busy.current || added.has(row.id)) return;
    busy.current = true;
    setPending(row.id);
    setError("");
    try {
      const response = await fetch("api/checklist", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: row.id }) });
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : `Request failed (${response.status})`);
      setChecklist(result as Checklist);
      setAnnouncement(`Added ${nameOf(row)} to checklist`);
    } catch (e) {
      setError(`Could not write the checklist: ${e instanceof Error ? e.message : "Please try again."}`);
    } finally {
      busy.current = false;
      setPending(null);
    }
  }

  function rows(group: BriefGroup) {
    return <ul className="-mx-2 mt-2 flex flex-col gap-1">
      {group.rows.map((row) => {
        const item = byId.get(row.item_ids[0]), name = nameOf(row), pair = row.kind !== "review_cost", isAdded = added.has(row.id);
        return <li key={row.id} className="flex min-w-0 items-center gap-1">
          <Button variant="ghost" className="h-auto min-h-10 min-w-0 flex-1 justify-start gap-3 px-2 py-2 text-left font-normal whitespace-normal" title={row.reason} onClick={() => pair ? onPair(row) : onItem(row.item_ids[0])}>
            {item && <span aria-hidden className="glyph" data-kind={item.kind} />}
            <span className="min-w-0 flex-1">
              <span className={cn("block text-sm", pair ? "[overflow-wrap:anywhere]" : "truncate")}>{name}</span>
              {!pair && row.tokens_saved != null && <span aria-hidden className="mt-1 block h-1 overflow-hidden rounded-full bg-line-1"><span className="block h-full rounded-full bg-indigo-bright/60" style={{ width: `${100 * row.tokens_saved / maxCost}%` }} /></span>}
              {pair && <span className="block text-xs text-text-3">{row.kind === "use_underlying" ? "wrapper" : "duplicate"}</span>}
              {!pair && item && <span className="sr-only">{kindName(item.kind)}</span>}
            </span>
            <span className="shrink-0 text-right font-mono text-xs tabular-nums" style={pair ? undefined : { minWidth: `${maxCost.toLocaleString().length}ch` }}>{row.tokens_saved == null ? <i className="font-sans text-text-3">unknown</i> : `${pair ? "~" : ""}${row.tokens_saved.toLocaleString()}`}<span className="sr-only"> tokens{pair ? " saved" : " always on"}</span></span>
          </Button>
          {checklist && <Button variant="ghost" size="icon-lg" disabled={isAdded || pending != null} aria-pressed={isAdded} aria-busy={pending === row.id} aria-label={isAdded ? `On checklist: ${name}` : `Add ${name} to cleanup checklist`} onClick={() => void add(row)}>
            {isAdded ? <CheckIcon aria-hidden /> : <PlusIcon aria-hidden />}
          </Button>}
        </li>;
      })}
    </ul>;
  }

  return <>
    {!hidden && (open ? <section
      aria-labelledby="brief-title"
      style={{ "--brief-bottom": `${bottom + footerInset}px` } as CSSProperties}
      className="glass fixed inset-x-0 bottom-0 flex max-h-[46dvh] animate-sheet-in flex-col rounded-t-2xl border border-b-0 shadow-(--shadow-float) sm:inset-x-auto sm:top-[76px] sm:bottom-auto sm:left-4 sm:max-h-[calc(100dvh-76px-var(--brief-bottom))] sm:w-[340px] sm:animate-panel-in sm:rounded-xl sm:border-b"
      onKeyDown={(e) => { if (e.key === "Escape") { e.preventDefault(); onOpen(false); requestAnimationFrame(() => pill.current?.focus()); } }}
    >
      <div aria-hidden className="mx-auto mt-2 h-1 w-9 shrink-0 rounded-full bg-line-2 sm:hidden" />
      <div className="flex shrink-0 items-center justify-between gap-2 px-4 pt-3 sm:px-6 sm:pt-4">
        <h2 id="brief-title" className="text-xs font-medium tracking-[0.02em] text-text-3">Where your context goes</h2>
        <Button variant="ghost" size="icon-lg" aria-label="Collapse cleanup brief" onClick={() => { onOpen(false); requestAnimationFrame(() => pill.current?.focus()); }}><XIcon aria-hidden /></Button>
      </div>
      <div className="flex flex-col gap-6 overflow-y-auto overscroll-contain px-4 pt-3 pb-[max(24px,env(safe-area-inset-bottom))] sm:px-6">
        {!data.cost.rows.length && !data.pairs.rows.length && <p className="text-[13px] leading-[1.4] text-text-2">Nothing to rank yet. Run <code className="font-mono text-xs">constellation scan</code> with a key to measure cost.</p>}
        <div>
          <h3 className="text-sm font-medium">Most expensive, always on</h3>
          {data.cost.measured ? <Counter group={data.cost} /> : <p className="mt-1 text-xs text-text-3 italic">Cost was not measured in this scan.</p>}
          {rows(data.cost)}
          {data.cost.unknown > 0 && <p className="mt-2 text-xs leading-[1.4] text-text-3">{data.cost.unknown} Items with unknown cost are not ranked.</p>}
        </div>
        <Separator />
        <div>
          <h3 className="text-sm font-medium">Duplicates and wrappers</h3>
          {data.pairs.rows.length ? <><Counter group={data.pairs} />{rows(data.pairs)}</> : <p className="mt-2 text-[13px] leading-[1.4] text-text-2">No duplicates or wrappers found.</p>}
        </div>
        {checklist && checklist.ids.length > 0 && <footer className="flex flex-col gap-2 text-xs leading-[1.4] text-text-2">
          <Separator />
          <p>{checklist.ids.length} on your checklist · {checklist.frees == null ? "saving not measured" : `frees ~${checklist.frees.toLocaleString()} tokens (estimate)`}</p>
          {checklist.unknown_rows > 0 && <p className="text-text-3">+ {checklist.unknown_rows} with unknown cost, not counted</p>}
          <p className="font-mono text-text-3 [overflow-wrap:anywhere]">{checklist.path}</p>
          <p>Nothing in your setup was changed.</p>
        </footer>}
        {error && <p role="alert" className="flex items-start gap-2 text-xs leading-[1.4] text-warn"><TriangleAlertIcon aria-hidden className="size-4 shrink-0" />{error}</p>}
      </div>
    </section> : <Button ref={pill} variant="outline" className="glass fixed right-4 bottom-24 h-10 gap-2 rounded-full px-4 sm:top-[76px] sm:right-auto sm:bottom-auto sm:left-4" aria-expanded={false} onClick={() => onOpen(true)}>Cleanup brief <span className="font-mono text-xs tabular-nums">{data.pairs.rows.length}</span></Button>)}
    <p className="sr-only" aria-live="polite">{announcement}</p>
  </>;
}

function Counter({ group }: { group: BriefGroup }) {
  return <p className="mt-1 text-xs leading-[1.4] text-text-3">
    {group.frees == null ? "Saving not measured" : `Removing these ${group.rows.length} frees ~${group.frees.toLocaleString()} tokens per session (estimate)`}
    {group.unknown_rows > 0 && <span className="mt-1 block">+ {group.unknown_rows} with unknown cost, not counted</span>}
  </p>;
}
