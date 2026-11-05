import { ArrowLeftIcon, XIcon } from "lucide-react";
import { forwardRef, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { day, kindName, noun, projectUses, relName, type GNode, type GOverlap, type Model, type UsageWindow } from "@/graph/model";

type Props = { model: Model; item: GNode; onSelect: (n: GNode) => void; onPreview: (n: GNode | null) => void; onClose: () => void; backTo?: string }; // backTo: the focused cluster's name, when the sheet replaces its card (narrow screens)

// Non-modal on purpose: the map stays live beside it. A side panel on desktop, a bottom sheet on phones.
export const Inspector = forwardRef<HTMLElement, Props>(function Inspector({ model, item, onSelect, onPreview, onClose, backTo }, ref) {
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
        {backTo && <Button variant="ghost" className="-mx-2 mb-1 h-10 max-w-[calc(100%-3rem)] justify-start gap-2 px-2 text-[13px] text-text-2" onClick={onClose}><ArrowLeftIcon aria-hidden /><span className="truncate">Back to {backTo}</span></Button>}
        <p className="flex min-h-7 items-center gap-2 pr-10 text-xs font-medium tracking-[0.02em] text-text-3">
          <span className="glyph" data-kind={item.kind} />
          {kindName(item.kind)}
        </p>
        <h2 id="i-name" tabIndex={-1} className="mt-2 mb-1 font-serif text-[26px] leading-[1.1] tracking-[-0.01em] [overflow-wrap:anywhere] outline-none sm:text-[30px]">
          {item.name}
        </h2>
        {item.label && <p className="text-[15px] leading-[1.45] tracking-[-0.005em] text-text-2">{item.label}</p>}

        <dl className="mt-6 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 border-t pt-4 text-[13px]">
          <dt className="text-text-3">Scope</dt>
          <dd>{item.scope === "project" ? (item.project && model.projects[item.project]) ? `Project: ${model.projects[item.project]}` : "Project" : "Global"}</dd>
          <dt className="text-text-3">Cluster</dt>
          <dd className="font-serif text-[17px] leading-tight tracking-[0.01em] italic">{item.cluster?.name ?? "Not clustered"}</dd>
        </dl>

        <Cost item={item} />
        <Usage item={item} window={model.usageWindow} model={model} />

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

const plain = (v: number | null) => (v == null ? <i className="text-text-3">unknown</i> : <>{v.toLocaleString()} tokens</>);

// Unknown (null or no entry) is said out loud, never shown as 0. Hooks have no static output; on-use needs --count-bodies.
function Cost({ item }: { item: GNode }) {
  const c = item.cost, hook = item.kind === "hook";
  return (
    <section className="mt-6" aria-label="Context cost">
      <h3 className="mb-2 text-xs font-medium tracking-[0.02em] text-text-3">Context cost</h3>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 rounded-lg border bg-surface-2 px-4 py-3 text-[13px]">
        <dt className="text-text-3">Always-on</dt>
        <dd className="text-right font-mono tabular-nums">{plain(c?.always_on ?? null)}</dd>
        <dt className="text-text-3">On use</dt>
        <dd className="text-right font-mono tabular-nums">{plain(c?.on_use ?? null)}</dd>
      </dl>
      {hook ? (
        <p className="mt-2 text-xs text-text-3">Hook output is only known when it runs.</p>
      ) : (
        c?.on_use == null && <p className="mt-2 text-xs text-text-3">Run <code className="font-mono">constellation scan --count-bodies</code> to measure.</p>
      )}
    </section>
  );
}

// No usage entry means the kind is not tracked (hooks, plugins): said as such, never as 0. Count 0 is "never seen" in the window scanned.
// A prompt-time hook also shows what it injects at session start: bytes are static, tokens only after --count-bodies, unknown never 0.
function Usage({ item, window, model }: { item: GNode; window: UsageWindow | null; model: Model }) {
  const u = item.usage, w = item.weight, where = projectUses(item, model);
  if (!u && !w && !(item.kind === "hook" || item.kind === "plugin")) return null;
  const seen = !u ? null : u.count > 0
    ? <>{noun(u.count, "use")}{u.last_used && <span className="text-text-3"> · last {day(u.last_used)}</span>}</>
    : window?.files ? <span className="text-text-2">Never seen in the {noun(window.files, "transcript")} scanned</span> : <i className="text-text-3">no transcripts scanned</i>;
  return (
    <section className="mt-6" aria-label="Usage">
      <h3 className="mb-2 text-xs font-medium tracking-[0.02em] text-text-3">Usage</h3>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 rounded-lg border bg-surface-2 px-4 py-3 text-[13px]">
        <dt className="text-text-3">Seen in transcripts</dt>
        <dd className="text-right">{seen ?? <i className="text-text-3">not tracked</i>}</dd>
        {where && <>
          <dt className="text-text-3">By project</dt>
          <dd className="text-right">{where.map((r) => <span key={r.label} className="block [overflow-wrap:anywhere]">{noun(r.count, "use")} in {r.label}{r.current && <span className="text-text-3"> (this repo)</span>}</span>)}</dd>
        </>}
        {w && <>
          <dt className="text-text-3">Session-start weight</dt>
          <dd className="text-right font-mono tabular-nums">
            {w.bytes == null ? <i className="font-sans text-text-3">unknown</i> : `${w.bytes.toLocaleString()} bytes`}
            {w.tokens != null ? <span className="block">{w.tokens.toLocaleString()} tokens</span> : w.bytes != null && <i className="block font-sans text-text-3">tokens not counted</i>}
          </dd>
        </>}
      </dl>
      {window?.first && window.last && u && <p className="mt-2 text-xs text-text-3">Transcripts from {day(window.first)} to {day(window.last)}.</p>}
    </section>
  );
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
