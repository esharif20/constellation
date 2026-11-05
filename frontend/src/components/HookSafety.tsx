import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { HookRow } from "@/graph/lenses";

const SHOWN = 6;
const WHEN: Record<string, string> = { before_prompt: "Runs on every prompt you send", session_start: "Runs once when a session starts", each_tool_call: "Runs around every tool call", other: "Runs on other events" };

// Plain-English line for one hook: when it runs, whether it can stop your work, how heavy it is. Never the command text.
export function hookLine(row: HookRow): string {
  const parts = [WHEN[row.phase] ?? WHEN.other];
  if (row.can_block) parts.push("can stop or change what happens");
  else parts.push("only observes");
  if (row.runs === "mcp_tool") parts.push("calls an MCP tool");
  return parts.join(" · ");
}

export function hookWeight(row: HookRow): string | null {
  if (row.tokens != null) return `${row.tokens.toLocaleString()} tokens`;
  if (row.bytes != null) return `${row.bytes.toLocaleString()} bytes`;
  return null;
}

export function HookSafety({ rows, onItem }: { rows: HookRow[]; onItem: (id: string) => void }) {
  const [all, setAll] = useState(false);
  const shown = all ? rows : rows.slice(0, SHOWN);
  const blockers = rows.filter((r) => r.can_block && r.phase === "before_prompt").length;
  return <section aria-label="Hook safety">
    <h3 className="text-xs font-medium tracking-[0.02em] text-text-3">Hook safety</h3>
    {rows.length === 0 ? <p className="mt-2 text-[13px] leading-[1.4] text-text-2">No hooks found, so nothing runs automatically around your prompts.</p> : <>
      <p className="mt-1 text-sm font-medium">{rows.length} {rows.length === 1 ? "hook runs" : "hooks run"} automatically{blockers > 0 && <>, {blockers} can block your prompt</>}</p>
      <p className="mt-1 text-xs leading-[1.4] text-text-3">Hooks are small programs Claude runs for you. The ones that run on your prompt come first.</p>
      <ul className="-mx-2 mt-2 flex flex-col gap-1">
        {shown.map((row) => {
          const weight = hookWeight(row);
          return <li key={row.id}><Button variant="ghost" className="h-auto min-h-10 w-full min-w-0 justify-start gap-3 px-2 py-2 text-left font-normal whitespace-normal" onClick={() => onItem(row.id)}>
            <span aria-hidden className="glyph" data-kind="hook" />
            <span className="min-w-0 flex-1"><span className="block truncate text-sm">{row.name}</span><span className="block text-xs leading-[1.4] text-text-3">{hookLine(row)}</span></span>
            <span className="shrink-0 text-right font-mono text-xs tabular-nums">{weight ?? <i className="font-sans text-text-3">unknown</i>}</span>
          </Button></li>;
        })}
      </ul>
      {rows.length > SHOWN && <Button variant="ghost" size="sm" className="mt-1" aria-expanded={all} onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${rows.length}`}</Button>}
    </>}
  </section>;
}
