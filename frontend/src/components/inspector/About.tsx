import { useLayoutEffect, useRef, useState } from "react";
import { splitDescription } from "@/lib/describe";
import type { GNode } from "@/graph/model";

// Hooks and MCP servers describe a command or a shape (KindDetails), so they skip the split.
const RAW = ["hook", "mcp_server", "connector"];

function Block({ title, text }: { title: string; text: string }) {
  const el = useRef<HTMLParagraphElement>(null);
  const [open, setOpen] = useState(false), [long, setLong] = useState(false);
  useLayoutEffect(() => { const p = el.current; if (p && !open) setLong(p.scrollHeight > p.clientHeight + 1); }, [text, open]);
  return (
    <section className="mt-4 first:mt-0">
      <h3 className="mb-1 text-xs font-medium tracking-[0.02em] text-text-3">{title}</h3>
      <p ref={el} className={`max-w-[65ch] text-sm leading-[1.55] text-text-2 [overflow-wrap:anywhere] ${open ? "" : "line-clamp-3"}`}>{text}</p>
      {(long || open) && (
        <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className="mt-1 inline-flex min-h-10 items-center rounded-md text-[13px] text-indigo-bright outline-none hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/50 max-sm:min-h-11">
          {open ? "Show less" : "Show more"}
        </button>
      )}
    </section>
  );
}

export function About({ item }: { item: GNode }) {
  const raw = RAW.includes(item.kind);
  const { does, when } = raw ? { does: "", when: "" } : splitDescription(item.description, item.label);
  return (
    <div className="mt-6">
      {raw ? null : !does && !when ? <p className="text-sm text-text-3">No description.</p> : (
        <>
          {does && <Block title="What it does" text={does} />}
          {when && <Block title="When it triggers" text={when} />}
        </>
      )}
      <p className="mt-3 font-mono text-xs leading-[1.45] text-text-3 [overflow-wrap:anywhere]">{item.source}</p>
    </div>
  );
}
