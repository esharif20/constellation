import { lazy, Suspense, useEffect, useState } from "react";
import { Failed, Loading, Nothing } from "@/components/States";
import { buildModel, type Constellation, type Model } from "@/graph/model";

// The map, search and inspector (force-graph, d3, cmdk, radix) are a separate chunk, so the first paint and the
// data fetch do not wait on them; they download in parallel.
const loadAtlas = () => import("@/components/Atlas");
const Atlas = lazy(loadAtlas);
void loadAtlas();

type Load = { state: "loading" } | { state: "failed"; detail: string } | { state: "ready"; model: Model | null };

// Relative URL, so the same build works under `constellation open` and from a static Snapshot.
async function fetchConstellation(): Promise<Constellation> {
  const r = await fetch("api/constellation");
  if (r.ok) return r.json();
  const body = await r.json().catch(() => ({}));
  throw new Error(body.detail || `The server answered ${r.status}`);
}

export default function App() {
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let live = true;
    fetchConstellation()
      .then((data) => live && setLoad({ state: "ready", model: data.items?.length ? buildModel(data, innerHeight / innerWidth) : null }))
      .catch((e: Error) => live && setLoad({ state: "failed", detail: e.message }));
    return () => { live = false; };
  }, [attempt]);

  if (load.state === "loading") return <Loading />;
  if (load.state === "failed") return <Failed detail={load.detail} onRetry={() => { setLoad({ state: "loading" }); setAttempt((a) => a + 1); }} />;
  if (!load.model) return <Nothing />;
  return (
    <Suspense fallback={<Loading />}>
      <Atlas model={load.model} />
    </Suspense>
  );
}
