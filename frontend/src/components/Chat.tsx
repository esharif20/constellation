import { MessageCircleIcon, RotateCcwIcon, SendIcon, TriangleAlertIcon, XIcon } from "lucide-react";
import { useEffect, useRef, useState, type CSSProperties, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { GNode, Model } from "@/graph/model";
import { cn } from "@/lib/utils";

export type ChatAction = { kind: "highlight" | "focus"; item_ids: string[] };
type Reply = { answer: string; actions: ChatAction[]; mode: "local"; cached: boolean };
type Props = {
  model: Model;
  selected: GNode | null;
  open: boolean;
  briefOpen: boolean;
  clusterOpen: boolean;
  onOpen: (open: boolean) => void;
  onActions: (actions: ChatAction[]) => void;
  onReset: () => void;
  onItem: (id: string) => void;
};

const UNAVAILABLE = "Local chat is unavailable here. Open this Constellation with a current local server to ask questions.";
const EXAMPLES = ["What costs the most?", "Show duplicates", "Find email tools", "What have I never used?"];

// Validate the whole reply before changing the map: the server can only refer to Items already in this Constellation.
function readReply(value: unknown, model: Model): Reply {
  if (!value || typeof value !== "object") throw new Error("Invalid local answer. Please try again.");
  const r = value as Partial<Reply>;
  const known = new Set(model.nodes.map((n) => n.id));
  if (typeof r.answer !== "string" || !r.answer.trim() || r.mode !== "local" || typeof r.cached !== "boolean" || !Array.isArray(r.actions) || r.actions.some((a) => !a || !["highlight", "focus"].includes(a.kind) || !Array.isArray(a.item_ids) || a.item_ids.some((id: unknown) => typeof id !== "string" || !known.has(id)))) {
    throw new Error("Invalid local answer. Please try again.");
  }
  return r as Reply;
}

export function Chat({ model, selected, open, briefOpen, clusterOpen, onOpen, onActions, onReset, onItem }: Props) {
  const trigger = useRef<HTMLButtonElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const request = useRef<AbortController | null>(null);
  const [bottom, setBottom] = useState(96);
  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState("");
  const [reply, setReply] = useState<Reply | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [unavailable, setUnavailable] = useState(false);

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
  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);

  function collapse() {
    onOpen(false);
    requestAnimationFrame(() => trigger.current?.focus());
  }

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

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (pending || unavailable || !question.trim() || question.length > 1000) return;
    if (!["localhost", "127.0.0.1"].includes(location.hostname)) {
      setAsked(question.trim());
      setUnavailable(true);
      setError(UNAVAILABLE);
      return;
    }
    const controller = new AbortController();
    request.current = controller;
    setPending(true);
    setError("");
    setReply(null);
    setAsked(question.trim());
    onReset();
    try {
      const response = await fetch("api/chat", {
        method: "POST", headers: { "Content-Type": "application/json" }, signal: controller.signal,
        body: JSON.stringify({ question: question.trim(), ...(selected && model.nodes.includes(selected) ? { selected_ids: [selected.id] } : {}) }),
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

  const ids = [...new Set(reply?.actions.flatMap((a) => a.item_ids) ?? [])];
  const items = ids.flatMap((id) => model.nodes.find((n) => n.id === id) ?? []);

  return <>
    {open ? <section
      id="chat-panel"
      aria-labelledby="chat-title"
      style={{ "--chat-bottom": `${bottom}px` } as CSSProperties}
      className="glass fixed inset-x-0 bottom-0 flex h-[58dvh] max-h-[58dvh] animate-sheet-in flex-col rounded-t-2xl border border-b-0 shadow-(--shadow-float) sm:inset-x-auto sm:h-auto sm:top-[76px] sm:bottom-(--chat-bottom) sm:left-4 sm:max-h-[calc(100dvh-76px-var(--chat-bottom))] sm:w-[340px] sm:animate-panel-in sm:rounded-xl sm:border-b"
      onKeyDown={(e) => { if (e.key === "Escape") { e.preventDefault(); collapse(); } }}
    >
      <div aria-hidden className="mx-auto mt-2 h-1 w-9 shrink-0 rounded-full bg-line-2 sm:hidden" />
      <div className="flex shrink-0 items-start justify-between gap-2 px-4 pt-3 sm:px-6 sm:pt-4">
        <div className="pt-1"><h2 id="chat-title" className="text-sm font-medium">Ask your Constellation</h2><p className="mt-1 text-xs text-text-3">Local answers · models off</p></div>
        <Button variant="ghost" size="icon-lg" className="-mr-2 text-text-3" aria-label="Collapse local chat" aria-expanded={true} aria-controls="chat-panel" onClick={collapse}><XIcon aria-hidden /></Button>
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto overscroll-contain px-4 pt-4 sm:px-6">
        {!asked && <>
          <p className="text-sm leading-[1.55] text-text-2">Find Items, compare Context costs, or explore known Overlaps. Answers use this saved scan, for free.</p>
          <div className="flex flex-col items-start gap-1">
            {EXAMPLES.map((q) => <Button key={q} variant="ghost" className="h-auto min-h-10 w-full justify-start px-2 py-2 text-left text-[13px] font-normal whitespace-normal" disabled={pending || unavailable} onClick={() => { setQuestion(q); input.current?.focus(); }}>{q}</Button>)}
            {selected && <Button disabled={pending || unavailable} variant="ghost" className="h-auto min-h-10 w-full justify-start px-2 py-2 text-left text-[13px] font-normal whitespace-normal" onClick={() => { setQuestion("Explain the selected Item"); input.current?.focus(); }}>Explain the selected Item</Button>}
          </div>
        </>}
        {asked && <p className="text-[13px] leading-[1.4] text-text-3 [overflow-wrap:anywhere]">{asked}</p>}
        <div role="status" aria-live="polite" aria-atomic="true">
          {pending && <p className="text-sm text-text-2">Looking in this Constellation…</p>}
          {reply && <p className="text-sm leading-[1.55] text-text-2 whitespace-pre-wrap [overflow-wrap:anywhere]">{reply.answer}</p>}
        </div>
        {items.length > 0 && <div>
          <p className="mb-2 text-xs text-text-3">Highlighted on the map</p>
          <ul className="-mx-2 flex flex-col gap-1">{items.map((n) => <li key={n.id}><Button variant="ghost" className="h-auto min-h-10 w-full justify-start gap-3 px-2 py-2 text-left text-[13px] font-normal whitespace-normal" onClick={() => onItem(n.id)}><span aria-hidden className="glyph" data-kind={n.kind} /><span className="[overflow-wrap:anywhere]">{n.name}</span></Button></li>)}</ul>
        </div>}
        {error && <p role="alert" className="flex items-start gap-2 text-[13px] leading-[1.4] text-warn"><TriangleAlertIcon aria-hidden className="size-4 shrink-0" />{error}</p>}
      </div>
      <form onSubmit={(e) => void submit(e)} className="mt-4 flex shrink-0 flex-col gap-2 border-t px-4 pt-4 pb-[max(16px,env(safe-area-inset-bottom))] sm:px-6 sm:pb-6">
        {selected && <p className="truncate text-xs text-text-3" title={selected.name}>Selected: {selected.name}</p>}
        <label htmlFor="chat-question" className="text-xs font-medium text-text-3">Your question</label>
        <Input ref={input} id="chat-question" value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={1000} autoComplete="off" placeholder="Ask about this scan…" disabled={pending || unavailable} className="h-11 text-sm" />
        <div className="flex items-center justify-between gap-2">
          <Button type="button" variant="ghost" disabled={!asked && !question} className="h-11 gap-2 px-2 text-text-3 sm:h-10" onClick={reset}><RotateCcwIcon aria-hidden />Reset</Button>
          <Button type="submit" disabled={pending || unavailable || !question.trim()} aria-busy={pending} className="h-11 gap-2 sm:h-10"><SendIcon aria-hidden />{pending ? "Looking…" : "Ask locally"}</Button>
        </div>
      </form>
    </section> : <Button ref={trigger} variant="outline" style={{ "--chat-bottom": `${bottom}px` } as CSSProperties} className={cn("glass fixed bottom-24 left-4 h-11 gap-2 rounded-full px-4 sm:bottom-(--chat-bottom) sm:h-10", selected ? "bottom-[calc(58dvh+12px)] sm:bottom-(--chat-bottom)" : clusterOpen ? "bottom-[calc(40dvh+12px)] sm:bottom-(--chat-bottom)" : briefOpen ? "bottom-[calc(46dvh+12px)] sm:bottom-(--chat-bottom)" : "")} aria-expanded={false} onClick={() => onOpen(true)}><MessageCircleIcon aria-hidden />Ask locally</Button>}
  </>;
}
