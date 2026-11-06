import type { BriefData, BriefRow } from "@/graph/model";

type Legacy = { cost: { rows: (BriefRow & { tokens_saved: number | null })[]; frees: number | null }; pairs: { rows: BriefRow[] }; scope?: BriefData["scope"]; checklist?: BriefData["checklist"] };
const arr = (x: unknown): x is unknown[] => Array.isArray(x);

// Accepts the new shape (safe / look / wait / range). shortcut: an older server still sends cost / pairs; it is shown as one
// ungrouped list ("Worth a look") with no range. Delete the legacy branch when slice S4 has wired the new /api/brief.
export function briefFrom(data: unknown): BriefData | null {
  const d = data as Partial<BriefData> & Partial<Legacy>;
  if (arr(d?.safe?.rows) && arr(d?.look?.rows) && arr(d?.wait?.rows) && d.range) return d as BriefData;
  if (!arr(d?.cost?.rows) || !arr(d?.pairs?.rows)) return null;
  const rows = [...d.pairs.rows, ...d.cost.rows].map((r) => ({ ...r, saves: r.saves ?? r.tokens_saved ?? null }));
  return { safe: { rows: [] }, look: { rows }, wait: { summary: [], rows: [] }, range: { low: 0, high: 0, unknown: 0 }, scope: d.scope, checklist: d.checklist };
}
