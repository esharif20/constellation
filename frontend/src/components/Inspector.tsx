import { XIcon } from "lucide-react";
import { forwardRef, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { kindName, relName, type GNode, type Model } from "@/graph/model";

type Props = { model: Model; item: GNode; onSelect: (n: GNode) => void; onPreview: (n: GNode | null) => void; onClose: () => void };

// null means not measured (an offline scan, or a count that failed): say so, never show 0
const tokens = (v: number | null) => (v == null ? "unknown" : v.toLocaleString());

// Non-modal on purpose: the map stays live beside it. A side panel on desktop, a bottom sheet on phones.
export const Inspector = forwardRef<HTMLElement, Props>(function Inspector({ model, item, onSelect, onPreview, onClose }, ref) {
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
        <p className="flex min-h-7 items-center gap-2 pr-10 text-xs font-medium tracking-[0.02em] text-text-3">
          <span className="glyph" data-kind={item.kind} />
          {kindName(item.kind)}
        </p>
        <h2 id="i-name" tabIndex={-1} className="mt-2 mb-1 font-serif text-[26px] leading-[1.1] tracking-[-0.01em] [overflow-wrap:anywhere] outline-none sm:text-[30px]">
          {item.name}
        </h2>
        {item.label && <p className="text-[15px] leading-[1.45] tracking-[-0.005em] text-text-2">{item.label}</p>}

        <dl className="mt-6 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 border-t pt-4 text-[13px]">
          <dt className="text-text-3">Cluster</dt>
          <dd className="font-serif text-[17px] leading-tight tracking-[0.01em] italic">{item.cluster?.name ?? "Not clustered"}</dd>
        </dl>

        {item.cost && (
          <div className="mt-6 grid grid-cols-2 gap-3" aria-label="Context cost">
            <Stat value={item.cost.always_on} unit="tokens every session" />
            <Stat value={item.cost.on_use} unit="tokens when used" />
          </div>
        )}

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
                  <Button
                    variant="ghost"
                    onClick={() => onSelect(o)}
                    onMouseEnter={() => onPreview(o)}
                    onMouseLeave={() => onPreview(null)}
                    onFocus={() => onPreview(o)}
                    onBlur={() => onPreview(null)}
                    className="h-auto min-h-10 w-full justify-start gap-3 rounded-md px-2 py-1 text-left text-sm font-normal text-foreground whitespace-normal"
                  >
                    <span className="glyph" data-kind={o.kind} />
                    <span className="[overflow-wrap:anywhere]">{o.name}</span>
                  </Button>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </aside>
  );
});

function Stat({ value, unit }: { value: number | null; unit: string }) {
  return (
    <div className="rounded-lg border bg-surface-2 px-4 py-3">
      <b className={value == null ? "block text-base font-normal text-text-3 italic" : "block font-mono text-xl leading-[1.2] font-normal tracking-[-0.01em] tabular-nums"}>{tokens(value)}</b>
      <span className="text-xs text-text-3">{unit}</span>
    </div>
  );
}
