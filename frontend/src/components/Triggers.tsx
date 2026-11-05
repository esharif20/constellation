import { Button } from "@/components/ui/button";
import type { TriggerRow, Triggers as TriggersData } from "@/graph/lenses";

const TOP = 8;
const times = (n: number) => `${n} ${n === 1 ? "time" : "times"}`;

// Plain-English reason for one row, from the flags and counts the API returns.
export function reasons(row: TriggerRow, files: number): string[] {
  const out: string[] = [];
  if (row.flags.includes("never")) out.push(`Never used in your last ${files} session ${files === 1 ? "file" : "files"}.`);
  if (row.flags.includes("vague")) out.push("Its description is very short, so Claude may not know when to pick it.");
  if (row.flags.includes("greedy")) out.push(`Used ${times(row.count)}, far more than your other skills. Its description may be too broad.`);
  return out;
}

export function Triggers({ data, onItem }: { data: TriggersData; onItem: (id: string) => void }) {
  return <section aria-label="Skills that never fire or fire too often">
    <h3 className="text-xs font-medium tracking-[0.02em] text-text-3">Skills that never fire or fire too often</h3>
    {data.files === 0 ? <p className="mt-2 text-[13px] leading-[1.4] text-text-2">No session history to check yet, so usage is not known.</p>
      : data.rows.length === 0 ? <p className="mt-2 text-[13px] leading-[1.4] text-text-2">Nothing found. Your skills all fire a reasonable amount.</p>
      : <ul className="-mx-2 mt-2 flex flex-col gap-1">
        {data.rows.slice(0, TOP).map((row) => <li key={row.id}>
          <Button variant="ghost" className="h-auto min-h-10 w-full min-w-0 justify-start gap-3 px-2 py-2 text-left font-normal whitespace-normal" onClick={() => onItem(row.id)}>
            <span aria-hidden className="glyph" data-kind="skill" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm">{row.name}</span>
              {reasons(row, data.files).map((r) => <span key={r} className="block text-xs leading-[1.4] text-text-3">{r}</span>)}
            </span>
          </Button>
        </li>)}
      </ul>}
    {data.rows.length > TOP && <p className="mt-1 text-xs text-text-3">+ {data.rows.length - TOP} more</p>}
  </section>;
}
