import { ChevronRightIcon } from "lucide-react";
import type { GNode, Habit, Habits, Model } from "@/graph/model";
import { compared, yourUse, type Line } from "@/lib/yours";
import { whatFor } from "@/lib/purpose";

export function WhatFor({ item, model }: { item: GNode; model: Pick<Model, "links"> }) {
  const text = whatFor(item, model);
  if (text === item.label) return null; // the header already says exactly this
  return (
    <section aria-label="What it is for" className="mt-3">
      <h3 className="text-xs font-medium tracking-[0.02em] text-text-3">What it&rsquo;s for</h3>
      <p className="mt-0.5 max-w-[65ch] text-sm leading-[1.5] text-foreground [overflow-wrap:anywhere]">{text}</p>
    </section>
  );
}

const Rows = ({ title, lines }: { title?: string; lines: Line[] }) => (
  <section className="mt-3 first:mt-0">
    {title && <h4 className="text-xs font-medium text-text-3">{title}</h4>}
    <dl className="mt-1">{lines.map((l) => (
      <div key={l.label} className="flex gap-3 py-1 text-[13px] leading-[1.45]">
        <dt className="w-20 shrink-0 text-text-3">{l.label}</dt>
        <dd className="min-w-0 text-text-2 [overflow-wrap:anywhere]">{l.text}</dd>
      </div>
    ))}</dl>
  </section>
);

// One disclosure, closed by default: the Inspector stays calm and the detail is a Tab and Enter away.
export function Yours({ item, model, habits, twin }: { item: GNode; model: Pick<Model, "projects" | "currentProject">; habits: Habits | null; twin?: GNode }) {
  const habit: Habit | undefined = habits?.items[item.id];
  const use = yourUse(item, habit, habits, model), cmp = compared(item, habit, twin);
  if (!use.lines.length && !cmp.length) return null;
  return (
    <details className="group mt-4 rounded-lg border border-line-1 px-3 py-1">
      <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 rounded-md text-[13px] text-text-2 outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 sm:min-h-10 [&::-webkit-details-marker]:hidden">
        <ChevronRightIcon aria-hidden className="size-4 shrink-0 text-text-3 transition-transform duration-(--t-fast) ease-(--ease-out) group-open:rotate-90" />
        <span className="shrink-0 font-medium text-foreground">Your use</span>
        <span className="min-w-0 truncate text-text-3">{use.lines[0]?.text ?? cmp[0]?.text}</span>
      </summary>
      <div className="animate-fade-in pt-1 pb-2">
        {use.lines.length > 0 && <Rows lines={use.lines} />}
        {use.thin && use.lines.length > 0 && <p className="mt-2 text-xs text-text-3">Not enough history yet to read much into this.</p>}
        {cmp.length > 0 && <Rows title="Compared with your others" lines={cmp} />}
      </div>
    </details>
  );
}
