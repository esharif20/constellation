import { CheckIcon, CircleHelpIcon, CircleMinusIcon, CopyIcon, EyeIcon, PowerIcon, type LucideIcon } from "lucide-react";
import type { Tone, Verdict as V } from "@/lib/verdict";
import { cn } from "@/lib/utils";

// Static class strings so Tailwind sees them. Icon and word carry the meaning; colour is the 10% tint of the same tone.
const TONE: Record<Tone, string> = {
  off: "border-line-1 bg-surface-2 text-text-3",
  destructive: "border-destructive/30 bg-destructive/10 text-destructive",
  warn: "border-warn/30 bg-warn/10 text-warn",
  keep: "border-indigo-bright/30 bg-indigo-bright/10 text-indigo-bright",
  none: "border-line-1 bg-surface-2 text-text-3",
};
const ICON: Record<string, LucideIcon> = { "Switched off": PowerIcon, "Keep one": CopyIcon, "Keep the wrapped one": CopyIcon, "Could go": CircleMinusIcon, Review: EyeIcon, Keep: CheckIcon, "Not enough data": CircleHelpIcon };

export function VerdictBanner({ verdict: v }: { verdict: V }) {
  const Icon = ICON[v.label];
  return (
    <div className="mt-4 animate-fade-in">
      <p className={cn("flex items-start gap-2 rounded-lg border px-3 py-2 text-[13px] leading-[1.45]", TONE[v.tone])}>
        <Icon aria-hidden className="mt-0.5 size-4 shrink-0" />
        <span className="min-w-0">
          <span className="sr-only">Verdict: </span>
          <b className="font-semibold">{v.label}</b>
          <span className="text-foreground"> · {v.why}</span>
        </span>
      </p>
      {v.basis && <p className="mt-1.5 text-xs text-text-3">Transcripts can be deleted, so &ldquo;never seen&rdquo; is a hint.</p>}
    </div>
  );
}
