import { useEffect, useState } from "react";
import type { Found } from "@/graph/find";

const DEBOUNCE = 250;

// The local skill search's answer for the query while `enabled`; null while pending or when the API is absent (static host, stopped server).
export function useFind(query: string, enabled: boolean): { found: Found | null; pending: boolean } {
  const q = query.trim();
  const [answer, setAnswer] = useState<(Found & { q: string }) | null>(null);
  const [failed, setFailed] = useState("");
  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    const id = setTimeout(() => {
      void fetch(`api/find?q=${encodeURIComponent(q)}`, { signal: controller.signal })
        .then((r) => { if (!r.ok) throw new Error("Find unavailable"); return r.json() as Promise<Found>; })
        .then((d) => { if (typeof d.available !== "boolean" || !Array.isArray(d.results)) throw new Error("Not the find API"); setAnswer({ q, available: d.available, results: d.results, note: d.note ?? null }); })
        .catch(() => { if (!controller.signal.aborted) setFailed(q); });
    }, DEBOUNCE);
    return () => { clearTimeout(id); controller.abort(); };
  }, [q, enabled]);
  const found = enabled && answer && answer.q === q ? answer : null;
  return { found, pending: enabled && !found && failed !== q };
}
