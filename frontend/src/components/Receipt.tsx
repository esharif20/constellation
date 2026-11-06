import { Button } from "@/components/ui/button";
import type { Receipt as ReceiptData, ReceiptGroup } from "@/graph/lenses";
import { kindName } from "@/graph/model";

const TOP = 5;
const PLURAL: Record<string, string> = { hook: "Hooks", memory: "CLAUDE.md", skill: "Skills", agent: "Agents", command: "Commands", mcp_server: "MCP servers", connector: "Connectors" };
const groupName = (kind: string) => PLURAL[kind] ?? kindName(kind);
const tokens = (n: number) => `${n.toLocaleString()} tokens`;

export function Receipt({ data, onItem }: { data: ReceiptData; onItem: (id: string) => void }) {
  const segments = data.groups.filter((g): g is ReceiptGroup & { tokens: number } => g.tokens != null && g.tokens > 0);
  const total = data.total_tokens;
  return <section aria-label="Before your first prompt">
    <h3 className="text-xs font-medium tracking-[0.02em] text-text-3">Before your first prompt</h3>
    {data.rows.length === 0 ? <p className="mt-2 text-[13px] leading-[1.4] text-text-2">Nothing loads before your first prompt.</p> : <>
      <p className="mt-1 text-sm font-medium">{total == null ? "Token counts not measured yet" : <><span className="font-mono tabular-nums">{total.toLocaleString()}</span> tokens load before you type</>}</p>
      {total != null && total > 0 && <>
        <div role="img" aria-label={segments.map((g) => `${groupName(g.kind)} ${tokens(g.tokens)}`).join(", ")} className="mt-2 flex h-2 gap-0.5 overflow-hidden rounded-full">
          {segments.map((g) => <span key={g.kind} className="h-full min-w-0.5" style={{ flexGrow: g.tokens, flexBasis: 0, background: `var(--k-${g.kind})` }} />)}
        </div>
        <ul aria-hidden className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-text-3">
          {segments.map((g) => <li key={g.kind} className="flex items-center gap-1.5"><span className="glyph" data-kind={g.kind} />{groupName(g.kind)} <span className="font-mono tabular-nums">{g.tokens.toLocaleString()}</span></li>)}
        </ul>
      </>}
      {data.uncounted_bytes > 0 && <p className="mt-2 text-xs leading-[1.4] text-text-3">+ <span className="font-mono tabular-nums">{data.uncounted_bytes.toLocaleString()}</span> bytes from hooks and CLAUDE.md not counted as tokens</p>}
      {data.unknown > 0 && <p className="mt-1 text-xs leading-[1.4] text-text-3">{data.unknown} unknown, including MCP tool schemas (not measured yet)</p>}
      {data.groups.some((g) => g.kind === "connector") && <p className="mt-1 text-xs leading-[1.4] text-text-3">MCP servers connected through claude.ai are only seen in transcripts</p>}
      <ul className="-mx-2 mt-2 flex flex-col gap-1">
        {data.rows.slice(0, TOP).map((row) => {
          const value = row.tokens != null ? tokens(row.tokens) : row.bytes != null ? `${row.bytes.toLocaleString()} bytes` : null;
          const body = <>
            <span aria-hidden className="glyph" data-kind={row.kind} />
            <span className="min-w-0 flex-1 truncate text-sm">{row.name}</span>
            <span className="shrink-0 text-right font-mono text-xs tabular-nums">{value ?? <i className="font-sans text-text-3">unknown</i>}</span>
          </>;
          return <li key={row.id ?? row.name}>{row.id == null
            ? <div className="flex min-h-10 items-center gap-3 px-2 py-2">{body}</div>
            : <Button variant="ghost" className="h-auto min-h-10 w-full min-w-0 justify-start gap-3 px-2 py-2 text-left font-normal whitespace-normal" onClick={() => onItem(row.id!)}>{body}</Button>}</li>;
        })}
      </ul>
    </>}
  </section>;
}
