import { BookOpenIcon } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Spinner } from "@/components/ui/spinner";
import type { Cluster, GNode, Model } from "@/graph/model";

// Shape of GET api/explain (src/constellation/explain.py): names only, no ids.
export type Summary = {
  public: boolean; items: number; known: number | null; unknown: number; text: string;
  clusters: { name: string; items: number; always_on: number | null }[];
  costs: { name: string; kind: string; always_on: number }[];
  unused: { name: string; kind: string; always_on: number | null }[] | null;
  window: { files: number; days: number } | null;
  actions: { reason: string; tokens_saved: number | null }[];
};

const SEEN = "constellation.explain";
const LIMIT = "No usage dates, paths or ids. Item names may still contain dates.";
const tok = (n: number | null) => (n == null ? "cost unknown" : `${n.toLocaleString("en-US")} tokens`);
const seen = () => { try { return localStorage.getItem(SEEN) === "seen"; } catch { return true; } }; // no storage: never nag
const mark = () => { try { localStorage.setItem(SEEN, "seen"); } catch { /* Storage is optional. */ } };

export type CopyResult = "ok" | "refused" | "failed";

// The private text is local; the public text is only copied when the server says it is public (a missing ?public means private).
export async function copyPublic(fetcher: typeof fetch = fetch, write: (t: string) => Promise<void> = (t) => navigator.clipboard.writeText(t)): Promise<{ result: CopyResult; text: string }> {
  try {
    const r = await fetcher("api/explain?public=1");
    const d = r.ok ? ((await r.json()) as Summary) : null;
    if (!d || d.public !== true) return { result: "refused", text: "" };
    await write(d.text);
    return { result: "ok", text: d.text };
  } catch { return { result: "failed", text: "" }; }
}

export function ExplainCard({ model, onCluster, onItem }: { model: Model; onCluster: (c: Cluster) => void; onItem: (n: GNode) => void }) {
  const [open, setOpen] = useState(() => !seen() && !navigator.webdriver); // first visit only; browser automation is never blocked
  const [data, setData] = useState<Summary | null>(null);
  const [error, setError] = useState(false);
  const [note, setNote] = useState("");
  const [copied, setCopied] = useState<"" | "local" | "public">("");
  const [fallback, setFallback] = useState("");

  const load = () => { setError(false); setData(null); };
  useEffect(() => {
    if (!open || data || error) return;
    fetch("api/explain").then((r) => { if (!r.ok) throw new Error(); return r.json(); }).then(setData, () => setError(true));
  }, [open, data, error]);

  const onOpenChange = (o: boolean) => { setOpen(o); if (o) { setNote(""); setFallback(""); } else mark(); };
  const done = (which: "local" | "public") => { setCopied(which); setNote(`Copied the ${which === "local" ? "summary" : "public version"}.`); setFallback(""); setTimeout(() => setCopied(""), 2000); };
  const fail = (text: string, msg = "Could not copy. Select the text below instead.") => { setNote(msg); setFallback(text); };

  const copyLocal = () => {
    if (!data) return;
    navigator.clipboard.writeText(data.text).then(() => done("local"), () => fail(data.text));
  };
  const copyPub = async () => {
    const { result } = await copyPublic();
    if (result === "ok") done("public");
    else if (result === "refused") fail("", "Could not confirm a public summary, so nothing was copied.");
    else fail("", "Could not copy the public version. Nothing was copied.");
  };

  const go = (fn: () => void) => { onOpenChange(false); fn(); };
  const cluster = (name: string) => model.clusters.find((c) => c.name === name);
  const item = (name: string, kind: string) => model.nodes.find((n) => n.name === name && n.kind === kind);
  const row = (key: string, label: ReactNode, detail: string, act: (() => void) | null) => (
    <li key={key}>
      <button type="button" disabled={!act} onClick={() => act && go(act)} className="flex min-h-11 w-full cursor-pointer items-baseline justify-between gap-3 rounded-md px-2 text-left hover:bg-surface-2 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none disabled:cursor-default disabled:hover:bg-transparent">
        <span className="min-w-0 truncate">{label}</span>
        <span className="shrink-0 font-mono text-xs text-text-3 tabular-nums">{detail}</span>
      </button>
    </li>
  );
  const h = "mt-5 mb-1 px-2 text-xs font-medium tracking-wide text-text-3";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button variant="ghost" aria-label="Explain my setup" className="pointer-events-auto h-11 rounded-lg px-3 text-[13px] text-text-2 sm:h-10 sm:order-last">
          <BookOpenIcon data-icon="inline-start" aria-hidden /><span className="hidden lg:inline">Explain my setup</span>
        </Button>
      </DialogTrigger>
      <DialogContent
        onOpenAutoFocus={(e) => { e.preventDefault(); (e.currentTarget as HTMLElement).querySelector<HTMLElement>("[data-title]")?.focus(); }}
        className="glass top-0 left-0 flex h-dvh max-h-dvh max-w-none translate-x-0 translate-y-0 flex-col gap-0 rounded-none p-0 pb-[env(safe-area-inset-bottom)] max-sm:zoom-in-100 max-sm:zoom-out-100 max-sm:data-[state=open]:slide-in-from-bottom-6 max-sm:data-[state=closed]:slide-out-to-bottom-6 sm:top-1/2 sm:left-1/2 sm:h-auto sm:max-h-[min(720px,90dvh)] sm:max-w-xl sm:-translate-x-1/2 sm:-translate-y-1/2 sm:rounded-xl"
      >
        <div className="px-6 pt-6 pb-2">
          <DialogTitle data-title tabIndex={-1} className="font-serif text-[22px] leading-tight font-normal italic outline-none">Your setup at a glance</DialogTitle>
          <DialogDescription className="mt-1 text-[13px]">{data ? `${data.items} Items, ${data.known == null ? "cost not measured" : `${data.known.toLocaleString("en-US")} always-on tokens known`}${data.unknown ? `, ${data.unknown} with unknown cost` : ""}.` : "A short summary of this scan."}</DialogDescription>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4 text-[13px] text-text-2">
          {error ? (
            <div className="flex flex-col items-start gap-3 px-2 py-6"><p>Could not read the summary.</p><Button variant="outline" className="h-11" onClick={load}>Try again</Button></div>
          ) : !data ? (
            <p className="flex items-center gap-2 px-2 py-6"><Spinner />Reading your scan…</p>
          ) : (
            <>
              <h3 className={h}>Largest clusters</h3>
              <ul>{data.clusters.map((c) => { const m = cluster(c.name); return row(c.name, <span className="font-serif text-[15px] text-foreground italic">{c.name}</span>, `${c.items} Items · ${tok(c.always_on)}`, m ? () => onCluster(m) : null); })}</ul>
              <h3 className={h}>Costliest always-on</h3>
              {data.costs.length ? <ul>{data.costs.map((c) => { const n = item(c.name, c.kind); return row(c.name + c.kind, <span className="text-foreground">{c.name}</span>, tok(c.always_on), n ? () => onItem(n) : null); })}</ul> : <p className="px-2 italic">Cost was not measured in this scan.</p>}
              <h3 className={h}>Not used lately</h3>
              {data.unused == null || data.window == null ? <p className="px-2 italic">Usage was not read in this scan.</p> : (
                <>
                  <p className="px-2">{data.unused.length ? "" : "None. "}Checked {data.window.files} transcripts over {data.window.days} days.</p>
                  <ul>{data.unused.map((u) => { const n = item(u.name, u.kind); return row(u.name + u.kind, <span className="text-foreground">{u.name}</span>, tok(u.always_on), n ? () => onItem(n) : null); })}</ul>
                </>
              )}
              <h3 className={h}>Three suggested actions</h3>
              <ul className="flex flex-col gap-2 px-2">{data.actions.length ? data.actions.map((a, i) => <li key={i}>{a.reason} <span className="font-mono text-xs text-text-3">(saves {tok(a.tokens_saved)})</span></li>) : <li className="italic">None.</li>}</ul>
              {fallback && <textarea readOnly aria-label="Summary text" value={fallback} onFocus={(e) => e.currentTarget.select()} className="mt-4 h-32 w-full rounded-md border bg-surface-2 p-2 font-mono text-xs" />}
            </>
          )}
        </div>
        <div className="flex flex-col gap-2 border-t px-6 py-4">
          <div className="flex flex-col gap-2 sm:flex-row">
            <Button variant="outline" disabled={!data} className="h-11 sm:h-10" onClick={copyLocal}>{copied === "local" ? "Copied" : "Copy summary"}</Button>
            <Button variant="outline" disabled={!data} className="h-11 sm:h-10" onClick={() => void copyPub()}>{copied === "public" ? "Copied" : "Copy public version"}</Button>
          </div>
          <p className="text-xs text-text-3">Includes usage dates. For sharing, copy the public version. Public version: {LIMIT}</p>
          <p className="sr-only" role="status" aria-live="polite">{note}</p>
          {note.startsWith("Could") && <p className="text-xs text-warn">{note}</p>}
        </div>
      </DialogContent>
    </Dialog>
  );
}
