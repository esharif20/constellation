import { CheckIcon, CircleHelpIcon, CircleMinusIcon, CopyIcon, EyeIcon, HourglassIcon, PowerIcon, type LucideIcon } from "lucide-react";
import type { GNode, Model, Tier } from "@/graph/model";
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
const ICON: Record<Tier, LucideIcon> = { keep: CheckIcon, keep_rare: CheckIcon, review: EyeIcon, redundant: CopyIcon, could_go: CircleMinusIcon, too_early: HourglassIcon, off: PowerIcon, untracked: CircleHelpIcon };
const CONFIDENCE = { high: "High confidence", medium: "Medium confidence", low: "Low confidence" } as const;
const LEVEL = { high: 3, medium: 2, low: 1 } as const;
const REMOVING = new Set(["remove", "remove_twin", "disable_plugin", "use_underlying"]);

// What taking the action would touch. All of it comes from the graph and the assessment; nothing is decided here.
export function ifRemoved(item: GNode, verdict: V, model: Pick<Model, "links">): string[] | null {
  if (!REMOVING.has(verdict.action)) return null;
  const lines = [verdict.saves == null ? "How many tokens it frees is unknown." : `Frees about ${verdict.saves.toLocaleString()} tokens at the start of every session.`];
  const callers = [...new Set(model.links.filter((l) => l.target === item && l.kind !== "contains").map((l) => l.source.name))];
  lines.push(callers.length ? `${callers.slice(0, 3).join(", ")}${callers.length > 3 ? ` and ${callers.length - 3} more` : ""} ${callers.length === 1 ? "points" : "point"} at it and would lose it.` : "Nothing else in your setup points at it.");
  const parts = model.links.filter((l) => l.source === item && l.kind === "contains").length;
  if (parts) lines.push(`It turns off all ${parts} of its parts together.`);
  return lines;
}

export function VerdictBanner({ verdict: v, item, model }: { verdict: V; item: GNode; model: Pick<Model, "links"> }) {
  const Icon = v.tier ? ICON[v.tier] : CircleHelpIcon;
  const removed = ifRemoved(item, v, model);
  return (
    <div className="mt-4 animate-fade-in">
      <div className={cn("rounded-lg border px-3 py-2 text-[13px] leading-[1.45]", TONE[v.tone])}>
        <p className="flex items-start gap-2">
          <Icon aria-hidden className="mt-0.5 size-4 shrink-0" />
          <span className="min-w-0 flex-1">
            <span className="sr-only">Verdict: </span>
            <b className="font-semibold">{v.label}</b>
            <span className="text-foreground"> · {v.why}</span>
          </span>
        </p>
        {v.confidence && <p className="mt-1.5 flex items-center gap-1.5 pl-6 text-xs text-text-2">
          <span aria-hidden className="flex gap-0.5">{[1, 2, 3].map((n) => <i key={n} className={cn("size-1.5 rounded-full", n <= LEVEL[v.confidence!] ? "bg-current" : "bg-line-2")} />)}</span>
          {CONFIDENCE[v.confidence]}
        </p>}
      </div>
      {v.more.length > 0 && <ul className="mt-1.5 list-disc pl-5 text-xs leading-[1.45] text-text-3">{v.more.map((t) => <li key={t}>{t}</li>)}</ul>}
      {v.recheck != null && v.recheck > 0 && <p className="mt-1.5 text-xs text-text-3">Check back after about {v.recheck} more days you use Claude Code.</p>}
      {v.basis && <p className="mt-1.5 text-xs text-text-3">Transcripts can be deleted, so &ldquo;never seen&rdquo; is a hint.</p>}
      {removed && <section aria-label="If removed" className="mt-3 rounded-lg border border-line-1 px-3 py-2">
        <h3 className="text-xs font-medium text-text-3">If removed</h3>
        <ul className="mt-1 list-disc pl-4 text-[13px] leading-[1.45] text-text-2">{removed.map((t) => <li key={t}>{t}</li>)}</ul>
      </section>}
    </div>
  );
}
