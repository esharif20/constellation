import { CheckIcon, CopyIcon, ListPlusIcon, PlusIcon, TriangleAlertIcon, XIcon } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type CSSProperties, type RefObject } from "react";
import { Button } from "@/components/ui/button";
import { Preview } from "@/components/Preview";
import { HookSafety } from "@/components/HookSafety";
import { Conflicts } from "@/components/Conflicts";
import { Receipt } from "@/components/Receipt";
import { Triggers } from "@/components/Triggers";
import { Weekly } from "@/components/Weekly";
import { useLenses } from "@/components/useLenses";
import { Separator } from "@/components/ui/separator";
import { budget, kindName, type Assessment, type Budget, type BriefData, type BriefRow, type Checklist, type GNode, type Model } from "@/graph/model";
import { instructionFor } from "@/lib/instruction";
import { verdictOf } from "@/lib/verdict";

type Props = {
  data: BriefData;
  model: Model;
  assessments?: Record<string, Assessment>;
  open: boolean;
  hidden: boolean;
  footerInset?: number;
  pill: RefObject<HTMLButtonElement | null>;
  onOpen: (open: boolean) => void;
  onItem: (id: string) => void;
  onPair: (row: BriefRow) => void;
  whatIf?: ReadonlySet<GNode> | null; // what-if: the ticked Items (null = off)
  removed?: ReadonlySet<GNode> | null; // the ticks plus what they contain
  onWhatIf?: (on: boolean) => void;
  onToggle?: (n: GNode) => void;
  onReset?: () => void;
};

export function Brief({ data, model, assessments, open, hidden, footerInset = 0, pill, onOpen, onItem, onPair, whatIf = null, removed = null, onWhatIf, onToggle, onReset }: Props) {
  const [checklist, setChecklist] = useState(data.checklist);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [announcement, setAnnouncement] = useState("");
  const [bottom, setBottom] = useState(96);
  const busy = useRef(false);
  const lenses = useLenses();
  const byId = new Map(model.nodes.map((n) => [n.id, n]));
  const added = new Set(checklist?.ids ?? []);
  const meter = useMemo(() => budget(model.nodes, removed ?? undefined), [model.nodes, removed]);
  const [copied, setCopied] = useState<"" | "done" | "failed">("");
  const actionable = data.safe.rows.length + data.look.rows.length;

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

  async function addMany(list: BriefRow[]) {
    const todo = list.filter((r) => !added.has(r.id));
    if (busy.current || !todo.length) return;
    busy.current = true;
    setPending(todo[0].id);
    setError("");
    try {
      for (const row of todo) {
        setPending(row.id);
        const response = await fetch("api/checklist", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: row.id }) });
        const result = await response.json();
        if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : `Request failed (${response.status})`);
        setChecklist(result as Checklist);
      }
      setAnnouncement(todo.length === 1 ? `Added ${nameOf(todo[0])} to checklist` : `Added ${todo.length} Items to checklist`);
    } catch (e) {
      setError(`Could not write the checklist: ${e instanceof Error ? e.message : "Please try again."}`);
    } finally {
      busy.current = false;
      setPending(null);
    }
  }
  const add = (row: BriefRow) => addMany([row]);

  // One instruction per Item, each asking to see the change and wait for an OK; Constellation itself changes nothing.
  async function copyAll(list: BriefRow[]) {
    const lines = list.flatMap((row, i) => {
      const target = byId.get(row.removes ?? row.item_ids[0]);
      return target ? [`${i + 1}. ${instructionFor(target, model, verdictOf(target, assessments))}`] : [];
    });
    try { await navigator.clipboard.writeText(lines.join("\n")); setCopied("done"); setAnnouncement(`Copied ${lines.length} instructions`); } catch { setCopied("failed"); }
  }

  function rows(list: BriefRow[], canAdd = true) {
    const maxSaves = Math.max(1, ...list.flatMap((r) => r.saves == null ? [] : [r.saves]));
    return <ul className="-mx-2 mt-2 flex flex-col gap-1">
      {list.map((row) => {
        const name = nameOf(row), pair = row.item_ids.length > 1, isAdded = added.has(row.id);
        const item = byId.get(row.removes ?? row.item_ids[0]), target = item;
        const why = row.reasons?.[0]?.text ?? row.reason;
        return <li key={row.id} className="flex min-w-0 items-center gap-1">
          {whatIf && <label className="flex size-10 shrink-0 items-center justify-center" title={target ? undefined : "Unknown which one to keep: tick it in the Inspector"}>
            <input type="checkbox" className="size-4 accent-[var(--indigo-bright)]" disabled={!target} checked={!!target && whatIf.has(target)} aria-label={`Remove ${target?.name ?? name} in what-if`} onChange={() => target && onToggle?.(target)} />
          </label>}
          <Button variant="ghost" className="h-auto min-h-10 min-w-0 flex-1 justify-start gap-3 px-2 py-2 text-left font-normal whitespace-normal" onClick={() => pair ? onPair(row) : onItem(row.item_ids[0])}>
            {item && <span aria-hidden className="glyph" data-kind={item.kind} />}
            <span className="min-w-0 flex-1">
              <span className="block text-sm [overflow-wrap:anywhere]">{item?.name ?? name}</span>
              <span className="block text-xs leading-[1.4] text-text-3">{why}{row.confidence && <span className="text-text-2"> · {row.confidence} confidence</span>}</span>
              {row.saves != null && <span aria-hidden className="mt-1 block h-1 overflow-hidden rounded-full bg-line-1"><span className="block h-full rounded-full bg-indigo-bright/60" style={{ width: `${100 * row.saves / maxSaves}%` }} /></span>}
              {item && <span className="sr-only">{kindName(item.kind)}</span>}
            </span>
            <span className="shrink-0 text-right font-mono text-xs tabular-nums">{row.saves == null ? <i className="font-sans text-text-3">unknown</i> : `~${row.saves.toLocaleString()}`}<span className="sr-only"> tokens saved</span></span>
          </Button>
          {canAdd && checklist && <Button variant="ghost" size="icon-lg" disabled={isAdded || pending != null} aria-pressed={isAdded} aria-busy={pending === row.id} aria-label={isAdded ? `On checklist: ${name}` : `Add ${name} to cleanup checklist`} onClick={() => void add(row)}>
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
        <div className="flex items-center gap-1">
          {onWhatIf && <Button variant={whatIf ? "secondary" : "ghost"} className="h-10 px-3 text-[13px]" aria-pressed={!!whatIf} onClick={() => onWhatIf(!whatIf)}>What if…</Button>}
        <Button variant="ghost" size="icon-lg" aria-label="Collapse cleanup brief" onClick={() => { onOpen(false); requestAnimationFrame(() => pill.current?.focus()); }}><XIcon aria-hidden /></Button>
        </div>
      </div>
      <div className="flex flex-col gap-6 overflow-y-auto overscroll-contain px-4 pt-3 pb-[max(24px,env(safe-area-inset-bottom))] sm:px-6">
        {data.weekly && <><Weekly data={data.weekly} /><Separator /></>}
        <Preview onItem={onItem} />
        {!actionable && !data.wait.rows.length && <p className="text-[13px] leading-[1.4] text-text-2">Nothing to clean up yet. Run <code className="font-mono text-xs">constellation scan</code> with a key to measure cost.</p>}
        {meter.measured && actionable > 0 && <Meter b={meter} whatIf={!!whatIf} onReset={onReset} onExit={() => onWhatIf?.(false)} />}
        {data.range.high > 0 && <Headline range={data.range} evidence={data.evidence} />}
        {data.safe.rows.length > 0 && <div>
          <h3 className="text-sm font-medium">Safe wins</h3>
          <p className="mt-1 text-xs leading-[1.4] text-text-3">Not used, or doing the same job as something you use, and we are confident. {data.safe.saves != null && `Removing these ${data.safe.rows.length} frees ~${data.safe.saves.toLocaleString()} tokens per session (estimate).`}</p>
          {rows(data.safe.rows)}
          <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
            <Button variant="outline" className="h-11 gap-2 px-3 text-[13px] font-normal sm:h-10" onClick={() => void copyAll(data.safe.rows)}>{copied === "done" ? <CheckIcon aria-hidden /> : <CopyIcon aria-hidden />}{copied === "done" ? "Copied" : "Copy instruction for all safe wins"}</Button>
            {checklist && <Button variant="outline" className="h-11 gap-2 px-3 text-[13px] font-normal sm:h-10" disabled={pending != null || data.safe.rows.every((r) => added.has(r.id))} onClick={() => void addMany(data.safe.rows)}><ListPlusIcon aria-hidden />{data.safe.rows.every((r) => added.has(r.id)) ? "All on checklist" : "Add all to checklist"}</Button>}
          </div>
          {copied === "failed" && <p role="alert" className="mt-2 text-xs text-warn">Could not copy. Select the Items and copy by hand.</p>}
        </div>}
        {data.look.rows.length > 0 && <div>
          <h3 className="text-sm font-medium">Worth a look</h3>
          <p className="mt-1 text-xs leading-[1.4] text-text-3">Probably fine to change, but check first.{data.look.saves != null && ` Up to ~${data.look.saves.toLocaleString()} tokens.`}{!!data.look.unknown && <span className="mt-1 block">+ {data.look.unknown} with unknown cost, not counted</span>}</p>
          {rows(data.look.rows)}
        </div>}
        {(data.wait.summary.length > 0 || data.wait.rows.length > 0) && <Wait wait={data.wait} byId={byId} onItem={onItem} />}
        {(actionable > 0 || data.wait.rows.length > 0) && <Separator />}
        {!!data.scope?.rows.length && <>
          <div>
            <h3 className="text-sm font-medium">Scope</h3>
            <p className="mt-1 text-xs leading-[1.4] text-text-3">Global Items that one project uses almost alone.</p>
            <ul className="-mx-2 mt-2 flex flex-col gap-1">
              {data.scope.rows.map((row) => {
                const item = byId.get(row.item_ids[0]);
                return <li key={row.id}>
                  <Button variant="ghost" className="h-auto min-h-10 w-full min-w-0 justify-start gap-3 px-2 py-2 text-left font-normal whitespace-normal" title={row.reason} onClick={() => onItem(row.item_ids[0])}>
                    {item && <span aria-hidden className="glyph" data-kind={item.kind} />}
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm [overflow-wrap:anywhere]">{item?.name ?? row.item_ids[0]}</span>
                      <span className="block text-xs text-text-3">Move to {row.project_label ?? "one project"} · {row.confidence ?? "medium"} confidence</span>
                    </span>
                    <span className="shrink-0 text-right font-mono text-xs tabular-nums">{row.tokens_saved == null ? <i className="font-sans text-text-3">unknown</i> : `~${row.tokens_saved.toLocaleString()}`}<span className="sr-only"> tokens saved</span></span>
                  </Button>
                </li>;
              })}
            </ul>
            <p className="mt-2 text-xs leading-[1.4] text-text-3">{data.scope.caveat}</p>
          </div>
          <Separator />
        </>}
        {lenses && <><Separator /><Receipt data={lenses.receipt} onItem={onItem} /></>}
        {lenses?.hooks && <><Separator /><HookSafety rows={lenses.hooks} onItem={onItem} /></>}
        {lenses?.triggers && <><Separator /><Triggers data={lenses.triggers} onItem={onItem} /></>}
        {lenses?.conflicts && <><Separator /><Conflicts rows={lenses.conflicts} nodes={model.nodes} onItem={onItem} /></>}
        {checklist && checklist.ids.length > 0 && <footer className="flex flex-col gap-2 text-xs leading-[1.4] text-text-2">
          <Separator />
          <p>{checklist.ids.length} on your checklist · {checklist.frees == null ? "saving not measured" : `frees ~${checklist.frees.toLocaleString()} tokens (estimate)`}</p>
          {checklist.unknown_rows > 0 && <p className="text-text-3">+ {checklist.unknown_rows} with unknown cost, not counted</p>}
          <p className="font-mono text-text-3 [overflow-wrap:anywhere]">{checklist.path}</p>
          <p>Nothing in your setup was changed.</p>
        </footer>}
        {error && <p role="alert" className="flex items-start gap-2 text-xs leading-[1.4] text-warn"><TriangleAlertIcon aria-hidden className="size-4 shrink-0" />{error}</p>}
      </div>
    </section> : <Button ref={pill} variant="outline" className="glass fixed right-4 bottom-24 h-10 gap-2 rounded-full px-4 sm:top-[76px] sm:right-auto sm:bottom-auto sm:left-4" aria-expanded={false} onClick={() => onOpen(true)}>{whatIf ? <>What-if <span className="font-mono text-xs tabular-nums">−{fmt(meter.saved)}</span></> : <>Cleanup brief <span className="font-mono text-xs tabular-nums">{actionable}</span></>}</Button>)}
    <p className="sr-only" aria-live="polite">{announcement}</p>
  </>;
}

const WAIT: Record<string, string> = { too_early: "not enough history yet", keep_rare: "made for occasional work, too early to tell", untracked: "cannot be measured from your history", low_confidence: "not sure enough to suggest" };
const dash = (c: number) => c.toLocaleString();

function Headline({ range, evidence }: { range: BriefData["range"]; evidence: BriefData["evidence"] }) {
  const span = range.low === range.high ? dash(range.low) : `${dash(range.low)} to ${dash(range.high)}`;
  return <div>
    <p className="text-[13px] leading-[1.45]">You could free <b className="font-mono font-medium tabular-nums">{span}</b> tokens at the start of every session (estimate).</p>
    {range.per_day && <p className="mt-1 text-xs leading-[1.4] text-text-2">About {dash(range.per_day[0])} to {dash(range.per_day[1])} a day at your pace.</p>}
    {range.unknown > 0 && <p className="mt-1 text-xs leading-[1.4] text-text-3">+ {range.unknown} with unknown cost, not counted</p>}
    {evidence && <p className="mt-1 text-xs leading-[1.4] text-text-3">Based on {evidence.sessions} sessions over {evidence.active_days} days you used Claude Code.{evidence.ledger === false && " Claude Code keeps transcripts for 30 days by default; Constellation keeps counts across scans, so verdicts sharpen as you rescan."}</p>}
  </div>;
}

function Wait({ wait, byId, onItem }: { wait: BriefData["wait"]; byId: Map<string, GNode>; onItem: (id: string) => void }) {
  return <div>
    <h3 className="text-sm font-medium">Don&apos;t touch yet</h3>
    <ul className="mt-1 list-disc pl-4 text-xs leading-[1.45] text-text-3">
      {wait.summary.map((w) => <li key={w.code}>{w.count} {w.count === 1 ? "Item" : "Items"}: {WAIT[w.code] ?? w.code.replace(/_/g, " ")}{w.recheck_after ? `; check back after about ${w.recheck_after} more active days` : ""}.</li>)}
    </ul>
    {wait.rows.length > 0 && <details className="mt-1">
      <summary className="flex h-10 cursor-pointer items-center text-xs text-text-2">Show which ({wait.rows.length})</summary>
      <ul className="-mx-2 flex flex-col gap-1">
        {wait.rows.map((row) => {
          const item = byId.get(row.item_ids[0]);
          return <li key={row.id}><Button variant="ghost" className="h-auto min-h-10 w-full min-w-0 justify-start gap-3 px-2 py-2 text-left font-normal whitespace-normal" onClick={() => onItem(row.item_ids[0])}>
            {item && <span aria-hidden className="glyph" data-kind={item.kind} />}
            <span className="min-w-0 flex-1"><span className="block text-sm [overflow-wrap:anywhere]">{item?.name ?? row.item_ids[0]}</span><span className="block text-xs leading-[1.4] text-text-3">{row.reasons?.[0]?.text ?? row.reason}</span></span>
          </Button></li>;
        })}
      </ul>
    </details>}
  </div>;
}

const fmt = (n: number) => n.toLocaleString();
function Meter({ b, whatIf, onReset, onExit }: { b: Budget; whatIf: boolean; onReset?: () => void; onExit: () => void }) {
  const before = b.known + b.saved, w = (n: number) => `${100 * n / (before || 1)}%`;
  return <div>
    <div className="flex flex-wrap items-baseline gap-x-2">
      <span className="text-xs text-text-3">Session start</span>
      <span className="font-mono text-xl tabular-nums sm:text-2xl">{whatIf ? <>{fmt(before)} → {fmt(b.known)}</> : fmt(b.known)}</span>
      <span className="text-xs text-text-3">tokens before your first prompt</span>
    </div>
    {whatIf && <p className="mt-1 text-xs font-medium text-indigo-bright">−{fmt(b.saved)} ({Math.round(100 * b.saved / (before || 1))}%)</p>}
    <div role="img" aria-label={`Items ${fmt(b.items)} tokens, hooks ${fmt(b.hooks)} tokens${whatIf ? `, removed ${fmt(b.saved)} tokens` : ""}`} className="mt-2 flex h-2 gap-0.5 overflow-hidden rounded-full bg-line-1">
      <span className="bg-indigo-bright/70" style={{ width: w(b.items) }} />
      {b.hooks > 0 && <span className="bg-indigo-bright/35" style={{ width: w(b.hooks) }} />}
      {whatIf && b.saved > 0 && <span className="rounded-full border border-dashed border-indigo-bright" style={{ width: w(b.saved) }} />}
    </div>
    <p className="mt-2 flex flex-wrap gap-x-3 text-xs text-text-3">
      <span className="flex items-center gap-1.5"><i aria-hidden className="size-2 rounded-full bg-indigo-bright/70" />Items {fmt(b.items)}</span>
      {b.hooks > 0 && <span className="flex items-center gap-1.5"><i aria-hidden className="size-2 rounded-full bg-[repeating-linear-gradient(45deg,var(--indigo-bright)_0_2px,transparent_2px_4px)]" />Hooks {fmt(b.hooks)}</span>}
      {whatIf && <span className="flex items-center gap-1.5"><i aria-hidden className="size-2 rounded-full border border-dashed border-indigo-bright" />Removed {fmt(b.saved)}</span>}
    </p>
    {whatIf && <p className="mt-1 text-xs text-text-2">{b.removed} removed{b.removedUnknown > 0 && ` · ${b.removedUnknown} with unknown cost, not counted`}</p>}
    {b.unknown > 0 && <p className="mt-1 text-xs text-text-3">{b.unknown} with unknown cost, not counted</p>}
    {whatIf && <div className="mt-2 flex gap-2">
      <Button variant="outline" className="h-10" onClick={onReset}>Reset</Button>
      <Button variant="ghost" className="h-10" onClick={onExit}>Exit what-if</Button>
    </div>}
  </div>;
}
