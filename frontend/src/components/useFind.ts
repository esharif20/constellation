import { useEffect, useState } from "react";
import { findQuery, type FindFilters, type Found } from "@/graph/find";

const DEBOUNCE = 250;

// The local skill search's answer for the query while `enabled`; null while pending or when the API is absent (static host, stopped server).
export function useFind(query: string, enabled: boolean, filters: FindFilters): { found: Found | null; pending: boolean } {
  const q = query.trim();
  const key = findQuery(q, filters);
  const [answer, setAnswer] = useState<(Found & { q: string }) | null>(null);
  const [failed, setFailed] = useState("");
  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    const id = setTimeout(() => {
      void fetch(`api/find?${key}`, { signal: controller.signal })
        .then((r) => { if (!r.ok) throw new Error("Find unavailable"); return r.json() as Promise<Found>; })
        .then((d) => { if (typeof d.available !== "boolean" || !Array.isArray(d.results)) throw new Error("Not the find API"); setAnswer({ q: key, available: d.available, results: d.results, note: d.note ?? null }); })
        .catch(() => { if (!controller.signal.aborted) setFailed(key); });
    }, DEBOUNCE);
    return () => { clearTimeout(id); controller.abort(); };
  }, [key, enabled]);
  const found = enabled && answer && answer.q === key ? answer : null;
  return { found, pending: enabled && !found && failed !== key };
}
