import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Legend } from "@/components/Legend";
import { Brief } from "@/components/Brief";
import { Chat, type ChatAction } from "@/components/Chat";
import { ClusterCard } from "@/components/ClusterCard";
import { StarMap, type StarMapHandle } from "@/components/StarMap";
import { TopBar } from "@/components/TopBar";
import { clusterSummary, kindName, search, type BriefData, type BriefRow, type Cluster, type GNode, type GOverlap, type Model } from "@/graph/model";

// The inspector only appears once something is selected, so it loads on its own; it is fetched when the page is idle
// so the first selection does not wait.
const loadInspector = () => import("@/components/Inspector");
const Inspector = lazy(() => loadInspector().then((m) => ({ default: m.Inspector })));

const PANEL = 380;

const hashCluster = (model: Model) => model.clusters.find((c) => c.slug === new URLSearchParams(location.hash.slice(1)).get("cluster")) ?? null;

export default function Atlas({ model }: { model: Model }) {
  const map = useRef<StarMapHandle>(null);
  const framedPair = useRef<GNode | undefined>(undefined);
  const pill = useRef<HTMLButtonElement>(null);
  const [brief, setBrief] = useState<BriefData | null>(null);
  const [briefOpen, setBriefOpen] = useState(() => {
    const onPhone = matchMedia("(max-width: 640px)").matches; // a first visit on a phone starts collapsed so the map stays visible
    try { const saved = localStorage.getItem("constellation.brief"); return saved ? saved === "open" : !onPhone; } catch { return !onPhone; }
  });
  const [chatOpen, setChatOpen] = useState(false);
  const [chatMatches, setChatMatches] = useState<Set<GNode> | null>(null);
  const [selected, setSelected] = useState<GNode | null>(null);
  // Cluster focus. The left slot has one occupant: the cluster card, the Brief or the chat. `card` outlives `cluster` while the card leaves.
  const [cluster, setCluster] = useState<Cluster | null>(() => hashCluster(model));
  const [card, setCard] = useState<Cluster | null>(cluster);
  const [byKeyboard, setByKeyboard] = useState(false);
  const [live, setLive] = useState("");
  const pushed = useRef(false); // our own history entry is on top, so leaving can go back instead of adding one
  const [preview, setPreview] = useState<GNode | null>(null);
  const [query, setQuery] = useState("");
  const [phone, setPhone] = useState(() => matchMedia("(max-width: 640px)").matches);
  const [narrow, setNarrow] = useState(() => matchMedia("(width < 960px)").matches);
  const found = useMemo(() => search(model.nodes, query), [model, query]);
  const matches = useMemo(() => (query.trim() ? new Set(found) : chatMatches), [found, query, chatMatches]);
  const showBrief = !!brief && briefOpen && !chatOpen && !(narrow && selected) && !cluster;
  const showInspector = !(narrow && chatOpen);
  if (cluster && card !== cluster) setCard(cluster);
  if (!cluster && card && narrow && selected) setCard(null);

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
    if (open) setChatOpen(false);
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

  const enter = useCallback((c: Cluster, keyboard = false) => {
    if (c === cluster) return;
    const url = `#cluster=${c.slug}`;
    if (cluster) history.replaceState({ pushed: pushed.current }, "", url); // a hop does not add history
    else { history.pushState({ pushed: true }, "", url); pushed.current = true; }
    const s = clusterSummary(c, model);
    setLive(`${c.name}, ${s.count} Items, ${s.known == null ? "cost unknown" : `${s.known.toLocaleString()} tokens known, ${s.unknown} unknown`}`);
    setChatOpen(false);
    setCluster(c);
    setByKeyboard(keyboard);
    if (narrow) { setSelected(null); setPreview(null); }
  }, [cluster, model, narrow]);

  // `swap`: leaving to go somewhere else, so the history entry is replaced rather than gone back from
  const leave = useCallback((swap = false) => {
    setCluster(null);
    setLive("Whole map");
    if (pushed.current && !swap) history.back();
    else history.replaceState(null, "", location.pathname + location.search);
    pushed.current = false;
  }, []);

  const openChat = useCallback((open: boolean) => {
    setChatOpen(open);
    setPreview(null);
    if (open) setCard(null);
    if (open && cluster) {
      if (selected) map.current?.holdCamera();
      leave(true);
    }
    if (selected) requestAnimationFrame(() => map.current?.glideTo(selected, framedPair.current));
  }, [selected, cluster, leave]);

  useEffect(() => {
    const on = (e: PopStateEvent) => { pushed.current = !!e.state?.pushed; const c = hashCluster(model); if (c) setChatOpen(false); setCluster(c); };
    addEventListener("popstate", on);
    return () => removeEventListener("popstate", on);
  }, [model]);

  const select = useCallback((n: GNode | null) => {
    if (n && cluster && n.cluster !== cluster) { map.current?.holdCamera(); leave(true); } // an Item outside the cluster: leave focus and glide there in one flight
    setSelected(n);
    setPreview(null);
    framedPair.current = undefined;
    if (n) {
      if (narrow) {
        openBrief(false);
        requestAnimationFrame(() => map.current?.glideTo(n));
      } else map.current?.glideTo(n);
    }
  }, [narrow, openBrief, cluster, leave]);

  const selectById = (id: string) => {
    const node = model.nodes.find((n) => n.id === id);
    if (node) { select(node); map.current?.focusCanvas(); }
  };

  const selectPair = (row: BriefRow) => {
    const node = model.nodes.find((n) => n.id === (row.removes ?? row.item_ids[0]));
    const other = model.nodes.find((n) => row.item_ids.includes(n.id) && n !== node);
    if (node) framePair(node, other);
  };

  const framePair = (node: GNode, other: GNode | undefined) => {
    setSelected(node);
    setPreview(null);
    framedPair.current = other;
    if (narrow) {
      openBrief(false);
      requestAnimationFrame(() => map.current?.glideTo(node, other));
    } else map.current?.glideTo(node, other);
    map.current?.focusCanvas();
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
      if (e.key === "b" && !e.metaKey && !e.ctrlKey && !e.altKey && brief) { e.preventDefault(); if (cluster) leave(); openBrief(cluster || chatOpen ? true : !briefOpen); } // opening the Brief leaves focus
      if (e.key === "Escape") { if (chatOpen) openChat(false); else if (cluster && !selected) leave(); else close(); } // search and Brief handle their own Escape first
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [close, brief, briefOpen, openBrief, cluster, selected, leave, chatOpen, openChat]);

  const applyChatActions = (actions: ChatAction[]) => {
    const ids = new Set(actions.flatMap((action) => action.item_ids));
    setQuery("");
    setChatMatches(ids.size ? new Set(model.nodes.filter((n) => ids.has(n.id))) : null);
    const focus = actions.find((action) => action.kind === "focus" && action.item_ids.length);
    const node = focus && model.nodes.find((n) => n.id === focus.item_ids[0]);
    if (node) select(node);
  };

  const back = () => { leave(); map.current?.focusCanvas(); };
  const onCluster = (c: Cluster | null, keyboard?: boolean) => (c ? enter(c, keyboard) : back());

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
        cluster={cluster}
        onCluster={onCluster}
      />
      {card && !chatOpen && !(narrow && selected) && <ClusterCard cluster={card} model={model} leaving={!cluster} focusTitle={byKeyboard} onBack={back} onItem={(n) => { select(n); map.current?.focusCanvas(); }} onPreview={setPreview} onPair={(o: GOverlap) => framePair(o.a, o.b)} onGone={() => setCard(null)} />}
      {brief && <Brief data={brief} model={model} open={showBrief} footerInset={52} hidden={chatOpen || (phone && !!selected) || !!cluster} pill={pill} onOpen={openBrief} onItem={selectById} onPair={selectPair} />}
      <Chat model={model} selected={selected} open={chatOpen} briefOpen={showBrief} clusterOpen={!!cluster} onOpen={openChat} onActions={applyChatActions} onReset={() => setChatMatches(null)} onItem={selectById} />
      </div>
      <StarMap ref={map} model={model} selected={selected} preview={preview} matches={matches} panelWidth={phone || (narrow && chatOpen) ? 0 : PANEL} leftPanel={chatOpen ? "chat" : showBrief ? "brief" : null} cluster={cluster} onSelect={select} onCluster={onCluster} />
      <Legend model={model} hidden={!!selected || showBrief || chatOpen} />
      {!selected && <p className="pointer-events-none fixed right-6 bottom-6 hidden text-xs text-text-3 sm:block">Drag to move, scroll to zoom, arrows to step</p>}
      {selected && showInspector && (
        <Suspense fallback={null}>
          <Inspector model={model} item={selected} onSelect={select} onPreview={setPreview} onClose={close} backTo={narrow ? cluster?.name : undefined} />
        </Suspense>
      )}
      <p className="sr-only" aria-live="polite">{live}</p>
      <p className="sr-only" aria-live="polite">{selected ? `${selected.name}, ${kindName(selected.kind)}` : ""}</p>
    </>
  );
}
