import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Inspector } from "@/components/Inspector";
import { Legend } from "@/components/Legend";
import { StarMap, type StarMapHandle } from "@/components/StarMap";
import { Failed, Loading, Nothing } from "@/components/States";
import { TopBar } from "@/components/TopBar";
import { buildModel, kindName, search, type Constellation, type GNode, type Model } from "@/graph/model";

type Load = { state: "loading" } | { state: "failed"; detail: string } | { state: "ready"; model: Model | null };

// Relative URL, so the same build works under `constellation open` and from a static Snapshot.
async function fetchConstellation(): Promise<Constellation> {
  const r = await fetch("api/constellation");
  if (r.ok) return r.json();
  const body = await r.json().catch(() => ({}));
  throw new Error(body.detail || `The server answered ${r.status}`);
}

const PANEL = 380;

export default function App() {
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let live = true;
    fetchConstellation()
      .then((data) => live && setLoad({ state: "ready", model: data.items?.length ? buildModel(data) : null }))
      .catch((e: Error) => live && setLoad({ state: "failed", detail: e.message }));
    return () => { live = false; };
  }, [attempt]);

  if (load.state === "loading") return <Loading />;
  if (load.state === "failed") return <Failed detail={load.detail} onRetry={() => { setLoad({ state: "loading" }); setAttempt((a) => a + 1); }} />;
  if (!load.model) return <Nothing />;
  return <Atlas model={load.model} />;
}

function Atlas({ model }: { model: Model }) {
  const map = useRef<StarMapHandle>(null);
  const [selected, setSelected] = useState<GNode | null>(null);
  const [preview, setPreview] = useState<GNode | null>(null);
  const [query, setQuery] = useState("");
  const [phone, setPhone] = useState(() => matchMedia("(max-width: 640px)").matches);
  const found = useMemo(() => search(model.nodes, query), [model, query]);
  const matches = useMemo(() => (query.trim() ? new Set(found) : null), [found, query]);

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
      <p className="pointer-events-none fixed right-6 bottom-6 hidden text-xs text-text-3 sm:block">Drag to move, scroll to zoom, arrows to step</p>
      {selected && <Inspector model={model} item={selected} onSelect={select} onPreview={setPreview} onClose={close} />}
      <p className="sr-only" aria-live="polite">{selected ? `${selected.name}, ${kindName(selected.kind)}` : ""}</p>
    </>
  );
}
