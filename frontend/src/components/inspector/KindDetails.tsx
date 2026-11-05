import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { kindName, noun, type GNode, type Model } from "@/graph/model";
import { hookInfo, pluginInfo } from "@/lib/details";

const unknown = <i className="text-text-3">unknown</i>;
const Row = ({ label, children }: { label: string; children: ReactNode }) => (
  <div className="flex flex-col gap-0.5 py-2 first:pt-0 last:pb-0 min-[360px]:flex-row min-[360px]:gap-3">
    <dt className="w-24 shrink-0 text-xs leading-[1.6] text-text-3">{label}</dt>
    <dd className="min-w-0 text-[13px] leading-[1.5] [overflow-wrap:anywhere]">{children}</dd>
  </div>
);

// Extra facts for hooks, MCP servers/connectors and plugins; other kinds have none (docs/design/inspector.md section 4).
export function KindDetails({ item, model }: { item: GNode; model: Model }) {
  const out = (kind: string) => model.links.filter((l) => l.source === item && l.kind === kind).map((l) => l.target);
  let rows: ReactNode = null, title = "";
  if (item.kind === "hook") {
    title = "Hook";
    const h = hookInfo(item), calls = out("triggers").filter((t) => t.kind === "mcp_server" || t.kind === "connector");
    rows = (
      <>
        <Row label="Event">{h.event ?? unknown}</Row>
        <Row label="Matcher">{h.matcher ?? unknown}</Row>
        {h.promptTime && <Row label="Timing">Runs before you type</Row>}
        {h.canBlock && <Row label="Can block">Yes. This event lets a hook stop the action.</Row>}
        {item.description && <Row label="Command"><code className="line-clamp-2 font-mono text-xs text-text-2">{item.description}</code></Row>}
        {calls.length > 0 && <Row label="Calls">{calls.map((c) => c.name).join(", ")}</Row>}
      </>
    );
  } else if (item.kind === "mcp_server" || item.kind === "connector") {
    title = kindName(item.kind);
    rows = (
      <>
        <Row label="Shape">{item.description ? <code className="font-mono text-xs text-text-2">{item.description}</code> : unknown}</Row>
        {item.scope && <Row label="Scope"><Badge>{item.scope === "project" ? "Project" : "Global"}</Badge></Row>}
      </>
    );
  } else if (item.kind === "plugin") {
    title = "Plugin";
    const kids = out("contains");
    if (!kids.length) return null;
    const p = pluginInfo(kids);
    rows = (
      <>
        <Row label="Contains">
          <span className="flex flex-wrap gap-x-3 gap-y-1">
            {p.counts.map(([k, n]) => <span key={k} className="inline-flex items-center gap-1.5"><span className="glyph" data-kind={k} />{noun(n, kindName(k))}</span>)}
          </span>
        </Row>
        <Row label="Total always-on">
          <span className="font-mono tabular-nums">
            {p.total == null ? unknown : `${p.total.toLocaleString()} tokens`}
            {p.unknown > 0 && (p.total == null ? null : <span className="font-sans text-text-3"> + {p.unknown} unknown</span>)}
          </span>
        </Row>
        {p.tracked > 0 && <Row label="Never seen">{p.unseen} of {p.tracked} tracked</Row>}
      </>
    );
  } else return null;
  return (
    <section aria-label={`${title} details`} className="mt-5 animate-fade-in rounded-lg border bg-surface-2 px-3 py-3">
      <dl className="divide-y divide-line-1">{rows}</dl>
    </section>
  );
}
