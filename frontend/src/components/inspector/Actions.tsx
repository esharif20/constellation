import { CheckIcon, CopyIcon, ListPlusIcon, MessageCircleIcon, TriangleAlertIcon } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { BriefData, BriefRow, Cluster, GNode } from "@/graph/model";

type Props = { item: GNode; instruction: string; brief?: BriefData; onAsk?: (text: string) => void; onCluster?: (c: Cluster) => void; className?: string };
type State = "idle" | "copied" | "added" | "had" | "failed";

// Only safe and look rows can be added (scope and wait rows answer 404). Rows that name this Item alone come first.
export const briefRow = (brief: BriefData | undefined, item: GNode): BriefRow | undefined =>
  brief && [...brief.safe.rows, ...brief.look.rows].sort((a, b) => a.item_ids.length - b.item_ids.length).find((r) => r.item_ids.includes(item.id));

const BTN = "h-11 gap-2 px-3 text-[13px] font-normal sm:h-10";

// Every button hides when its feature is missing. The sheet pins this row to its bottom on phones (inspector.md section 5/7).
export function Actions({ item, instruction, brief, onAsk, className }: Props) {
  const row = brief?.checklist ? briefRow(brief, item) : undefined;
  const [state, setState] = useState<State>("idle");
  const [done, setDone] = useState<string | null>(null); // the row id added from here, so the button stays disabled
  const added = !!row && (done === row.id || !!brief?.checklist?.ids.includes(row.id));
  async function copy() {
    try { await navigator.clipboard.writeText(instruction); setState("copied"); } catch { setState("failed"); }
  }
  async function add() {
    if (!row) return;
    try {
      const r = await fetch("api/checklist", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: row.id }) });
      if (!r.ok) throw new Error();
      setDone(row.id);
      setState("added");
    } catch { setState("failed"); }
  }
  return (
    <div className={className}>
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" className={`${BTN} max-sm:w-full`} onClick={() => void copy()}>
          {state === "copied" ? <CheckIcon aria-hidden /> : <CopyIcon aria-hidden />}{state === "copied" ? "Copied" : "Copy instruction for Claude Code"}
        </Button>
        {row && (
          <Button variant="outline" className={BTN} disabled={added} onClick={() => void add()}>
            {added ? <CheckIcon aria-hidden /> : <ListPlusIcon aria-hidden />}{added ? "On checklist" : "Add to checklist"}
          </Button>
        )}
        {onAsk && <Button variant="outline" className={BTN} onClick={() => onAsk(`Compare ${item.name} with `)}><MessageCircleIcon aria-hidden />Compare with…</Button>}
      </div>
      <span role="status" className="sr-only">{state === "copied" ? "Copied" : state === "added" ? "Added to checklist" : ""}</span>
      {state === "failed" && <p role="alert" className="mt-2 flex items-center gap-1.5 text-xs text-warn"><TriangleAlertIcon aria-hidden className="size-3.5" />Could not do that. Try again.</p>}
    </div>
  );
}
