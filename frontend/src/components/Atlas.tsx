import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Legend } from "@/components/Legend";
import { StarMap, type StarMapHandle } from "@/components/StarMap";
import { TopBar } from "@/components/TopBar";
import { kindName, search, type GNode, type Model } from "@/graph/model";

// The inspector only appears once something is selected, so it loads on its own; it is fetched when the page is idle
// so the first selection does not wait.
const loadInspector = () => import("@/components/Inspector");
const Inspector = lazy(() => loadInspector().then((m) => ({ default: m.Inspector })));

const PANEL = 380;

export default function Atlas({ model }: { model: Model }) {
  const map = useRef<StarMapHandle>(null);
  const [selected, setSelected] = useState<GNode | null>(null);
  const [preview, setPreview] = useState<GNode | null>(null);
  const [query, setQuery] = useState("");
  const [phone, setPhone] = useState(() => matchMedia("(max-width: 640px)").matches);
  const found = useMemo(() => search(model.nodes, query), [model, query]);
  const matches = useMemo(() => (query.trim() ? new Set(found) : null), [found, query]);

  useEffect(() => {
    const id = setTimeout(loadInspector, 600);
    return () => clearTimeout(id);
  }, []);

  useEffect(() => {
    const mq = matchMedia("(max-width: 640px)"), on = () => setPhone(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);

  const select = useCallback((n: GNode | null) => {
    setSelected(n);
    setPreview(null);
    if (n) map.current?.glideTo(n);
  }, []);

  const close = useCallback(() => {
    setSelected(null);
    setPreview(null);
    map.current?.focusCanvas();
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !(e.target instanceof HTMLInputElement) && !e.defaultPrevented) close();
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [close]);

  return (
    <>
      <StarMap ref={map} model={model} selected={selected} preview={preview} matches={matches} panelWidth={phone ? 0 : PANEL} onSelect={select} />
      <TopBar
        model={model}
        query={query}
        found={found}
        onQuery={setQuery}
        onPreview={setPreview}
        onChoose={(n) => { setQuery(""); select(n); map.current?.focusCanvas(); }}
      />
      <Legend model={model} hidden={!!selected} />
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
