// Scan history for the time-lapse chart (#62). Dates and counts only; the server never sends hashes, the setup key or a path.
import { day } from "./model.ts";

export type HistoryEntry = { date: string; items: number; always_on: number; unknown: number; added: number; removed: number; gone: number };
export type Timeline = { entries: HistoryEntry[]; first_seen: Record<string, string> };
export type Box = { left: number; right: number; top: number; bottom: number }; // bottom is the y of the zero baseline
export type ChartPoint = { x: number; y: number; entry: HistoryEntry; marker: boolean };

const DAY = 864e5;
const at = (iso: string) => Date.parse(`${iso}T00:00:00Z`);

export const maxTokens = (entries: HistoryEntry[]) => Math.max(1, ...entries.map((e) => e.always_on));

// x is proportional to the date (not the index); y runs from 0 at the baseline to the largest value at the top. One entry sits in the middle.
export function chartPoints(entries: HistoryEntry[], box: Box): ChartPoint[] {
  if (!entries.length) return [];
  const first = at(entries[0].date), span = at(entries[entries.length - 1].date) - first, top = maxTokens(entries);
  return entries.map((entry) => ({
    x: span > 0 ? box.left + ((at(entry.date) - first) / span) * (box.right - box.left) : (box.left + box.right) / 2,
    y: box.bottom - (entry.always_on / top) * (box.bottom - box.top),
    entry,
    marker: entry.added > 0,
  }));
}

export const changes = (e: HistoryEntry) => [e.added > 0 && `+${e.added}`, e.removed > 0 && `−${e.removed}`].filter(Boolean).join(" ");

// "4 Nov 2026 · 19,050 tokens · 212 Items · +3 −1"
export function hoverLine(e: HistoryEntry): string {
  return [day(e.date), `${e.always_on.toLocaleString("en-US")} tokens`, `${e.items} Items`, changes(e)].filter(Boolean).join(" · ");
}

export const spanDays = (entries: HistoryEntry[]) => (entries.length ? Math.round((at(entries[entries.length - 1].date) - at(entries[0].date)) / DAY) : 0);

// Items first seen after `date` are absent at that date; an id with no first_seen is treated as present. Dates are ISO, so string order is date order.
export const absentAt = <T extends { id: string }>(nodes: T[], firstSeen: Record<string, string>, date: string): Set<T> => new Set(nodes.filter((n) => (firstSeen[n.id] ?? "") > date));
