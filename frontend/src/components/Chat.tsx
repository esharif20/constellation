import { RANK } from "@/lib/dismiss";
import { useLayer } from "@/lib/useLayer";
import { ArrowRightIcon, CheckIcon, CopyIcon, ListPlusIcon, MessageCircleIcon, RotateCcwIcon, SendIcon, TriangleAlertIcon, XIcon } from "lucide-react";
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { Pane, Presence } from "@/components/Motion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Kbd } from "@/components/ui/kbd";
import type { GNode, Model } from "@/graph/model";
import { cn } from "@/lib/utils";

export type ChatAction = { kind: "highlight" | "focus"; item_ids: string[] };
type Overlap = { with_id: string; with_name: string; verdict: string; reason: string };
type Verdict = { label: string; tone: "keep" | "review" | "remove" | "unknown"; why: string };
export type Handoff = { instruction: string; checklist_id: string | null };
type Card = { handoff: Handoff; id: string; name: string; kind: string; kind_label: string; what: string; always_on: string; on_use: string; usage: string; overlap: Overlap | null; verdict: Verdict };
type Row = { id: string; name: string; kind: string; what: string; value: string };
type Blocks = {
  headline: string; cards: Card[]; compare: { rows: { label: string; a: string; b: string }[]; same_cluster: boolean } | null; rows: Row[]; more: number;
  note: string | null; next: string | null; follow_ups: string[]; did_you_mean: { id: string; name: string; ask: string }[]; handoff: Handoff | null;
};
type Reply = { answer: string; blocks: Blocks | null; actions: ChatAction[]; mode: "local"; cached: boolean };
type Props = {
  model: Model;
  selected: GNode | null;
  open: boolean;
  onOpen: (open: boolean) => void;
  onActions: (actions: ChatAction[]) => void;
  onReset: () => void;
  onItem: (id: string) => void;
  draft?: { text: string; n: number }; // a question to put in the box without sending it (Inspector "Compare with…")
};

const UNAVAILABLE = "Local chat is unavailable here. Open this Constellation with a current local server to ask questions.";
const GLOSS: Record<string, string> = {
  "Every session": "Loaded into every conversation before you type.",
  "When used": "Extra cost only when Claude uses it.",
  tokens: "A token is about three quarters of a word.",
};
const TONE = { keep: "text-text-2", review: "text-warn", remove: "text-warn", unknown: "text-text-3" } as const;
const isUnknown = (v: string) => /^(unknown|Usage unknown|Cost unknown)$/.test(v);
const str = (v: unknown) => typeof v === "string";
const strs = (v: unknown) => Array.isArray(v) && v.every(str);

// Starter questions come from the loaded scan, so each one can be answered; a starter whose inputs are missing is left out.
export function starters(model: Model, selected: GNode | null): string[] {
  const out: string[] = [selected ? `Should I keep ${selected.name}?` : "What could I remove?", "What do I pay before I type anything?", "What costs the most every session?", "What have I not used in 30 days?"];
  const costed = model.nodes.filter((n) => n.cost?.always_on != null).sort((x, y) => y.cost!.always_on! - x.cost!.always_on!);
  const subject = selected ?? costed[0];
  if (subject) out.push(`What is ${subject.name}?`);
  const pair = ["duplicate", "wrapper", "overlap"].map((v) => model.overlaps.find((o) => o.verdict === v)).find(Boolean);
  if (pair) out.push(`Compare ${pair.a.name} and ${pair.b.name}`);
  const biggest = [...model.clusters].sort((x, y) => y.members.length - x.members.length)[0];
  if (out.length < 5 && biggest) out.push(`What do I have for ${biggest.name.toLowerCase()}?`);
  return out;
}

const handoffOk = (h: unknown) => !!h && typeof h === "object" && str((h as Handoff).instruction) && ((h as Handoff).checklist_id === null || str((h as Handoff).checklist_id));
const idOk = (known: Set<string>, v: unknown) => str(v) && known.has(v as string);

// Check every field and every id before rendering; a reply that fails shows its plain `answer` instead.
export function readBlocks(value: unknown, known: Set<string>): Blocks | null {
  const b = value as Blocks | null | undefined;
  if (!b || typeof b !== "object" || !str(b.headline) || !b.headline.trim()) return null;
  const card = (c: Card) => !!c && idOk(known, c.id) && [c.name, c.kind, c.kind_label, c.what, c.always_on, c.on_use, c.usage].every(str)
    && handoffOk(c.handoff) && !!c.verdict && ["label", "why"].every((k) => str((c.verdict as Record<string, unknown>)[k])) && c.verdict.tone in TONE
    && (c.overlap === null || (!!c.overlap && idOk(known, c.overlap.with_id) && str(c.overlap.with_name) && str(c.overlap.verdict) && str(c.overlap.reason)));
  const row = (r: Row) => !!r && idOk(known, r.id) && [r.name, r.kind, r.what, r.value].every(str);
  const ok = Array.isArray(b.cards) && b.cards.every(card) && Array.isArray(b.rows) && b.rows.every(row) && Number.isInteger(b.more)
    && (b.note === null || str(b.note)) && (b.next === null || str(b.next)) && strs(b.follow_ups) && (b.handoff === null || handoffOk(b.handoff))
    && Array.isArray(b.did_you_mean) && b.did_you_mean.every((d) => !!d && idOk(known, d.id) && str(d.name) && str(d.ask))
    && (b.compare === null || (!!b.compare && typeof b.compare.same_cluster === "boolean" && Array.isArray(b.compare.rows) && b.compare.rows.every((r) => [r.label, r.a, r.b].every(str)) && b.cards.length === 2));
  return ok ? b : null;
}

// Validate the whole reply before changing the map: the server can only refer to Items already in this Constellation.
function readReply(value: unknown, model: Model): Reply {
  if (!value || typeof value !== "object") throw new Error("Invalid local answer. Please try again.");
  const r = value as Partial<Reply>;
  const known = new Set(model.nodes.map((n) => n.id));
  if (typeof r.answer !== "string" || !r.answer.trim() || r.mode !== "local" || typeof r.cached !== "boolean" || !Array.isArray(r.actions) || r.actions.some((a) => !a || !["highlight", "focus"].includes(a.kind) || !Array.isArray(a.item_ids) || a.item_ids.some((id: unknown) => typeof id !== "string" || !known.has(id)))) {
    throw new Error("Invalid local answer. Please try again.");
  }
  return { ...(r as Reply), blocks: readBlocks(r.blocks, known) };
}

function Term({ id, term }: { id: string; term: string }) {
  return <>
    <span tabIndex={0} title={GLOSS[term]} aria-describedby={id} className="cursor-help rounded-xs underline decoration-dotted decoration-line-3 underline-offset-2 outline-offset-2 focus-visible:outline-2 focus-visible:outline-ring">{term}</span>
    <span id={id} className="sr-only">{GLOSS[term]}</span>
  </>;
}

function Value({ v }: { v: string }) {
  if (isUnknown(v)) return <span className="font-sans italic text-text-3">{v}</span>;
  const m = /^([\d,]+) (tokens.*)$/.exec(v);
  return m ? <span className="tabular-nums">{m[1]}<span className="font-sans text-text-3"> {m[2]}</span></span> : <span>{v}</span>;
}

function Name({ id, name, onItem, className }: { id: string; name: string; onItem: (id: string) => void; className?: string }) {
  return <Button variant="ghost" className={cn("h-auto min-h-11 justify-start px-2 py-1 text-left text-sm font-medium whitespace-normal text-foreground sm:min-h-10 [overflow-wrap:anywhere]", className)} onClick={() => onItem(id)}>{name}</Button>;
}

// Copy text for Claude Code, or add the row to the checklist (the server only accepts rows in today's brief). Ask never edits anything itself.
function HandoffBar({ h }: { h: Handoff }) {
  const [state, setState] = useState<"idle" | "copied" | "added" | "had" | "failed">("idle");
  async function copy() {
    try { await navigator.clipboard.writeText(h.instruction); setState("copied"); } catch { setState("failed"); }
  }
  async function add() {
    try {
      const r = await fetch("api/checklist", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: h.checklist_id }) });
      if (!r.ok) throw new Error();
      setState(((await r.json()) as { added?: boolean }).added ? "added" : "had");
    } catch { setState("failed"); }
  }
  return <div className="mt-2 flex flex-wrap items-center gap-2">
    {h.checklist_id && <Button variant="outline" className="h-11 gap-2 px-3 text-[13px] font-normal sm:h-9" disabled={state === "added" || state === "had"} onClick={() => void add()}>
      {state === "added" || state === "had" ? <CheckIcon aria-hidden /> : <ListPlusIcon aria-hidden />}{state === "added" ? "Added to checklist" : state === "had" ? "Already on checklist" : "Add to checklist"}</Button>}
    <Button variant="outline" className="h-11 gap-2 px-3 text-[13px] font-normal sm:h-9" onClick={() => void copy()}>
      {state === "copied" ? <CheckIcon aria-hidden /> : <CopyIcon aria-hidden />}{state === "copied" ? "Copied" : "Copy instruction for Claude Code"}</Button>
    <span role="status" className="sr-only">{state === "copied" ? "Instruction copied" : state === "added" ? "Added to checklist" : ""}</span>
    {state === "failed" && <span role="alert" className="text-xs text-warn">Could not do that. Try again.</span>}
  </div>;
}

function ItemCard({ c, onItem }: { c: Card; onItem: (id: string) => void }) {
  const t = `card-${c.id}`;
  return <article aria-labelledby={t} className="rounded-lg border border-line-1 bg-surface-2 px-3 py-3 sm:px-4">
    <p className="flex items-center gap-2 text-xs font-medium text-text-3"><span aria-hidden className="glyph" data-kind={c.kind} />{c.kind_label}</p>
    <h3 id={t} className="-ml-2"><Name id={c.id} name={c.name} onItem={onItem} /></h3>
    <p className="line-clamp-3 text-sm leading-[1.55] text-text-2">{c.what}</p>
    <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1">
      <div><dt className="text-[11px] text-text-3"><Term id={`${t}-a`} term="Every session" /></dt><dd className="font-mono text-xs"><Value v={c.always_on} /></dd></div>
      <div><dt className="text-[11px] text-text-3"><Term id={`${t}-b`} term="When used" /></dt><dd className="font-mono text-xs"><Value v={c.on_use} /></dd></div>
      <div className="col-span-2"><dt className="sr-only">Usage</dt><dd className="text-xs"><Value v={c.usage} /></dd></div>
    </dl>
    {c.overlap && <p className="mt-2 text-[13px] text-text-2">{c.overlap.verdict === "wrapper" ? "Wraps or is wrapped by " : "Does the same job as "}<Name id={c.overlap.with_id} name={c.overlap.with_name} onItem={onItem} className="inline h-auto min-h-0 px-1 py-0 underline" /></p>}
    <p className="mt-2 flex flex-wrap items-center gap-2"><span className={cn("inline-flex h-5 items-center rounded-full border border-line-2 px-2 text-xs font-medium", TONE[c.verdict.tone])}>{c.verdict.label}</span><span className="text-xs text-text-3">{c.verdict.why}</span></p>
    <HandoffBar h={c.handoff} />
  </article>;
}

function Compare({ b, onItem }: { b: Blocks; onItem: (id: string) => void }) {
  const [x, y] = b.cards;
  return <div className="overflow-x-auto rounded-lg border border-line-1 bg-surface-2 px-2 py-2 sm:px-3">
    <table className="w-full table-fixed border-collapse text-[13px]">
      <caption className="sr-only">{x.name} compared with {y.name}</caption>
      <thead><tr><td className="w-[22%]" />{[x, y].map((c) => <th key={c.id} scope="col" className="text-left align-top"><Name id={c.id} name={c.name} onItem={onItem} className="px-1 text-[13px]" /></th>)}</tr></thead>
      <tbody>{b.compare!.rows.map((r) => <tr key={r.label} className="border-t border-line-1 align-top">
        <th scope="row" className="py-2 pr-2 text-left text-[11px] font-normal text-text-3">{r.label}</th>
        {[r.a, r.b].map((v, n) => <td key={n} className="px-1 py-2 [overflow-wrap:anywhere]"><Value v={v} /></td>)}
      </tr>)}
      <tr className="border-t border-line-1"><th scope="row" className="py-2 pr-2 text-left text-[11px] font-normal text-text-3">Same cluster</th><td colSpan={2} className="px-1 py-2">{b.compare!.same_cluster ? "yes" : "no"}</td></tr></tbody>
    </table>
  </div>;
}

function Chips({ items, onAsk }: { items: { text: string; ask: string }[]; onAsk: (q: string) => void }) {
  return <ul className="flex flex-wrap gap-2">{items.map((c) => <li key={c.ask}><Button variant="outline" className="h-11 rounded-md px-3 text-[13px] font-normal whitespace-normal sm:h-9" onClick={() => onAsk(c.ask)}>{c.text}</Button></li>)}</ul>;
}

// Mode chip plus a placeholder for the optional model mode (docs/design/model-mode.md, #45). Nothing here is wired: no network, no settings.
function ModeRow() {
  return <div className="mt-2 flex flex-col gap-2">
    <div className="flex flex-wrap items-center gap-2">
      <span className="inline-flex h-6 items-center rounded-full border border-line-2 px-2 text-xs font-medium text-text-2">Local · free</span>
      <span className="inline-flex items-center gap-2 text-xs text-text-3">
        <span role="switch" aria-checked="false" aria-disabled="true" aria-labelledby="smarter-label" aria-describedby="smarter-why" className="relative inline-block h-4 w-7 rounded-full border border-line-2 bg-surface-3 opacity-60"><span className="absolute top-0.5 left-0.5 size-2.5 rounded-full bg-text-4" /></span>
        <span id="smarter-label">Smarter (optional)</span><span>Off</span>
      </span>
    </div>
    <p id="smarter-why" className="hidden text-xs leading-[1.5] text-text-3 sm:block">When you turn it on, a model could write a smarter answer from the same local facts. It is off, and nothing is sent. <span className="text-text-2">Not connected</span> (coming from model mode, #45).</p>
    <details className="text-xs text-text-3 sm:hidden"><summary className="flex min-h-11 cursor-pointer items-center rounded-xs outline-offset-2 focus-visible:outline-2 focus-visible:outline-ring">What is Smarter?</summary><p className="pb-1 leading-[1.5]">When you turn it on, a model could write a smarter answer from the same local facts. It is off, and nothing is sent. <span className="text-text-2">Not connected</span> (coming from model mode, #45).</p></details>
  </div>;
}

// The live region holds only the headline, so a five-row answer is not read aloud in full.
export function Answer({ reply, copied, onCopy, onItem, onAsk }: { reply: Reply; copied: boolean; onCopy: () => void; onItem: (id: string) => void; onAsk: (q: string) => void }) {
  const b = reply.blocks;
  const copy = <Button variant="ghost" size="icon-lg" className="-mr-2 shrink-0 text-text-3" aria-label={copied ? "Copied" : "Copy answer"} onClick={onCopy}>{copied ? <CheckIcon aria-hidden /> : <CopyIcon aria-hidden />}</Button>;
  if (!b) return <div className="flex items-start justify-between gap-2"><p role="status" aria-live="polite" aria-atomic="true" className="text-sm leading-[1.55] whitespace-pre-wrap text-foreground [overflow-wrap:anywhere]">{reply.answer}</p>{copy}</div>;
  return <>
    <div className="flex items-start justify-between gap-2"><p role="status" aria-live="polite" aria-atomic="true" className="text-[15px] leading-[1.45] font-medium text-foreground [overflow-wrap:anywhere]">{b.headline}</p>{copy}</div>
    {(b.cards.length > 0 || b.rows.length > 0) && <div className="mt-4 flex flex-col gap-3">
      {b.compare ? <Compare b={b} onItem={onItem} /> : b.cards.map((c) => <ItemCard key={c.id} c={c} onItem={onItem} />)}
      {b.rows.length > 0 && <ul className="-mx-2 flex flex-col">{b.rows.map((r) => <li key={r.id} className="flex items-center justify-between gap-3">
        <div className="min-w-0"><Name id={r.id} name={r.name} onItem={onItem} /><p className="-mt-1 truncate px-2 pb-1 text-xs text-text-3" title={r.what}>{r.what}</p></div>
        <span className="shrink-0 pr-2 text-right font-mono text-xs"><Value v={r.value} /></span>
      </li>)}</ul>}
      {b.more > 0 && <p className="text-xs text-text-3">{b.more.toLocaleString()} more. Ask a narrower question.</p>}
    </div>}
    {b.note && <p className="mt-3 text-xs text-text-3">{b.note}</p>}
    {b.handoff && <HandoffBar h={b.handoff} />}
    {b.next && <p className="mt-4 flex items-start gap-2 text-[13px] text-text-2"><ArrowRightIcon aria-hidden className="mt-0.5 size-4 shrink-0" />{b.next}</p>}
    {b.did_you_mean.length > 0 && <div className="mt-4"><Chips items={b.did_you_mean.map((d) => ({ text: d.name, ask: d.ask }))} onAsk={onAsk} /></div>}
    {b.follow_ups.length > 0 && <div className="mt-4"><Chips items={b.follow_ups.map((q) => ({ text: q, ask: q }))} onAsk={onAsk} /></div>}
  </>;
}

export function Chat({ model, selected, open, onOpen, onActions, onReset, onItem, draft }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const request = useRef<AbortController | null>(null);
  const [bottom, setBottom] = useState(96);
  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState("");
  const [reply, setReply] = useState<Reply | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [unavailable, setUnavailable] = useState(false);
  const [slow, setSlow] = useState(false);
  const [copied, setCopied] = useState(false);
  const [more, setMore] = useState(false);
  const echo = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    if (!pending) return;
    const t = setTimeout(() => setSlow(true), 150); // local answers are usually faster: no flash of "Looking…"
    return () => { clearTimeout(t); setSlow(false); };
  }, [pending]);
  useEffect(() => {
    if (reply) echo.current?.scrollIntoView({ block: "start", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }, [reply]);
  async function copy() {
    try { await navigator.clipboard.writeText(reply?.answer ?? ""); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch { /* clipboard blocked: nothing to confirm */ }
  }

  useEffect(() => {
    const legend = document.querySelector('ul[aria-label="Legend"]');
    if (!legend) return;
    const measure = () => setBottom(innerHeight - legend.getBoundingClientRect().top + 8);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(legend);
    addEventListener("resize", measure);
    return () => { observer.disconnect(); removeEventListener("resize", measure); };
  }, [open]); // the Legend changes height when it hides or the chat opens, so measure again
  const [seen, setSeen] = useState(draft);
  if (draft !== seen) { setSeen(draft); setQuestion(draft?.text ?? ""); } // a new draft replaces the box once (not an effect: no extra render)
  useEffect(() => { if (open && draft) input.current?.focus(); }, [draft, open]);
  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => {
    if (open) { input.current?.focus(); return; }
    // Closing (Esc, entering a cluster, picking an Item) drops the request and the answer so a late reply cannot move the map.
    request.current?.abort();
    request.current = null;
  }, [open]);
  if (!open && (pending || reply || asked)) { setPending(false); setReply(null); setAsked(""); }

  function collapse() {
    onOpen(false);
    requestAnimationFrame(() => document.getElementById("ask-trigger")?.focus());
  }
  // On the dismiss stack, but a click on a star or the Inspector keeps it (that is the "ask about this" flow); empty sky, Escape and the X close it.
  useLayer(open, { rank: RANK.panel, press: false, close: (why) => (why === "escape" ? collapse() : onOpen(false)) });

  function reset() {
    request.current?.abort();
    request.current = null;
    setPending(false);
    setQuestion("");
    setAsked("");
    setReply(null);
    setError(unavailable ? UNAVAILABLE : "");
    onReset();
    requestAnimationFrame(() => input.current?.focus());
  }

  async function ask(text: string) {
    text = text.trim();
    setQuestion(text);
    if (pending || unavailable || !text || text.length > 1000) return;
    if (!["localhost", "127.0.0.1"].includes(location.hostname)) {
      setAsked(text);
      setUnavailable(true);
      setError(UNAVAILABLE);
      return;
    }
    const controller = new AbortController();
    request.current = controller;
    setPending(true);
    setError("");
    setReply(null);
    setAsked(text);
    onReset();
    try {
      const response = await fetch("api/chat", {
        method: "POST", headers: { "Content-Type": "application/json" }, signal: controller.signal,
        body: JSON.stringify({ question: text, ...(selected && model.nodes.includes(selected) ? { selected_ids: [selected.id] } : {}) }),
      });
      if ([404, 405, 501].includes(response.status) || !response.headers.get("content-type")?.includes("application/json")) {
        setUnavailable(true);
        throw new Error(UNAVAILABLE);
      }
      if (!response.ok) throw new Error("Could not get a local answer. Please try again.");
      const result = readReply(await response.json(), model);
      if (controller.signal.aborted) return;
      setReply(result);
      onActions(result.actions);
    } catch (e) {
      if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Could not get a local answer. Please try again.");
    } finally {
      if (request.current === controller) {
        request.current = null;
        setPending(false);
        requestAnimationFrame(() => input.current?.focus());
      }
    }
  }

  return <>
    <Presence>{open && <Pane
      key="chat" as="section" from="left"
      id="chat-panel"
      aria-labelledby="chat-title"
      style={{ "--chat-bottom": `${bottom}px` } as CSSProperties}
      className="glass fixed inset-x-0 bottom-0 flex h-[58dvh] max-h-[58dvh] flex-col rounded-t-2xl border border-b-0 shadow-(--shadow-float) sm:inset-x-auto sm:h-auto sm:top-[76px] sm:bottom-(--chat-bottom) sm:left-4 sm:max-h-[calc(100dvh-76px-var(--chat-bottom))] sm:w-[340px] sm:rounded-xl sm:border-b"
      onKeyDown={(e) => { if (e.key === "Escape") { e.preventDefault(); collapse(); } }}
    >
      <div aria-hidden className="mx-auto mt-2 h-1 w-9 shrink-0 rounded-full bg-line-2 sm:hidden" />
      <div className="shrink-0 border-b border-line-1 px-4 pt-3 pb-3 sm:px-6 sm:pt-4">
        <div className="flex items-center justify-between gap-2">
          <h2 id="chat-title" className="text-sm font-medium">Ask your Constellation</h2>
          <Button variant="ghost" size="icon-lg" className="-mr-2 text-text-3" aria-label="Collapse local chat" aria-expanded={true} aria-controls="chat-panel" onClick={collapse}><XIcon aria-hidden /></Button>
        </div>
        <ModeRow />
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto overscroll-contain px-4 pt-4 pb-4 sm:px-6">
        {!asked && <>
          <p className="hidden text-sm leading-[1.55] text-text-2 sm:block">Ask about this setup. Answers are worked out here, for free.</p>
          <div>
            <h3 className="mb-1 text-xs font-medium text-text-3">What you can ask</h3>
            <div className="-mx-2 flex flex-col items-start">
              {starters(model, selected).slice(0, more ? 6 : 4).map((q) => <Button key={q} variant="ghost" className="h-auto min-h-11 w-full justify-start px-2 py-2 text-left text-[13px] font-normal whitespace-normal sm:min-h-10" disabled={pending || unavailable} onClick={() => void ask(q)}>{q}</Button>)}
              {starters(model, selected).length > 4 && <Button variant="ghost" className="h-auto min-h-11 w-full justify-start px-2 py-2 text-left text-[13px] font-normal text-text-3 sm:min-h-10" aria-expanded={more} onClick={() => setMore(!more)}>{more ? "Fewer questions" : "More questions"}</Button>}
            </div>
          </div>
        </>}
        {asked && <p ref={echo} className="scroll-mt-2 text-[13px] leading-[1.4] text-text-3 [overflow-wrap:anywhere]">{asked}</p>}
        {slow && pending && <p role="status" aria-live="polite" className="text-sm text-text-2">Looking in this Constellation…</p>}
        {reply && <div><Answer reply={reply} copied={copied} onCopy={() => void copy()} onItem={onItem} onAsk={(q) => void ask(q)} /></div>}
        {error && <p role="alert" className="flex items-start gap-2 text-[13px] leading-[1.4] text-warn"><TriangleAlertIcon aria-hidden className="size-4 shrink-0" />{error}</p>}
      </div>
      <form onSubmit={(e) => { e.preventDefault(); void ask(question); }} className="flex shrink-0 flex-col gap-2 border-t border-line-1 px-4 pt-3 pb-[max(16px,env(safe-area-inset-bottom))] sm:px-6 sm:pb-4">
        {selected && <p className="truncate text-xs text-text-3" title={selected.name}>Selected: {selected.name}</p>}
        <label htmlFor="chat-question" className="sr-only">Your question</label>
        <Input ref={input} id="chat-question" value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={1000} autoComplete="off" placeholder="Ask about this scan…" disabled={pending || unavailable} className="h-11 text-sm" />
        <div className="flex items-center justify-between gap-2">
          <Button type="button" variant="ghost" disabled={!asked && !question} className="h-11 gap-2 px-2 text-text-3 sm:h-10" onClick={reset}><RotateCcwIcon aria-hidden />Reset</Button>
          <Button type="submit" disabled={pending || unavailable || !question.trim()} aria-busy={pending} className="h-11 gap-2 sm:h-10"><SendIcon aria-hidden />{pending ? "Looking…" : "Send"}</Button>
        </div>
      </form>
    </Pane>}</Presence>
  </>;
}

// Lives in the top bar beside search (docs/design/ask-placement.md), so it never competes with the Legend or a sheet for the bottom-left corner.
export function AskTrigger({ open, onOpen }: { open: boolean; onOpen: (open: boolean) => void }) {
  return <Button id="ask-trigger" variant="outline" aria-expanded={open} aria-controls={open ? "chat-panel" : undefined} aria-keyshortcuts="A" title="Ask (A)" onClick={() => onOpen(!open)}
    className="glass h-11 shrink-0 gap-2 rounded-lg border-indigo-bright/40 px-3 text-[13px] text-foreground hover:border-indigo-bright/70 aria-expanded:bg-indigo-bright/20 sm:h-10">
    {/* the label folds to an icon where the one-row desktop bar is full (641-1379px); it stays on phones, where the button has its own row */}
    <MessageCircleIcon aria-hidden /><span className="sm:max-[1379px]:sr-only">Ask</span><Kbd aria-hidden className="hidden lg:inline-flex">A</Kbd>
  </Button>;
}
