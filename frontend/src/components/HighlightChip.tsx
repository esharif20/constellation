import { XIcon } from "lucide-react";

// Names who lit up the map and clears it: search and chat write the same highlight set.
export function HighlightChip({ highlight, onClear }: { highlight: { from: "chat" | "search"; count: number } | null; onClear: () => void }) {
  if (!highlight) return null;
  return (
    <div role="status" className="glass fixed top-[5.25rem] left-1/2 flex h-8 -translate-x-1/2 items-center gap-1 rounded-full border pr-1 pl-3 text-xs text-text-2 shadow-(--shadow-float) sm:top-4">
      <span>{highlight.count} highlighted <span className="text-text-3">· from {highlight.from}</span></span>
      <button type="button" onClick={onClear} aria-label={`Clear highlight from ${highlight.from}`} className="grid size-6 cursor-pointer place-items-center rounded-full text-text-3 hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"><XIcon aria-hidden className="size-3.5" /></button>
    </div>
  );
}
