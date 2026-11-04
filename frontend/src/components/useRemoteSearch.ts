import { useEffect, useState } from "react";
import type { Remote } from "@/graph/searchMerge";

const DEBOUNCE = 120, RETRY_AFTER = 30_000;
let downAt = 0; // a static host or stopped server: skip the call for a while so typing never waits on it

// The server's answer for the query, or null while it is pending or when the API is absent (then `pending` is false and local results stand alone).
export function useRemoteSearch(query: string): { remote: Remote | null; pending: boolean } {
  const q = query.trim();
  const [answer, setAnswer] = useState<(Remote & { q: string }) | null>(null);
  const [failed, setFailed] = useState("");
  useEffect(() => {
    if (!q) return;
    const controller = new AbortController();
    const id = setTimeout(() => {
      if (Date.now() - downAt < RETRY_AFTER) { setFailed(q); return; }
      void fetch(`api/search?q=${encodeURIComponent(q)}&limit=8`, { signal: controller.signal })
        .then((r) => { if (!r.ok) throw new Error("Search unavailable"); return r.json() as Promise<Remote>; })
        .then((data) => { if (!Array.isArray(data.results)) throw new Error("Not the search API"); setAnswer({ q, results: data.results, note: data.note ?? null }); })
        .catch(() => { if (!controller.signal.aborted) { downAt = Date.now(); setFailed(q); } });
    }, DEBOUNCE);
    return () => { clearTimeout(id); controller.abort(); };
  }, [q]);
  const remote = answer && answer.q === q ? answer : null;
  return { remote, pending: !!q && !remote && failed !== q };
}
