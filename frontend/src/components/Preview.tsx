import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

export type PreviewData = {
  pack: { name: string; layout: string };
  items: { id: string; kind: string; name: string }[];
  always_on: { counted: number; estimated: number; unknown: number };
  overlaps: { new_id: string; existing_id: string; existing_name: string; why: string }[];
  already_installed: boolean;
  compared: boolean;
};

const TOP = 5;
const num = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const str = (v: unknown): v is string => typeof v === "string";
const list = (v: unknown): v is Record<string, unknown>[] => Array.isArray(v) && v.every((x) => typeof x === "object" && x !== null);

// The file is untrusted text: anything that is not the expected shape renders nothing.
export function isPreview(d: unknown): d is PreviewData {
  if (typeof d !== "object" || d === null) return false;
  const p = d as Record<string, unknown>, t = p.always_on as Record<string, unknown> | null, k = p.pack as Record<string, unknown> | null;
  return !!t && !!k && str(k.name) && num(t.counted) && num(t.estimated) && num(t.unknown) && typeof p.already_installed === "boolean" && typeof p.compared === "boolean"
    && list(p.items) && p.items.every((i) => str(i.id) && str(i.kind) && str(i.name))
    && list(p.overlaps) && p.overlaps.every((o) => str(o.new_id) && str(o.existing_id) && str(o.existing_name) && str(o.why));
}

export async function loadPreview(fetcher: typeof fetch = fetch, signal?: AbortSignal): Promise<PreviewData | null> {
  try {
    const response = await fetcher("api/preview", { signal });
    if (!response.ok) return null;
    const data: unknown = await response.json();
    return isPreview(data) ? data : null;
  } catch {
    return null;
  }
}

export function Preview({ onItem }: { onItem: (id: string) => void }) {
  const [p, setP] = useState<PreviewData | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void loadPreview(fetch, controller.signal).then((d) => { if (!controller.signal.aborted) setP(d); });
    return () => controller.abort();
  }, []);
  if (!p) return null;
  const { counted, estimated, unknown } = p.always_on, total = counted + estimated;
  const names = new Map(p.items.map((i) => [i.id, i.name]));
  return <>
    <section aria-labelledby="preview-title">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <h3 id="preview-title" className="min-w-0 text-sm font-medium [overflow-wrap:anywhere]">If you install {p.pack.name}</h3>
        {p.already_installed && <Badge variant="warn">Already installed</Badge>}
      </div>
      <p className="mt-1 text-xs leading-[1.4] text-text-3"><span className="font-mono tabular-nums">{p.items.length}</span> Items · about <span className="font-mono tabular-nums">{total.toLocaleString()}</span> tokens every session</p>
      <p className="text-xs leading-[1.4] text-text-3"><span className="font-mono tabular-nums">{counted.toLocaleString()}</span> counted, <span className="font-mono tabular-nums">{estimated.toLocaleString()}</span> estimated from text length</p>
      {unknown > 0 && <p className="text-xs leading-[1.4] text-text-3"><span className="font-mono tabular-nums">{unknown}</span> MCP servers or hooks: unknown until installed</p>}
      {!p.compared ? <p className="mt-2 text-[13px] leading-[1.4] text-text-2">Not compared with a saved scan.</p>
        : p.overlaps.length === 0 ? <p className="mt-2 text-[13px] leading-[1.4] text-text-2">No overlap with your setup found.</p>
        : <ul className="-mx-2 mt-2 flex flex-col gap-1">
          {p.overlaps.slice(0, TOP).map((o) => <li key={`${o.new_id}|${o.existing_id}`}>
            <Button variant="ghost" className="h-auto min-h-10 w-full min-w-0 justify-start gap-3 px-2 py-2 text-left font-normal whitespace-normal" onClick={() => onItem(o.existing_id)}>
              <span className="min-w-0 flex-1">
                <span className="block text-sm [overflow-wrap:anywhere]">{names.get(o.new_id) ?? o.new_id}</span>
                <span className="block text-xs text-text-3 [overflow-wrap:anywhere]">and your {o.existing_name}</span>
              </span>
              <span className="shrink-0 text-xs text-text-3">{o.why}</span>
            </Button>
          </li>)}
        </ul>}
      {p.overlaps.length > TOP && p.compared && <p className="mt-1 text-xs text-text-3">+ {p.overlaps.length - TOP} more</p>}
      <p className="mt-2 text-xs leading-[1.4] text-text-3">Read locally. Nothing was run or sent.</p>
    </section>
    <Separator />
  </>;
}
