import { escape, RANK } from "@/lib/dismiss";
import { useLayer } from "@/lib/useLayer";
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Presence } from "@/components/Motion";
import { Legend } from "@/components/Legend";
import { Brief } from "@/components/Brief";
import { AskTrigger, Chat, type ChatAction } from "@/components/Chat";
import { HighlightChip } from "@/components/HighlightChip";
import { ClusterCard } from "@/components/ClusterCard";
import { WhatIfChip } from "@/components/WhatIfChip";
import { StarMap, type StarMapHandle } from "@/components/StarMap";
import { History } from "@/components/History";
import { Scrubber } from "@/components/Scrubber";
import { TopBar } from "@/components/TopBar";
import { ExplainCard } from "@/components/ExplainCard";
import { absentAt, type Timeline } from "@/graph/history";
import { useRemoteSearch } from "@/components/useRemoteSearch";
import { searchItems } from "@/graph/search";
import { matchClusters, mergeResults } from "@/graph/searchMerge";
import { budget, clusterSummary, withContents, type Assessment, type BriefData, type Habits, type BriefRow, type Cluster, type GNode, type GOverlap, type Model, type Scope, scopeSet } from "@/graph/model";
import { InspectorSkeleton } from "@/components/inspector/Skeleton";
import { verdictOf } from "@/lib/verdict";
import { briefFrom } from "@/lib/brief";

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
  const [assess, setAssess] = useState<Record<string, Assessment> | null>(null);
  const [habits, setHabits] = useState<Habits | null>(null);
  const assessments = assess ?? model.assessments;
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [briefOpen, setBriefOpen] = useState(() => {
    const onPhone = matchMedia("(max-width: 640px)").matches; // a first visit on a phone starts collapsed so the map stays visible
    try { const saved = localStorage.getItem("constellation.brief"); return saved ? saved === "open" : !onPhone; } catch { return !onPhone; }
  });
  const [chatOpen, setChatOpen] = useState(false);
  const [scrub, setScrub] = useState<string | null>(null); // time travel: the chosen scan date (null = off)
  const absent = useMemo(() => (scrub && timeline ? absentAt(model.nodes, timeline.first_seen, scrub) : null), [model, timeline, scrub]);
  const [chatMatches, setChatMatches] = useState<Set<GNode> | null>(null);
  const [whatIf, setWhatIf] = useState<Set<GNode> | null>(null); // what-if ticks, page memory only (null = off)
  const removed = useMemo(() => whatIf && withContents(model, whatIf), [model, whatIf]);
  const [selected, setSelected] = useState<GNode | null>(null);
  const [scope, setScope] = useState<Scope>("all");
  const scoped = useMemo(() => scopeSet(model, scope), [model, scope]);
  // Cluster focus. The left slot has one occupant: the cluster card, the Brief or the chat. AnimatePresence keeps the card on screen while it leaves.
  const [cluster, setCluster] = useState<Cluster | null>(() => hashCluster(model));
  const [byKeyboard, setByKeyboard] = useState(false);
  const [live, setLive] = useState("");
  const [draft, setDraft] = useState<{ text: string; n: number }>();
  const pushed = useRef(false); // our own history entry is on top, so leaving can go back instead of adding one
  const [preview, setPreview] = useState<GNode | null>(null);
  const [query, setQuery] = useState("");
  const [phone, setPhone] = useState(() => matchMedia("(max-width: 640px)").matches);
  const [narrow, setNarrow] = useState(() => matchMedia("(width < 960px)").matches);
  const { remote, pending } = useRemoteSearch(query);
  const byId = useMemo(() => new Map(model.nodes.map((n) => [n.id, n])), [model]);
  const rows = useMemo(() => mergeResults(searchItems(model.nodes, query, Infinity), remote, byId), [model, query, remote, byId]);
  const found = useMemo(() => rows.map((r) => r.item), [rows]);
  const clusterHits = useMemo(() => matchClusters(model.clusters, query), [model, query]);
  // One owner for the highlighted set: search wins while a query is typed, otherwise the last chat answer. The chip names it and clears it.
  const [pack, setPack] = useState<string | null>(null); // a Packs legend choice: an origin whose members are lit
  if (pack && query.trim()) setPack(null); // typing takes the highlight over
  const packSet = useMemo(() => (pack ? new Set(model.packs.find((p) => p.origin === pack)?.members) : null), [model, pack]);
  const highlight = query.trim() ? { from: "search" as const, count: found.length } : packSet ? { from: "pack" as const, count: packSet.size, detail: pack! } : chatMatches ? { from: "chat" as const, count: chatMatches.size } : null;
  const matches = useMemo(() => (query.trim() ? new Set(found) : packSet ?? chatMatches), [found, query, packSet, chatMatches]);
  const clearHighlight = useCallback(() => { setQuery(""); setChatMatches(null); setPack(null); }, []);
  const showBrief = !!brief && briefOpen && !chatOpen && !(narrow && selected) && !cluster;
  const showInspector = !(narrow && chatOpen);
  if (!chatOpen && chatMatches) setChatMatches(null); // chat highlights end with the chat

  useEffect(() => {
    const controller = new AbortController();
    void fetch("api/assess", { signal: controller.signal }) // the live verdicts; the Constellation's own `assessments` cover a Snapshot
      .then((response) => { if (!response.ok) throw new Error("Assess unavailable"); return response.json(); })
      .then((data: { items?: Record<string, Assessment>; habits?: Habits["items"]; evidence?: { sessions?: number; active_days?: number } }) => {
        if (data.items && typeof data.items === "object") setAssess(data.items);
        if (data.habits && typeof data.habits === "object") setHabits({ items: data.habits, sessions: data.evidence?.sessions ?? 0, activeDays: data.evidence?.active_days ?? 0 });
      })
      .catch(() => { /* Static Snapshots and older servers have no /api/assess. */ });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    void fetch("api/brief", { signal: controller.signal })
      .then((response) => { if (!response.ok) throw new Error("Brief unavailable"); return response.json(); })
      .then((data) => { const b = briefFrom(data); if (b) setBrief(b); })
      .catch(() => { /* Static Snapshots and older servers have no brief. */ });
    return () => controller.abort();
  }, []);

  const toggleRemove = useCallback((n: GNode) => {
    const next = new Set(whatIf);
    if (!next.delete(n)) next.add(n);
    const b = budget(model.nodes, withContents(model, next));
    setWhatIf(next);
    setLive(`${next.has(n) ? "Removed" : "Put back"} ${n.name}. Session start ${b.known.toLocaleString()} tokens, saves ${b.saved.toLocaleString()}.`);
  }, [model, whatIf]);
  const startWhatIf = (on: boolean) => { setWhatIf(on ? new Set() : null); setLive(on ? "What-if on. Nothing in your setup changes." : "What-if ended, nothing changed"); };
  useEffect(() => {
    const controller = new AbortController();
    void fetch("api/history", { signal: controller.signal })
      .then((response) => { if (!response.ok) throw new Error("History unavailable"); return response.json(); })
      .then((data: Timeline) => { if (Array.isArray(data.entries)) setTimeline(data); })
      .catch(() => { /* Static Snapshots and older servers have no history. */ });
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
    setPreview(null); // the row that set it unmounts under a still pointer, so no mouseleave comes
    if (narrow) setSelected(null);
  }, [cluster, model, narrow]);

  // `swap`: leaving to go somewhere else, so the history entry is replaced rather than gone back from
  const leave = useCallback((swap = false) => {
    setCluster(null);
    setPreview(null);
    setLive("Whole map");
    if (pushed.current && !swap) history.back();
    else history.replaceState(null, "", location.pathname + location.search);
    pushed.current = false;
  }, []);

  const openChat = useCallback((open: boolean) => {
    setChatOpen(open);
    setPreview(null);
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
    if (!n) clearHighlight(); // the only null caller is a click on empty sky: back to the normal view
    framedPair.current = undefined;
    if (n) {
      if (narrow) {
        openBrief(false);
        requestAnimationFrame(() => map.current?.glideTo(n));
      } else map.current?.glideTo(n);
    }
  }, [narrow, openBrief, cluster, leave, clearHighlight]);

  const selectById = (id: string) => {
    const node = model.nodes.find((n) => n.id === id);
    if (node) { select(node); map.current?.focusCanvas(); }
  };

  // Narrow screens show the Inspector instead of the chat, so picking an Item from the chat's list closes it.
  const ask = (text: string) => { openChat(true); setDraft((d) => ({ text, n: (d?.n ?? 0) + 1 })); };
  const chatItem = (id: string) => { selectById(id); if (narrow) setChatOpen(false); };

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
    clearHighlight();
    map.current?.focusCanvas();
  }, [clearHighlight]);

  // Docked layers (docs/design/dismiss.md): Escape closes the Inspector, then the cluster card, then the highlight, then the Brief
  useLayer(!!selected && showInspector, { rank: RANK.inspector, close: close });
  useLayer(!!cluster && !selected, { rank: RANK.cluster, close: () => leave() });
  useLayer(!!highlight, { rank: RANK.highlight, close: clearHighlight });
  useLayer(showBrief, { rank: RANK.brief, close: () => { openBrief(false); requestAnimationFrame(() => pill.current?.focus()); } });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof Element && !!e.target.closest('input, textarea, select, [contenteditable="true"]');
      if (typing || e.defaultPrevented) return;
      if (e.key === "b" && !e.metaKey && !e.ctrlKey && !e.altKey && brief) { e.preventDefault(); if (cluster) leave(); openBrief(cluster || chatOpen ? true : !briefOpen); } // opening the Brief leaves focus
      if (e.key === "a" && !e.metaKey && !e.ctrlKey && !e.altKey && !chatOpen) { e.preventDefault(); openChat(true); }
      if (e.key === "x" && !e.metaKey && !e.ctrlKey && !e.altKey && whatIf && selected) { e.preventDefault(); toggleRemove(selected); }
      if (e.key === "Escape") { if (!escape()) close(); } // the dismiss stack closes one layer per press; search, popovers and a focused panel handle their own Escape first
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
  }, [close, brief, briefOpen, openBrief, cluster, selected, leave, chatOpen, openChat, whatIf, toggleRemove, scrub]);

  const applyChatActions = (actions: ChatAction[]) => {
    const ids = new Set(actions.flatMap((action) => action.item_ids));
    setQuery("");
    setPack(null);
    setChatMatches(ids.size ? new Set(model.nodes.filter((n) => ids.has(n.id))) : null);
    const focus = actions.find((action) => action.kind === "focus" && action.item_ids.length);
    const node = focus && model.nodes.find((n) => n.id === focus.item_ids[0]);
    if (node) select(node);
  };

  const back = useCallback(() => { leave(); map.current?.focusCanvas(); }, [leave]);
  const onCluster = useCallback((c: Cluster | null, keyboard?: boolean) => (c ? enter(c, keyboard) : back()), [enter, back]); // stable, so opening a panel does not re-render the map

  return (
    <>
      <div className="relative z-10">
      <TopBar
        model={model}
        query={query}
        found={found}
        rows={rows}
        clusterHits={clusterHits}
        note={remote?.note ?? null}
        pending={pending}
        onQuery={setQuery}
        onPreview={setPreview}
        onChoose={(n) => { setQuery(""); select(n); map.current?.focusCanvas(); }}
        cluster={cluster}
        onCluster={onCluster}
        scope={scope}
        onScope={setScope}
        extra={<History timeline={timeline} onTimeTravel={() => setScrub(timeline?.entries.at(-1)?.date ?? null)} />}
        ask={<AskTrigger open={chatOpen} onOpen={openChat} />}
        explain={brief ? <ExplainCard model={model} habits={habits} onCluster={(c) => enter(c, true)} onItem={(n) => selectById(n.id)} /> : undefined}
      />
      <Presence>{cluster && !chatOpen && !(narrow && selected) && <ClusterCard key="card" cluster={cluster} model={model} focusTitle={byKeyboard} onBack={back} onItem={(n) => { select(n); map.current?.focusCanvas(); }} onPreview={setPreview} onPair={(o: GOverlap) => framePair(o.a, o.b)} removed={removed} />}</Presence>
      {brief && <Brief data={brief} model={model} assessments={assessments} open={showBrief} hidden={chatOpen || (phone && !!selected) || !!cluster} pill={pill} onOpen={openBrief} onItem={selectById} onPair={selectPair} whatIf={whatIf} removed={removed} onWhatIf={startWhatIf} onToggle={toggleRemove} onReset={() => { setWhatIf(new Set()); setLive("What-if reset"); }} />}
      <Chat model={model} selected={selected} open={chatOpen} onOpen={openChat} onActions={applyChatActions} onReset={() => setChatMatches(null)} onItem={chatItem} draft={draft} />
      <Presence>{highlight && <HighlightChip key="highlight" highlight={highlight} onClear={clearHighlight} />}</Presence>
      </div>
      <StarMap ref={map} model={model} selected={selected} preview={preview} matches={matches} scope={scoped} panelWidth={phone || (narrow && chatOpen) ? 0 : PANEL} leftPanel={chatOpen ? "chat" : showBrief ? "brief" : null} cluster={cluster} onSelect={select} onCluster={onCluster} removed={removed} absent={absent} />
      {!scrub && <Legend model={model} hidden={!!selected || showBrief || chatOpen} pack={pack} onPack={(o) => { setPack((p) => (p === o ? null : o)); setChatMatches(null); }} />}
      <Presence>{scrub && timeline && <Scrubber key="scrub" entries={timeline.entries} nodes={model.nodes} firstSeen={timeline.first_seen} date={scrub} onDate={setScrub} onClose={() => setScrub(null)} />}</Presence>
      {!selected && <p className="pointer-events-none fixed right-6 bottom-6 hidden text-xs text-text-3 sm:block">Drag to move, scroll to zoom, arrows to step</p>}
      <Presence>{selected && showInspector && (
        <Suspense key="inspector" fallback={<InspectorSkeleton item={selected} />}>
          <Inspector model={model} item={selected} brief={brief ?? undefined} assessments={assessments} habits={habits} onFind={setQuery} onAsk={ask} onCluster={(c) => enter(c, true)} onSelect={select} onPreview={setPreview} onClose={close} backTo={narrow ? cluster?.name : undefined} whatIf={whatIf} removed={removed} onToggle={toggleRemove} />
        </Suspense>
      )}</Presence>
      <Presence>{removed && !showBrief && <WhatIfChip key="whatif" count={removed.size} saved={budget(model.nodes, removed).saved} onReset={() => { setWhatIf(new Set()); setLive("What-if reset"); }} onExit={() => startWhatIf(false)} />}</Presence>
      <p className="sr-only" aria-live="polite">{live}</p>
      <p className="sr-only" aria-live="polite">{selected ? `Selected ${selected.name}, ${verdictOf(selected, assessments).label}` : ""}</p>
    </>
  );
}
