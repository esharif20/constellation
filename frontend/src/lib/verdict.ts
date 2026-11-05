// The Inspector's local verdict (docs/design/inspector.md section 2). Pure: no provider call, nothing sent. First match wins.
// Wording matches chat-answers.md: "could", never "should delete".
import { day, noun, type GNode, type GOverlap, type UsageWindow } from "@/graph/model";

export const DORMANT_DAYS = 30; // the owner's open decision (ask-purpose.md 6.3): one constant

export type Tone = "off" | "destructive" | "warn" | "keep" | "none";
export type Verdict = { tone: Tone; label: string; why: string; basis: boolean }; // basis: the verdict rests on "never seen", which transcripts can fake

const MAX_WHY = 90;
const clip = (s: string) => (s.length > MAX_WHY ? `${s.slice(0, MAX_WHY - 1)}…` : s);
const days = (w: UsageWindow | null) => (w?.first && w.last ? Math.round((Date.parse(w.last) - Date.parse(w.first)) / 864e5) + 1 : null);
const every = (n: number | null | undefined) => (n ? `costs ${n.toLocaleString()} tokens every session` : "");

export function verdictOf(item: GNode, overlaps: GOverlap[], children: GNode[], window: UsageWindow | null): Verdict {
  const v = (tone: Tone, label: string, why: string, basis = false): Verdict => ({ tone, label, why: clip(why), basis });
  if (item.disabled) return v("off", "Switched off", item.kind === "plugin" ? "Disabled in enabledPlugins; the scan still counts its cost." : "Disabled; the scan still counts its cost.");
  const dup = overlaps.find((o) => o.verdict === "duplicate");
  if (dup) return v("destructive", "Keep one", `Does the same job as ${dup.a === item ? dup.b.name : dup.a.name}.`);
  const wrap = overlaps.find((o) => o.verdict === "wrapper" && o.a === item);
  if (wrap) return v("warn", "Keep the wrapped one", `Only calls ${wrap.b.name}.`);
  const cost = item.cost?.always_on, u = item.usage;
  if (u && cost && cost > 0) {
    const span = days(window);
    if (u.count === 0 && window?.files) return v("destructive", "Could go", `Not seen in ${span ? noun(span, "day") : noun(window.files, "transcript")} of sessions; ${every(cost)}.`, true);
    if (u.count > 0 && u.last_used && window?.last && (Date.parse(window.last) - Date.parse(u.last_used)) / 864e5 >= DORMANT_DAYS) return v("warn", "Review", `Last used ${day(u.last_used)}; ${every(cost)}.`, true);
  }
  if (u && u.count > 0) return v("keep", "Keep", usedLine(u.count, window), true);
  // A plugin with no Overlap rolls up its contents.
  const tracked = children.filter((c) => c.usage);
  const total = children.reduce((s, c) => s + (c.cost?.always_on ?? 0), 0);
  if (item.kind === "plugin" && tracked.length && window?.files && total > 0 && tracked.every((c) => c.usage!.count === 0)) {
    return v("destructive", "Could go", `None of its ${noun(tracked.length, "tracked part")} was seen; ${every(total)}.`, true);
  }
  if (u) return v("none", "Not enough data", window?.files ? "Never seen, but its cost is unknown." : "No transcripts scanned.");
  return v("none", "Not enough data", `Usage is not tracked for ${item.kind === "plugin" ? "plugins" : item.kind === "hook" ? "hooks" : "this kind"}.`);
}

const usedLine = (count: number, w: UsageWindow | null) => `Used ${noun(count, "time")}${days(w) ? ` in ${noun(days(w)!, "day")}` : ""}.`;
