// The Inspector's verdict: a thin reader of the server's assessments (smarter-verdict.md 4.1, 4.4). No thresholds, no dates,
// no usage maths here: src/constellation/verdict.py decides, this file maps a tier to a tone and passes the words through.
// DORMANT_DAYS is gone with the old local rules. tests/test_chat_ask.py (the DORMANT_DAYS parity check, lines ~50-54) reads this
// file for it and must be deleted by slice S4 together with answer.py's own constant (smarter-verdict.md 12).
import type { Assessment, Confidence, GNode, Tier } from "@/graph/model";

export type Tone = "off" | "destructive" | "warn" | "keep" | "none";
export type Verdict = {
  tone: Tone; label: string; why: string; // why: the first reason
  more: string[]; // the other reasons (at most two), shown smaller
  tier: Tier | null; confidence: Confidence | null; action: string; saves: number | null; recheck: number | null; twin: string | null; // twin: the id of the Item compared (remove_twin)
  basis: boolean; // a reason rests on "never seen", which deleted transcripts can fake
};

const TONE: Record<Tier, Tone> = { keep: "keep", keep_rare: "keep", review: "warn", too_early: "warn", redundant: "destructive", could_go: "destructive", off: "off", untracked: "none" };
const MAX_WHY = 90;
const clip = (s: string) => (s.length > MAX_WHY ? `${s.slice(0, MAX_WHY - 1)}…` : s);

export function verdictOf(item: GNode, assessments: Record<string, Assessment> | undefined): Verdict {
  const a = assessments?.[item.id];
  if (!a) return { tone: "none", label: "Not enough data", why: "No verdict from this scan yet. Scan again with a current Constellation.", more: [], tier: null, confidence: null, action: "none", saves: null, recheck: null, twin: null, basis: false };
  const [first, ...rest] = a.reasons;
  return {
    tone: TONE[a.tier], label: a.label, why: clip(first?.text ?? ""), more: rest.slice(0, 2).map((r) => clip(r.text)),
    tier: a.tier, confidence: a.confidence, action: a.action, saves: a.saves, recheck: a.recheck_after, twin: a.twin_id ?? null,
    basis: a.reasons.some((r) => r.code === "never_seen" || r.code === "duplicate_loser"),
  };
}
