import { CheckIcon, CopyIcon, ListPlusIcon, MessageCircleIcon, PinIcon, SearchIcon, TriangleAlertIcon, GitCompareIcon, PencilLineIcon } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { BriefData, BriefRow, GNode } from "@/graph/model";
import type { Next } from "@/lib/yours";

type Props = { item: GNode; instruction: string; brief?: BriefData; next?: Next; pinned?: boolean; twin?: GNode; onAsk?: (text: string) => void; onFind?: (name: string) => void; onSelect?: (n: GNode) => void; className?: string };
type State = "idle" | "copied" | "added" | "pinned" | "failed";

// Only safe and look rows can be added (scope and wait rows answer 404). Rows that name this Item alone come first.
export const briefRow = (brief: BriefData | undefined, item: GNode): BriefRow | undefined =>
  brief && [...brief.safe.rows, ...brief.look.rows].sort((a, b) => a.item_ids.length - b.item_ids.length).find((r) => r.item_ids.includes(item.id));

const BTN = "h-11 gap-1.5 px-2 text-[13px] font-normal sm:h-10";

// Primary first (the one sensible next step), then the quieter ones, so Tab reaches the likely action first. Every button hides when its
// feature is missing. The sheet pins this row to its bottom on phones (inspector.md section 5/7).
export function Actions({ item, instruction, brief, next, pinned = false, twin, onAsk, onFind, onSelect, className }: Props) {
  const row = brief?.checklist ? briefRow(brief, item) : undefined;
  const [state, setState] = useState<State>("idle");
  const [done, setDone] = useState<string | null>(null); // the row id added from here, so the button stays disabled
  const [pinDone, setPinDone] = useState(false);
  const added = !!row && (done === row.id || !!brief?.checklist?.ids.includes(row.id));
  const isPinned = pinned || pinDone;
  async function copy() {
    try { await navigator.clipboard.writeText(instruction); setState("copied"); } catch { setState("failed"); }
  }
  async function post(url: string, body: object, ok: () => void, then: State) {
    try {
      const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      if (!r.ok) throw new Error();
      ok();
      setState(then);
    } catch { setState("failed"); }
  }
  const kind = next?.kind ?? null;
  const primary = kind === "checklist" ? (row ? { icon: added ? CheckIcon : ListPlusIcon, label: added ? "On checklist" : next!.label, off: added, go: () => void post("api/checklist", { id: row.id }, () => setDone(row.id), "added") } : null)
    : kind === "pin" ? { icon: isPinned ? CheckIcon : PinIcon, label: isPinned ? "Pinned as keep" : next!.label, off: isPinned, go: () => void post("api/pin", { id: item.id }, () => setPinDone(true), "pinned") }
    : kind === "twin" && twin && onSelect ? { icon: GitCompareIcon, label: next!.label, off: false, go: () => onSelect(twin) }
    : kind === "describe" ? { icon: PencilLineIcon, label: next!.label, off: false, go: () => void copy() }
    : null;
  return (
    <div className={className}>
      <div className="flex flex-wrap gap-1.5">
        {primary && <Button className={`${BTN} w-full`} disabled={primary.off} onClick={primary.go}><primary.icon aria-hidden />{primary.label}</Button>}
        {onAsk && <Button variant="outline" className={BTN} aria-label="Ask about this" onClick={() => onAsk(`Should I keep ${item.name}?`)}><MessageCircleIcon aria-hidden />Ask</Button>}
        {onFind && <Button variant="outline" className={BTN} onClick={() => onFind(item.name)}><SearchIcon aria-hidden />Find similar</Button>}
        <Button variant="outline" className={BTN} aria-label="Copy instruction for Claude Code" onClick={() => void copy()}>
          {state === "copied" ? <CheckIcon aria-hidden /> : <CopyIcon aria-hidden />}{state === "copied" ? "Copied" : "Copy instruction"}
        </Button>
      </div>
      <span role="status" className="sr-only">{state === "copied" ? "Copied the instruction for Claude Code" : state === "added" ? "Added to cleanup checklist" : state === "pinned" ? "Pinned as keep" : ""}</span>
      {state === "failed" && <p role="alert" className="mt-2 flex items-center gap-1.5 text-xs text-warn"><TriangleAlertIcon aria-hidden className="size-3.5" />Could not do that. Try again.</p>}
    </div>
  );
}
