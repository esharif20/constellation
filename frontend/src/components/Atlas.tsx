import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Legend } from "@/components/Legend";
import { Brief } from "@/components/Brief";
import { StarMap, type StarMapHandle } from "@/components/StarMap";
import { TopBar } from "@/components/TopBar";
import { kindName, search, type BriefData, type BriefRow, type GNode, type Model } from "@/graph/model";

// The inspector only appears once something is selected, so it loads on its own; it is fetched when the page is idle
// so the first selection does not wait.
const loadInspector = () => import("@/components/Inspector");
const Inspector = lazy(() => loadInspector().then((m) => ({ default: m.Inspector })));

const PANEL = 380;

export default function Atlas({ model }: { model: Model }) {
  const map = useRef<StarMapHandle>(null);
  const framedPair = useRef<GNode | undefined>(undefined);
  const pill = useRef<HTMLButtonElement>(null);
  const [brief, setBrief] = useState<BriefData | null>(null);
  const [briefOpen, setBriefOpen] = useState(() => { try { return localStorage.getItem("constellation.brief") !== "closed"; } catch { return true; } });
  const [selected, setSelected] = useState<GNode | null>(null);
  const [preview, setPreview] = useState<GNode | null>(null);
  const [query, setQuery] = useState("");
  const [phone, setPhone] = useState(() => matchMedia("(max-width: 640px)").matches);
  const [narrow, setNarrow] = useState(() => matchMedia("(width < 960px)").matches);
  const found = useMemo(() => search(model.nodes, query), [model, query]);
  const matches = useMemo(() => (query.trim() ? new Set(found) : null), [found, query]);
  const showBrief = !!brief && briefOpen && !(narrow && selected);

  useEffect(() => {
    const controller = new AbortController();
    void fetch("api/brief", { signal: controller.signal })
      .then((response) => { if (!response.ok) throw new Error("Brief unavailable"); return response.json(); })
      .then((data: BriefData) => { if (Array.isArray(data.cost?.rows) && Array.isArray(data.pairs?.rows)) setBrief(data); })
      .catch(() => { /* Static Snapshots and older servers have no brief. */ });
    return () => controller.abort();
  }, []);

  const openBrief = useCallback((open: boolean) => {
    setBriefOpen(open);
    if (open && narrow) { setSelected(null); setPreview(null); }
    try { localStorage.setItem("constellation.brief", open ? "open" : "closed"); } catch { /* Storage is optional. */ }
  }, [narrow]);

  useEffect(() => {
    const id = setTimeout(loadInspector, 600);
    return () => clearTimeout(id);
  }, []);

  useEffect(() => {
    const mq = matchMedia("(max-width: 640px)"), on = () => setPhone(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);

  useEffect(() => {
    const mq = matchMedia("(width < 960px)");
    const on = () => {
      setNarrow(mq.matches);
      if (mq.matches && selected) {
        openBrief(false);
        requestAnimationFrame(() => map.current?.glideTo(selected, framedPair.current));
      }
    };
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [selected, openBrief]);

  const select = useCallback((n: GNode | null) => {
    setSelected(n);
    setPreview(null);
    framedPair.current = undefined;
    if (n) {
      if (narrow) {
        openBrief(false);
        requestAnimationFrame(() => map.current?.glideTo(n));
      } else map.current?.glideTo(n);
    }
  }, [narrow, openBrief]);

  const selectById = (id: string) => {
    const node = model.nodes.find((n) => n.id === id);
    if (node) { select(node); map.current?.focusCanvas(); }
  };

  const selectPair = (row: BriefRow) => {
    const node = model.nodes.find((n) => n.id === (row.removes ?? row.item_ids[0]));
    const other = model.nodes.find((n) => row.item_ids.includes(n.id) && n !== node);
    if (node) {
      setSelected(node);
      setPreview(null);
      framedPair.current = other;
      if (narrow) {
        openBrief(false);
        requestAnimationFrame(() => map.current?.glideTo(node, other));
      } else map.current?.glideTo(node, other);
      map.current?.focusCanvas();
    }
  };

  const close = useCallback(() => {
    setSelected(null);
    setPreview(null);
    map.current?.focusCanvas();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof Element && !!e.target.closest('input, textarea, select, [contenteditable="true"]');
      if (typing || e.defaultPrevented) return;
      if (e.key === "b" && !e.metaKey && !e.ctrlKey && !e.altKey && brief) { e.preventDefault(); openBrief(!briefOpen); }
      if (e.key === "Escape") close();
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [close, brief, briefOpen, openBrief]);

  return (
    <>
      <div className="relative z-10">
      <TopBar
        model={model}
        query={query}
        found={found}
        onQuery={setQuery}
        onPreview={setPreview}
        onChoose={(n) => { setQuery(""); select(n); map.current?.focusCanvas(); }}
      />
      {brief && <Brief data={brief} model={model} open={showBrief} hidden={phone && !!selected} pill={pill} onOpen={openBrief} onItem={selectById} onPair={selectPair} />}
      </div>
      <StarMap ref={map} model={model} selected={selected} preview={preview} matches={matches} panelWidth={phone ? 0 : PANEL} briefOpen={showBrief} onSelect={select} />
      <Legend model={model} hidden={!!selected || showBrief} />
      {!selected && <p className="pointer-events-none fixed right-6 bottom-6 hidden text-xs text-text-3 sm:block">Drag to move, scroll to zoom, arrows to step</p>}
      {selected && (
        <Suspense fallback={null}>
          <Inspector model={model} item={selected} onSelect={select} onPreview={setPreview} onClose={close} />
        </Suspense>
      )}
      <p className="sr-only" aria-live="polite">{selected ? `${selected.name}, ${kindName(selected.kind)}` : ""}</p>
    </>
  );
}
