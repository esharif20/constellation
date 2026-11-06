// "Your use" and "Compared with your others": plain sentences from counts the server already computed. No thresholds decide a
// verdict here (verdict.py does); these only say what happened. Pure, local, no dates beyond the scan's own last_used day.
import { day, noun, projectUses, type GNode, type Habit, type Habits, type Model } from "@/graph/model";

export type Line = { label: string; text: string };
const TREND = { new: "New: not enough days yet to see a pattern.", rising: "Rising: used more lately.", steady: "Steady.", fading: "Fading: used less lately." } as const;
const MIN_USES = 3; // below this, the gap and trend would be guesses
const SHARE = 0.6;

const days = (n: number) => noun(Math.round(n), "active day");

export function yourUse(item: GNode, habit: Habit | undefined, habits: Habits | null, model: Pick<Model, "projects" | "currentProject">): { lines: Line[]; thin: boolean } {
  const u = item.usage;
  if (!u) return { lines: [], thin: false };
  const lines: Line[] = [];
  if (u.count === 0) {
    lines.push({ label: "Uses", text: habits ? `None in ${noun(habits.activeDays, "active day")}.` : "None seen in the transcripts." });
    return { lines, thin: !habits || habits.activeDays < 14 };
  }
  const span = habit ? ` on ${noun(habit.days_used, "active day")}${habits ? ` and in ${habit.sessions_used} of ${noun(habits.sessions, "session")}` : ""}` : "";
  lines.push({ label: "Uses", text: `${noun(u.count, "time")}${span}.` });
  if (u.last_used) lines.push({ label: "Last used", text: `${day(u.last_used)}${habit?.idle_active_days != null ? ` (${habit.idle_active_days === 0 ? "an active day today" : `${days(habit.idle_active_days)} ago`})` : ""}` });
  const thin = !habit || u.count < MIN_USES;
  if (habit?.trend && !thin) lines.push({ label: "Trend", text: TREND[habit.trend] });
  if (habit?.mean_gap != null) {
    const over = habit.idle_active_days != null && habit.idle_active_days > habit.mean_gap * 2;
    lines.push({ label: "Usual gap", text: `About ${days(habit.mean_gap)} between uses${over ? `. Overdue: ${days(habit.idle_active_days!)} since the last one.` : "."}` });
  }
  const where = projectUses(item, model);
  const total = where?.reduce((s, r) => s + r.count, 0) ?? 0;
  if (where && total >= MIN_USES && where[0].label !== "another project" && where[0].count / total >= SHARE) lines.push({ label: "Where", text: `Used mostly in ${where[0].label}.` });
  return { lines, thin };
}

const plural = (k: string) => `${k === "mcp_server" ? "MCP server" : k.replace(/_/g, " ")}s`;

// Rank among the same kind, and which of an overlapping pair gets used more. Counts come from the scan; the twin is the one the engine compared.
export function compared(item: GNode, habit: Habit | undefined, twin: GNode | undefined): Line[] {
  const lines: Line[] = [];
  if (habit?.percentile != null && item.usage) {
    const p = habit.percentile;
    lines.push({ label: "Rank", text: p >= 50 ? `Used more than ${p}% of your ${plural(item.kind)}.` : `Used less than ${100 - p}% of your ${plural(item.kind)}.` });
  }
  if (twin?.usage && item.usage) {
    const a = item.usage.count, b = twin.usage.count;
    lines.push({ label: "Twin", text: a === b ? `You use ${twin.name} and this one equally (${noun(a, "use")} each).` : `You use ${a > b ? "this one" : twin.name} more (${noun(Math.max(a, b), "use")} against ${Math.min(a, b)}).` });
  }
  return lines;
}

export type Next = { kind: "checklist" | "pin" | "twin" | "describe" | null; label: string };
// The one sensible next step, read from the server's action. The checklist button needs a Brief row; otherwise a removal falls back to pin or nothing.
export function nextStep(action: string, tier: string | null, hasRow: boolean, pinned: boolean): Next {
  if (["remove", "disable_plugin", "remove_twin", "use_underlying", "move_to_project"].includes(action) && hasRow) return { kind: "checklist", label: "Add to cleanup checklist" };
  if (action === "remove_twin" || action === "use_underlying") return { kind: "twin", label: "Review the twin" };
  if (action === "fix_description") return { kind: "describe", label: "Fix the description" };
  if (!pinned && (tier === "keep" || tier === "keep_rare" || tier === "review")) return { kind: "pin", label: "Pin as keep" };
  return { kind: null, label: "" };
}
