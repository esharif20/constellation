import { ArrowLeftIcon } from "lucide-react";
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { Pane } from "@/components/Motion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { clusterHealth, clusterSummary, kindName, rankMembers, type Cluster, type GNode, type GOverlap, type Model } from "@/graph/model";

type Props = {
  cluster: Cluster;
  model: Model;
  focusTitle: boolean; // entered by keyboard: move focus to the heading so it is read out
  onBack: () => void;
  onItem: (n: GNode) => void;
  onPreview: (n: GNode | null) => void;
  onPair: (o: GOverlap) => void;
  removed?: Set<GNode> | null; // what-if ghosts
};

const n1 = (n: number, one: string, many = `${one}s`) => `${n.toLocaleString()} ${n === 1 ? one : many}`;
// "skills", "MCP servers": lower-case the kind name unless it starts with an acronym
const kindPlural = (k: string, n: number) => { const s = kindName(k); const w = /^[A-Z]{2}/.test(s) ? s : s.toLowerCase(); return n1(n, w); };
const day = (iso: string) => new Date(`${iso}T00:00:00Z`).getTime();

// What one cluster costs: the left card while a cluster is focused (the left slot has one occupant: this, the Brief or the chat).
// Unknown cost is said as "unknown", never added in and never shown as 0.
export function ClusterCard({ cluster, model, focusTitle, onBack, onItem, onPreview, onPair, removed = null }: Props) {
  const s = clusterSummary(cluster, model);
  const health = clusterHealth(model, removed);
  const hc = health.get(cluster)!;
  const title = useRef<HTMLHeadingElement>(null);
  const [bottom, setBottom] = useState(96);
  const maxTop = s.top[0]?.cost?.always_on ?? 0;
  const win = model.usageWindow;
  const days = win?.first && win.last ? Math.max(1, Math.round((day(win.last) - day(win.first)) / 864e5) + 1) : 0;

  useEffect(() => { if (focusTitle) title.current?.focus(); }, [focusTitle, cluster]);
  useEffect(() => { // keep clear of the legend, as the Brief does
    const legend = document.querySelector('ul[aria-label="Legend"]');
    if (!legend) return;
    const measure = () => setBottom(innerHeight - legend.getBoundingClientRect().top + 8);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(legend);
    addEventListener("resize", measure);
    return () => { observer.disconnect(); removeEventListener("resize", measure); };
  }, []);

  const verdicts = (["duplicate", "wrapper", "overlap"] as const).flatMap((v) => {
    const n = s.overlaps.filter((o) => o.verdict === v).length;
    return n ? [n1(n, v === "duplicate" ? "duplicate" : v === "wrapper" ? "wrapper" : "overlap")] : [];
  });
  const row = (n: GNode) => (
    <Button
      variant="ghost"
      className="h-auto min-h-10 w-full min-w-0 justify-start gap-3 px-2 py-2 text-left font-normal whitespace-normal"
      onClick={() => onItem(n)}
      onMouseEnter={() => onPreview(n)}
      onMouseLeave={() => onPreview(null)}
      onFocus={() => onPreview(n)}
      onBlur={() => onPreview(null)}
    >
      <span aria-hidden className="glyph" data-kind={n.kind} />
      <span className="min-w-0 flex-1 text-sm [overflow-wrap:anywhere]">{n.name}<span className="sr-only">, {kindName(n.kind)}</span></span>
      <span className="shrink-0 text-right font-mono text-xs tabular-nums">{n.unknown ? <i className="font-sans text-text-3">unknown</i> : <>{n.cost!.always_on!.toLocaleString()}<span className="sr-only"> tokens always on</span></>}</span>
    </Button>
  );

  return (
    <Pane
      as="section" from="left" delay={300} /* waits for ~30% of the camera flight */
      aria-labelledby="cluster-title"
      style={{ "--card-bottom": `${bottom}px` } as CSSProperties}
      className="glass fixed inset-x-0 bottom-0 flex max-h-[40dvh] flex-col rounded-t-2xl border border-b-0 shadow-(--shadow-float) sm:inset-x-auto sm:top-[76px] sm:bottom-auto sm:left-4 sm:max-h-[calc(100dvh-76px-var(--card-bottom))] sm:w-[340px] sm:rounded-xl sm:border-b"
    >
      <div aria-hidden className="mx-auto mt-2 h-1 w-9 shrink-0 rounded-full bg-line-2 sm:hidden" />
      <div className="flex shrink-0 items-center gap-1 px-2 pt-2 sm:px-3 sm:pt-3">
        <Button variant="ghost" size="icon-lg" aria-label="Back to the whole map" onClick={onBack}><ArrowLeftIcon aria-hidden /></Button>
        <p className="text-xs font-medium tracking-[0.02em] text-text-3">Cluster</p>
      </div>
      <div className="flex flex-col gap-5 overflow-y-auto overscroll-contain px-4 pt-1 pb-[max(20px,env(safe-area-inset-bottom))] sm:px-6">
        <div>
          <h2 id="cluster-title" ref={title} tabIndex={-1} className="font-serif text-[22px] leading-[1.15] tracking-[0.01em] [overflow-wrap:anywhere] italic outline-none">{cluster.name}</h2>
          <p className="mt-1 text-sm text-text-2">{n1(s.count, "Item")}</p>
          <ul className="mt-3 flex flex-wrap gap-1.5" aria-label="Kinds in this cluster">
            {s.kinds.map(([k, n]) => (
              <li key={k}><Badge className="gap-1.5"><span aria-hidden className="glyph" data-kind={k} />{kindPlural(k, n)}</Badge></li>
            ))}
          </ul>
        </div>

        <div className="rounded-lg border bg-surface-2 px-4 py-3">
          {s.known == null
            ? <p className="text-base text-text-3 italic">unknown</p>
            : <p className="font-mono text-2xl leading-none tabular-nums">{s.known.toLocaleString()}</p>}
          <p className="mt-1.5 text-xs text-text-3">{s.known == null ? "tokens always on, not measured" : "tokens always on (known)"}</p>
          {s.unknown > 0 && s.known != null && <p className="mt-1 text-xs leading-[1.4] text-text-3">{s.unknown} of {s.count} have unknown cost, not counted</p>}
          {hc.useShare != null && <p className="mt-1 text-xs text-text-3">{hc.useShare > 0 && hc.useShare < 0.01 ? "<1" : Math.round(hc.useShare * 100)}% of all recorded uses</p>}
          {hc.rank != null && <p className="mt-1 text-xs text-text-3">Costliest cluster: {hc.rank} of {[...health.values()].filter((h) => h.rank != null).length}</p>}
        </div>

        {s.top.length > 0 && <section aria-labelledby="card-top">
          <h3 id="card-top" className="text-sm font-medium">Most expensive</h3>
          <ul className="-mx-2 mt-2 flex flex-col gap-0.5">
            {s.top.map((n) => (
              <li key={n.id}>
                {row(n)}
                <span aria-hidden className="-mt-1 mb-1 ml-[29px] block h-1 overflow-hidden rounded-full bg-line-1"><span className="block h-full rounded-full bg-indigo-bright/60" style={{ width: `${maxTop ? (100 * n.cost!.always_on!) / maxTop : 0}%` }} /></span>
              </li>
            ))}
          </ul>
        </section>}

        {s.overlaps.length > 0 && <section aria-labelledby="card-overlaps">
          <h3 id="card-overlaps" className="text-sm font-medium">Overlaps inside</h3>
          <p className="mt-1 text-xs text-text-3">{verdicts.join(", ")}</p>
          <ul className="-mx-2 mt-2 flex flex-col gap-0.5">
            {s.overlaps.slice(0, 4).map((o) => (
              <li key={`${o.a.id}|${o.b.id}`}>
                <Button variant="ghost" className="h-auto min-h-10 w-full justify-start gap-3 px-2 py-2 text-left font-normal whitespace-normal" onClick={() => onPair(o)}
                  onMouseEnter={() => onPreview(o.a)} onMouseLeave={() => onPreview(null)} onFocus={() => onPreview(o.a)} onBlur={() => onPreview(null)}>
                  <span className="min-w-0 flex-1 text-sm [overflow-wrap:anywhere]">{o.a.name} / {o.b.name}<span className="block text-xs text-text-3">{o.verdict === "wrapper" ? "wrapper" : o.verdict}</span></span>
                </Button>
              </li>
            ))}
          </ul>
        </section>}

        {s.unused && win && <section aria-labelledby="card-unused">
          <h3 id="card-unused" className="text-sm font-medium">Unused</h3>
          <p className="mt-1 text-[13px] leading-[1.4] text-text-2">{s.unused.unseen} of {s.unused.tracked} tracked Items not seen in {n1(win.files, "transcript")}{days ? ` over ${n1(days, "day")}` : ""}</p>
          <p className="mt-1 text-xs text-text-3">Claude Code deletes older transcripts.</p>
        </section>}

        <Separator />
        <details open={s.count <= 12} className="group">
          <summary className="cursor-pointer list-none text-sm font-medium after:ml-2 after:text-text-3 after:content-['+'] group-open:after:content-['\2212']">All {s.count} Items</summary>
          <ul className="-mx-2 mt-2 flex flex-col gap-0.5">
            {rankMembers(cluster).map((n) => <li key={n.id}>{row(n)}</li>)}
          </ul>
        </details>
      </div>
    </Pane>
  );
}
