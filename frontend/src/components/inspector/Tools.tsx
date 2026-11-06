import { useEffect, useRef, useState } from "react";
import { ChevronRightIcon, LoaderCircleIcon } from "lucide-react";
import { Presence, Pane } from "@/components/Motion";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type Tool = { name: string; description: string };
export type Listing = { tools: Tool[] } | { error: string } | { remote: true };

const WAIT_MS = 15_000; // the server gives up at 10 s; this only covers a server that never answers

// Turn the /api/expand reply into what the panel shows. Messages are fixed words: server text, paths and settings never reach the screen.
export function listing(status: number, body: unknown): Listing {
  const b = (body && typeof body === "object" ? body : {}) as { status?: string; items?: { name?: unknown; description?: unknown }[] };
  if (status === 200 && b.status === "expanded" && Array.isArray(b.items)) {
    return { tools: b.items.map((i) => ({ name: String(i.name ?? ""), description: String(i.description ?? "") })) };
  }
  if (status === 200 && b.status === "not_expandable") return { remote: true };
  if (status === 200 && b.status === "unavailable") return { error: "the app was opened without a config folder" };
  if (status === 200) return { error: "it did not start or did not answer in time" };
  return { error: status === 404 ? "this server is not in the current scan" : "the request was refused" };
}

const oneLine = (text: string) => text.replace(/\s+/g, " ").trim();

export function ToolsBody({ data }: { data: Listing }) {
  if ("remote" in data) return <p role="status" className="mt-2 text-xs text-text-3">Tools can only be listed for local servers.</p>;
  if ("error" in data) return <p role="status" className="mt-2 text-xs leading-[1.45] text-warn">Could not reach this server: {data.error}.</p>;
  if (data.tools.length === 0) return <p role="status" className="mt-2 text-xs text-text-3">This server offers no tools.</p>;
  return <div className="mt-2">
    <h4 className="text-xs font-medium text-text-3">Tools <span className="ml-1 font-mono tabular-nums">{data.tools.length}</span></h4>
    <ul className="mt-1 flex flex-col gap-2">{data.tools.map((t) => <li key={t.name}>
      <span className="font-mono text-[13px] text-foreground [overflow-wrap:anywhere]">{t.name}</span>
      {t.description && <p className="line-clamp-2 text-xs leading-[1.45] text-text-3 [overflow-wrap:anywhere]">{oneLine(t.description)}</p>}
    </li>)}</ul>
  </div>;
}

// "Tools this server offers": closed until asked, and nothing starts until "List tools" is pressed (Expansion runs the user's own server).
// All state stays here, so opening the section never re-renders the rest of the Inspector.
export function ToolsSection({ item }: { item: { id: string; kind: string } }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<Listing | "loading" | null>(null);
  const run = useRef<AbortController | null>(null);
  useEffect(() => () => run.current?.abort(), []);
  if (item.kind !== "mcp_server" && item.kind !== "connector") return null;
  const local = item.kind === "mcp_server";
  const go = () => {
    run.current?.abort();
    const controller = (run.current = new AbortController());
    const timer = setTimeout(() => controller.abort(), WAIT_MS);
    setData("loading");
    fetch("api/expand", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: item.id }), signal: controller.signal })
      .then(async (r) => listing(r.status, await r.json().catch(() => null)))
      .catch((): Listing => ({ error: controller.signal.aborted ? "it did not answer in time" : "the app could not be asked" }))
      .then((d) => { if (run.current === controller) setData(d); })
      .finally(() => clearTimeout(timer));
  };
  return <section className="mt-4 border-t border-line-1 pt-2">
    <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} className="group flex min-h-10 w-full items-center gap-2 rounded-md text-left text-[13px] font-medium text-text-2 outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 max-sm:min-h-11">
      <ChevronRightIcon aria-hidden className={cn("size-4 shrink-0 text-text-3 transition-transform duration-(--t-fast) ease-(--ease-out)", open && "rotate-90")} />
      Tools this server offers
    </button>
    <Presence>{open ? <Pane from="top">
      {!local ? <ToolsBody data={{ remote: true }} /> : <>
        {!(data && typeof data === "object" && "remote" in data) && <p className="mt-2 text-xs leading-[1.45] text-text-3">This starts the server on your machine to ask what it offers; nothing is sent anywhere.</p>}
        {data === null || (typeof data === "object" && "error" in data)
          ? <Button variant="outline" className="mt-2 h-10 max-sm:h-11" onClick={go}>{data === null ? "List tools" : "Try again"}</Button>
          : null}
        {data === "loading" ? <p role="status" className="mt-2 flex items-center gap-2 text-xs text-text-3"><LoaderCircleIcon aria-hidden className="size-3.5 animate-spin motion-reduce:animate-none" />Asking the server...</p>
          : data && <ToolsBody data={data} />}
      </>}
    </Pane> : null}</Presence>
  </section>;
}
