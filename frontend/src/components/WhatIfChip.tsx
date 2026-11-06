import { XIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Pane } from "@/components/Motion";

// Desktop only: the Brief's meter is hidden (cluster focus, chat, collapsed), so the preview stays visible and can be ended.
export function WhatIfChip({ count, saved, onReset, onExit }: { count: number; saved: number; onReset: () => void; onExit: () => void }) {
  return <Pane from="bottom" role="group" aria-label="What-if" className="glass fixed bottom-28 left-1/2 z-10 hidden h-10 -translate-x-1/2 items-center gap-1 rounded-full border pr-1 pl-4 text-[13px] shadow-(--shadow-float) sm:flex">
    <span className="whitespace-nowrap">What-if: {count} removed · <span className="font-mono tabular-nums text-indigo-bright">−{saved.toLocaleString()}</span> tokens</span>
    <Button variant="ghost" className="h-8 rounded-full px-3 text-[13px]" onClick={onReset}>Reset</Button>
    <Button variant="ghost" size="icon" className="size-8 rounded-full" aria-label="Exit what-if" onClick={onExit}><XIcon aria-hidden /></Button>
  </Pane>;
}
