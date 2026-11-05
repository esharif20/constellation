import { useEffect, useState } from "react";
import type { Lenses } from "@/graph/lenses";

// The lenses once per mount, or null while pending, on an error, or when the API is absent (a static host); the Brief works without them.
export function useLenses(): Lenses | null {
  const [lenses, setLenses] = useState<Lenses | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void fetch("api/lenses", { signal: controller.signal })
      .then((r) => { if (!r.ok) throw new Error("Lenses unavailable"); return r.json() as Promise<Lenses>; })
      .then((data) => { if (data.receipt && Array.isArray(data.receipt.rows)) setLenses(data); })
      .catch(() => {});
    return () => controller.abort();
  }, []);
  return lenses;
}
