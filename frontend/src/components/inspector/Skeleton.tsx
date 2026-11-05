import { kindName, type GNode } from "@/graph/model";

// Suspense fallback while the lazy Inspector chunk loads: the name at once, a shimmer under it only after 150 ms, same shell so nothing jumps.
export function InspectorSkeleton({ item }: { item: GNode }) {
  return (
    <aside aria-hidden className="glass fixed inset-x-0 bottom-0 flex max-h-[58dvh] flex-col rounded-t-2xl border border-b-0 px-4 pt-6 pb-6 shadow-(--shadow-float) sm:inset-x-auto sm:top-[76px] sm:right-4 sm:bottom-4 sm:max-h-none sm:w-[380px] sm:rounded-xl sm:border-b sm:px-6">
      <p className="min-h-7 text-xs font-medium text-text-3">{kindName(item.kind)}</p>
      <h2 className="mt-2 mb-1 font-serif text-[26px] leading-[1.1] [overflow-wrap:anywhere] sm:text-[30px]">{item.name}</h2>
      <div className="mt-6 space-y-3 [animation:fade-in_200ms_150ms_backwards]">
        {[88, 64, 76].map((w) => <div key={w} className="h-4 animate-pulse rounded bg-surface-3" style={{ width: `${w}%` }} />)}
      </div>
    </aside>
  );
}
