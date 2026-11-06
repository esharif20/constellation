import type { WeeklyData } from "@/graph/model";

const n = (v: number) => v.toLocaleString();
const range = (r: { low: number; high: number }) => (r.low === r.high ? n(r.low) : `${n(r.low)} to ${n(r.high)}`);
const when = (day: string) => new Date(`${day}T00:00:00Z`).toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: "UTC" });

// "This week" at the top of the Cleanup Brief: one glance (counts, session start, reclaimable range), the lists behind a disclosure.
export function Weekly({ data }: { data: WeeklyData }) {
  const s = data.session_start, r = data.reclaim, changed = data.added.length + data.removed.length + data.verdict_changes.length + data.went_quiet.length;
  const approx = s.unknown_now + s.unknown_then > 0;
  return <section aria-labelledby="weekly-title" data-testid="weekly">
    <div className="flex items-baseline justify-between gap-2">
      <h3 id="weekly-title" className="text-sm font-medium">This week</h3>
      <span className="text-xs text-text-3">since {when(data.since)}{data.days > 0 && <> · {data.days} {data.days === 1 ? "day" : "days"}</>}</span>
    </div>
    <p className="mt-1 flex flex-wrap gap-x-3 text-xs text-text-2">
      <span><b className="font-mono font-medium tabular-nums">{data.added.length}</b> added</span>
      <span><b className="font-mono font-medium tabular-nums">{data.removed.length}</b> removed</span>
      <span><b className="font-mono font-medium tabular-nums">{data.went_quiet.length}</b> went quiet</span>
    </p>
    <p className="mt-2 text-[13px] leading-[1.45]">
      <span className="text-text-3">Session start </span>
      {s.delta == null || s.then == null || s.now == null
        ? <i className="text-text-3">not measured</i>
        : <><span className="font-mono tabular-nums">{n(s.then)} → {n(s.now)}</span> <span className="font-mono text-xs tabular-nums text-text-2">({s.delta > 0 ? "+" : s.delta < 0 ? "−" : "±"}{n(Math.abs(s.delta))})</span></>}
    </p>
    {approx && s.delta != null && <p className="mt-1 text-xs leading-[1.4] text-text-3">Known costs only: {s.unknown_then} → {s.unknown_now} with unknown cost.</p>}
    <p className="mt-1 text-[13px] leading-[1.45]">
      <span className="text-text-3">Could free </span><b className="font-mono font-medium tabular-nums">{range(r.now)}</b><span className="text-text-3"> tokens</span>
      <span className="text-xs text-text-2"> · {r.now.confidence} confidence</span>
    </p>
    <p className="mt-1 text-xs leading-[1.4] text-text-3">Last time {range(r.then)}.{r.now.unknown > 0 && ` + ${r.now.unknown} with unknown cost, not counted.`}</p>
    {(changed > 0 || data.used_most.length > 0) && <details className="group mt-1">
      <summary className="flex h-10 cursor-pointer items-center text-xs text-text-2">What changed</summary>
      <div className="flex flex-col gap-3 pb-1 text-xs leading-[1.45]">
        <Names title="Added" rows={data.added} />
        <Names title="Removed" rows={data.removed} />
        <Names title="Went quiet" rows={data.went_quiet} />
        {data.verdict_changes.length > 0 && <div>
          <h4 className="font-medium text-text-2">Verdicts that moved</h4>
          <ul className="mt-1 flex flex-col gap-1.5 text-text-3">
            {data.verdict_changes.map((c) => <li key={`${c.kind}:${c.name}`}><span className="text-text-2 [overflow-wrap:anywhere]">{c.name}</span> · {c.from} → {c.to}<span className="block">{c.why}</span></li>)}
          </ul>
        </div>}
        {data.used_most.length > 0 && <div>
          <h4 className="font-medium text-text-2">Used most</h4>
          <ul className="mt-1 flex flex-col gap-1 text-text-3">
            {data.used_most.map((u) => <li key={`${u.kind}:${u.name}`} className="flex justify-between gap-3"><span className="min-w-0 [overflow-wrap:anywhere]">{u.name}</span><span className="shrink-0 font-mono tabular-nums">{u.uses}<span className="sr-only"> sessions</span></span></li>)}
          </ul>
        </div>}
      </div>
    </details>}
  </section>;
}

function Names({ title, rows }: { title: string; rows: { kind: string; name: string }[] }) {
  if (!rows.length) return null;
  return <div>
    <h4 className="font-medium text-text-2">{title} ({rows.length})</h4>
    <ul className="mt-1 flex flex-col gap-1 text-text-3">{rows.map((x) => <li key={`${x.kind}:${x.name}`} className="[overflow-wrap:anywhere]">{x.name} <span className="text-text-3/80">· {x.kind}</span></li>)}</ul>
  </div>;
}
