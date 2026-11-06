import { useEffect, useState } from "react";
import { ChevronRightIcon, CheckIcon, TriangleAlertIcon } from "lucide-react";
import { Presence, Pane } from "@/components/Motion";
import type { GNode, Model } from "@/graph/model";
import type { Removal, RemovalRow } from "@/graph/lenses";
import { cn } from "@/lib/utils";

const GROUPS: [keyof Pick<Removal, "covered_by" | "referenced_by" | "hooks" | "contains">, string][] = [
  ["covered_by", "Still covered by"], ["referenced_by", "Refer to it"], ["hooks", "Hooks"], ["contains", "Goes with it"],
];

// One Item row; a click glides to it when the map holds that Item.
function Row({ row, model, onSelect }: { row: RemovalRow; model: Pick<Model, "nodes">; onSelect: (n: GNode) => void }) {
  const node = model.nodes.find((n) => n.id === row.id);
  const label = <><span className="glyph" data-kind={row.kind} /><span className="[overflow-wrap:anywhere]">{row.name}</span></>;
  return <li>
    {node
      ? <button type="button" onClick={() => onSelect(node)} className="-mx-2 flex min-h-10 w-[calc(100%+1rem)] items-center gap-3 rounded-md px-2 text-left text-sm text-foreground outline-none hover:bg-surface-2 focus-visible:ring-[3px] focus-visible:ring-ring/50 max-sm:min-h-11">{label}</button>
      : <span className="flex min-h-8 items-center gap-3 text-sm">{label}</span>}
    <p className="pl-[26px] text-xs leading-[1.45] text-text-3 [overflow-wrap:anywhere]">{row.why}</p>
  </li>;
}

// The answer, split out of the disclosure so it renders without a fetch.
// `listed`: ids the Inspector already shows under "Does the same job" / "Wraps"; a covering Item in that list is named once, there.
export function RemovalBody({ data, model, onSelect, listed = new Set() }: { data: Removal; model: Pick<Model, "nodes">; onSelect: (n: GNode) => void; listed?: ReadonlySet<string> }) {
  const dup = data.covered_by.filter((r) => listed.has(r.id));
  const Icon = data.safe ? CheckIcon : TriangleAlertIcon;
  return <div className="mt-2">
    <p className={cn("flex items-start gap-2 text-[13px] leading-[1.45]", data.safe ? "text-indigo-bright" : "text-warn")}>
      <Icon aria-hidden className="mt-0.5 size-4 shrink-0" /><b className="font-semibold">{data.verdict}</b>
    </p>
    <ul className="mt-1 list-disc pl-5 text-[13px] leading-[1.45] text-text-2">{data.reasons.map((t) => <li key={t}>{t}</li>)}</ul>
    {dup.length > 0 && <p className="mt-3 text-xs leading-[1.45] text-text-3">Still covered by {dup.map((r) => r.name).join(", ")}, listed below.</p>}
    {GROUPS.map(([key, title]) => {
      const rows = key === "covered_by" ? data[key].filter((r) => !listed.has(r.id)) : data[key];
      return rows.length > 0 && <section key={key} className="mt-3">
      <h4 className="text-xs font-medium text-text-3">{title} <span className="ml-1 font-mono tabular-nums">{rows.length}</span></h4>
      <ul className="flex flex-col">{rows.map((r) => <Row key={r.id} row={r} model={model} onSelect={onSelect} />)}</ul>
    </section>;
    })}
    {data.cluster && <p className="mt-3 text-xs leading-[1.45] text-text-3">Same group, {data.cluster.name}: {data.cluster.others.join(", ")}{data.cluster.more > 0 && ` and ${data.cluster.more} more`}.</p>}
    <p className="mt-3 text-xs text-text-3">Nothing is changed here. Remove it by hand.</p>
  </div>;
}

// "If you remove this": closed until asked, then one local request to /api/removal. A failed request says so and offers no guess.
export function RemovalPreview({ item, model, onSelect, listed }: { item: GNode; model: Pick<Model, "nodes">; onSelect: (n: GNode) => void; listed?: ReadonlySet<string> }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<Removal | "error" | null>(null);
  useEffect(() => {
    if (!open || data) return;
    const controller = new AbortController();
    void fetch(`api/removal?id=${encodeURIComponent(item.id)}`, { signal: controller.signal })
      .then((r) => { if (!r.ok) throw new Error("unavailable"); return r.json() as Promise<Removal>; })
      .then(setData)
      .catch((e: unknown) => { if (!(e instanceof DOMException && e.name === "AbortError")) setData("error"); });
    return () => controller.abort();
  }, [open, data, item.id]);
  return <section className="mt-4 border-t border-line-1 pt-2">
    <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className="group flex min-h-10 w-full items-center gap-2 rounded-md text-left text-[13px] font-medium text-text-2 outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 max-sm:min-h-11">
      <ChevronRightIcon aria-hidden className={cn("size-4 shrink-0 text-text-3 transition-transform duration-(--t-fast) ease-(--ease-out)", open && "rotate-90")} />
      If you remove this
    </button>
    <Presence>{open ? <Pane from="top">
      {data === null ? <p role="status" className="mt-2 text-xs text-text-3">Checking your setup...</p>
        : data === "error" ? <p role="status" className="mt-2 text-xs text-text-3">The preview is not available here.</p>
        : <RemovalBody data={data} model={model} onSelect={onSelect} listed={listed} />}
    </Pane> : null}</Presence>
  </section>;
}
