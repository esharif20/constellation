import { cn } from "@/lib/utils";

// A 4px bar scaled to the scan's p95 cost; above it the bar is full and a "+" follows. Unknown has no bar at all (callers skip it).
export function MiniBar({ value, max, label, off }: { value: number; max: number; label: string; off?: boolean }) {
  return (
    <div className="mt-1.5 flex items-center gap-1.5">
      <div role="img" aria-label={label} className="h-1 min-w-0 flex-1 overflow-hidden rounded-full bg-line-1">
        <div className={cn("h-full origin-left animate-bar-grow rounded-full", off ? "bg-text-4" : "bg-indigo-bright")} style={{ width: `${Math.min(1, value / max) * 100}%` }} />
      </div>
      {value > max && <span aria-hidden className="font-sans text-xs leading-none text-text-3">+</span>}
    </div>
  );
}
