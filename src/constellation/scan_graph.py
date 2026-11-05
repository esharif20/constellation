"""The whole scan as one LangGraph graph (#22). Nodes call the same functions scan() always called; only the wiring is new.

Privacy: `State` is what the checkpointer saves to disk, so it holds ids, cache keys, labels, numbers and model replies only,
and every string a node puts into it goes through `Context.safe` (redact) first. Everything with file text in it (Items, bodies,
descriptions, vectors, project labels, secrets) lives in `Context`, which LangGraph never saves."""

import functools
import hashlib
import operator
import re
import sqlite3
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Send

from .checkpoint import close_checkpointer, open_checkpointer
from .classify import MAX_CONCURRENCY, _prompt, label_flush, label_one, label_plan
from .cluster import cluster
from .costs import cache_key, count_texts, measure
from .hooks import static_hook_texts
from .models import LLM, Cluster, Cost, Embedder, Item, Overlap, TokenCounter, Weight
from .overlaps import _parse, announce_cost, candidates, check_one, exact_duplicates, pair_job, verify_flush, verify_plan, wrappers
from .redact import redact

DEFAULT_CHECKPOINT = Path.home() / ".cache" / "constellation" / "scan.sqlite"
STATE_TYPES = tuple(("constellation.models", name) for name in ("Cluster", "Cost", "Overlap", "Weight"))  # what State may hold
MEMORY_FILE = "CLAUDE.md"  # pragma: no mutate  (file names are case-insensitive on macOS, so a changed case cannot be told apart)
CACHE_KEY = re.compile(r"[0-9a-f]{64}")
QUOTED_PATH = re.compile(r"""(['"])(?:/|[A-Za-z]:\\)[^'"]*\1""")
CHECKPOINT_WARNING = "Ignored an unreadable or foreign scan checkpoint; this scan ran from the start."


@dataclass
class Context:
    """Runtime context (`context_schema`): inputs every node can read but that are never written to a checkpoint.
    The providers are already the guarded ones, so everything they receive is redacted."""

    config_dir: Path
    items: list[Item]
    bodies: dict[str, str]
    secrets: set[str]
    llm: LLM | None = None
    verifier: LLM | None = None
    counter: TokenCounter | None = None
    embedder: Embedder | None = None
    offline: bool = False
    count_bodies: bool = False
    vectors: dict[str, list[float]] = field(default_factory=dict)  # empty without an embedder, or when it failed
    centred: bool = False
    embed_error: str | None = None
    cluster_threshold: float | None = None
    cost_cache: Path | None = None
    label_cache: Path | None = None
    verdict_cache: Path | None = None
    label_model: str = ""
    verifier_model: str = ""
    on_verify: Callable[[int, int], None] | None = None
    _alias: dict[str, str] = field(init=False, repr=False, default_factory=dict)  # Item id -> the id State holds
    _back: dict[str, str] = field(init=False, repr=False, default_factory=dict)

    def __post_init__(self) -> None:
        """State holds ids with any secret redacted out of the name part. Ids with none are unchanged; ids that would collide
        after redaction get a numeric suffix; `rid` maps back, so the scan's result keeps the real ids."""
        taken = {i.id for i in self.items}
        for n, item in enumerate(sorted(self.items, key=lambda i: i.id)):
            shown = self.safe(item.id)
            if shown != item.id and shown in taken:
                shown = f"{shown}#{n}"
            taken.add(shown)
            self._alias[item.id], self._back[shown] = shown, item.id

    def sid(self, id_: str) -> str:
        return self._alias.get(id_) or self.safe(id_)

    def rid(self, shown: str) -> str:
        return self._back.get(shown, shown)

    def item(self, id_: str) -> Item:
        real = self.rid(id_)
        return next(i for i in self.items if i.id == real)

    def safe(self, text: str) -> str:
        """The only way a string reaches State: redacted first, because State is written to disk."""
        return redact(text, self.secrets)

    def scrub(self, text: str) -> str:
        """`safe`, plus no absolute paths: quoted paths become <path> and the home directory becomes ~."""
        home = str(Path.home())
        text = QUOTED_PATH.sub(lambda m: f"{m[1]}<path>{m[1]}", text)  # before redact: a long path looks like a random token
        return self.safe(text.replace(home, "~") if len(home) > 1 else text)

    def safe_overlap(self, overlap: Overlap) -> Overlap:
        return replace(overlap, a_id=self.sid(overlap.a_id), b_id=self.sid(overlap.b_id), reason=self.safe(overlap.reason))

    def safe_warnings(self, stage: str, warnings: list[str]) -> dict[str, list[str]]:
        return {stage: [self.scrub(w) for w in warnings]}

    def restore(self, state: "State") -> "State":
        """The final State with the real Item ids back (what scan() builds the Constellation from)."""
        back = state.copy()
        if "labels" in back:
            back["labels"] = {self.rid(k): v for k, v in back["labels"].items()}
        if "clusters" in back:
            back["clusters"] = [replace(c, item_ids=tuple(self.rid(i) for i in c.item_ids)) for c in back["clusters"]]
        for key in ("costs", "hook_weights"):
            if key in back:
                back[key] = {self.rid(k): v for k, v in back[key].items()}  # type: ignore[typeddict-item]
        if "final_overlaps" in back:
            back["final_overlaps"] = [replace(o, a_id=self.rid(o.a_id), b_id=self.rid(o.b_id)) for o in back["final_overlaps"]]
        return back


class NodeError(Exception):
    """Stands in for an exception inside a node whose class cannot be rebuilt from a message alone."""


def _guarded[F: Callable[..., Any]](node: F) -> F:  # keeps the node's own signature for LangGraph and mypy
    @functools.wraps(node)
    def guarded(state: Any, runtime: Runtime[Context]) -> Any:
        try:
            return node(state, runtime)
        except Exception as error:
            # LangGraph saves repr(exception) in the checkpoint, so the original (its message may hold a secret or a home path)
            # must not be the one that propagates: raise the same class with a scrubbed message, and no chained cause.
            message = runtime.context.scrub(str(error))
            try:
                clean: Exception = type(error)(message)
            except Exception:
                clean = NodeError(f"{type(error).__name__}: {message}")
            raise clean from None

    return guarded  # type: ignore[return-value]


def _merge_stage(left: dict[str, list[str]], right: dict[str, list[str]]) -> dict[str, list[str]]:
    """Reducer for warnings, keyed by stage: parallel branches finish in any order, so each writes under its own stage
    and `assemble` joins the stages in today's fixed order."""
    return {stage: left.get(stage, []) + right.get(stage, []) for stage in left | right}


class State(TypedDict, total=False):
    # Reducers: when parallel branches write the same key in one step, LangGraph merges the writes with the key's reducer.
    # operator.or_ merges dicts, operator.add concatenates lists.
    label_jobs: list[str]  # Item ids still to label
    labels: Annotated[dict[str, str], operator.or_]
    label_replies: Annotated[dict[str, str], operator.or_]  # cache key -> label, flushed to the label cache
    clusters: list[Cluster]
    costs: dict[str, Cost]
    hook_weights: dict[str, Weight]
    local_overlaps: list[Overlap]
    pair_jobs: list[tuple[str, str]]  # Item id pairs still to verify
    verdicts: Annotated[list[Overlap], operator.add]
    verdict_replies: Annotated[dict[str, str], operator.or_]  # cache key -> reply
    warnings: Annotated[dict[str, list[str]], _merge_stage]
    final_overlaps: list[Overlap]
    final_warnings: list[str]


class _LabelJob(TypedDict):
    item_id: str  # Send payloads carry ids only: they are saved with the checkpoint, and nodes rebuild text from the Context


class _PairJob(TypedDict):
    a_id: str
    b_id: str


@_guarded
def plan_labels(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    """Free and local: labels already cached are merged in; only the rest becomes a paid job."""
    ctx = runtime.context
    if not ctx.llm:
        return {}
    labels, todo = label_plan(ctx.items, ctx.secrets, ctx.label_cache, ctx.label_model)
    return {"labels": {ctx.sid(id_): ctx.safe(text) for id_, text in labels.items()}, "label_jobs": [ctx.sid(i.id) for i in todo]}


def route_labels(state: State) -> list[Send] | str:
    """Conditional edge + Send fan-out (map): one parallel `label` branch per Item left to label, or straight to `labels_done`.
    This is the cost rule as code: a paid node runs only for what free work could not decide."""
    return [Send("label", {"item_id": id_}) for id_ in state["label_jobs"]] or "labels_done"


@_guarded
def label(state: _LabelJob, runtime: Runtime[Context]) -> dict[str, Any]:
    ctx = runtime.context
    assert ctx.llm  # only reached through a Send from plan_labels
    item = ctx.item(state["item_id"])
    result = label_one(item, ctx.llm)
    if "warnings" in result:
        return {"warnings": ctx.safe_warnings("labels", result["warnings"])}
    key = cache_key(_prompt(item), ctx.secrets, ctx.label_model)
    text = ctx.safe(result["labels"][item.id])  # a model reply may echo a secret; the redacted text is what is saved and cached
    return {"labels": {ctx.sid(item.id): text}, "label_replies": {key: text}}


@_guarded
def labels_done(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    """Join (reduce): runs after every label branch, or at once when there were none."""
    ctx = runtime.context
    return {"warnings": ctx.safe_warnings("labels", label_flush(ctx.label_cache, state["label_replies"]))}


@_guarded
def cluster_items(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    """Waits for `labels_done` (a plain edge), because cluster names come from the labels."""
    ctx = runtime.context
    if not ctx.embedder:
        return {}
    if ctx.embed_error:
        return {"warnings": ctx.safe_warnings("cluster", [f"could not cluster items: {ctx.embed_error}"])}
    labels = {ctx.rid(k): v for k, v in state["labels"].items()}
    found = cluster(ctx.items, labels, ctx.vectors, ctx.centred, ctx.cluster_threshold)
    return {"clusters": [replace(c, name=ctx.safe(c.name), item_ids=tuple(ctx.sid(i) for i in c.item_ids)) for c in found]}


@_guarded
def costs(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    """Independent of the other branches: it starts at the same time as the labels."""
    ctx = runtime.context
    costs: dict[str, Cost] = {}
    warnings: list[str] = []
    if ctx.counter or ctx.offline:
        costs, warnings = measure(ctx.items, ctx.bodies if ctx.count_bodies else {}, ctx.counter, ctx.secrets, ctx.cost_cache)
    hook_texts = static_hook_texts(ctx.config_dir, ctx.items)
    weights = {id_: Weight(None if t is None else len(t.encode()), None) for id_, t in hook_texts.items()}
    if ctx.count_bodies and (ctx.counter or ctx.offline):  # hook text is file text, so it follows the same opt-in as skill bodies
        known_texts = {id_: t for id_, t in hook_texts.items() if t is not None}
        tokens, hook_warnings = count_texts(known_texts, ctx.counter, ctx.secrets, ctx.cost_cache)
        weights |= {id_: Weight(weights[id_].bytes, n) for id_, n in tokens.items()}
        warnings += hook_warnings
    return {
        "costs": {ctx.sid(k): v for k, v in costs.items()},
        "hook_weights": {ctx.sid(k): v for k, v in weights.items()},
        "warnings": ctx.safe_warnings("costs", warnings),
    }


@_guarded
def local_overlaps(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    ctx = runtime.context
    found = [*exact_duplicates(ctx.items, ctx.bodies), *wrappers(ctx.items, ctx.bodies)]
    return {"local_overlaps": [ctx.safe_overlap(o) for o in found]}


@_guarded
def plan_pairs(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    ctx = runtime.context
    if not ctx.verifier:
        return {}
    decided = {frozenset((ctx.rid(o.a_id), ctx.rid(o.b_id))) for o in state["local_overlaps"]}
    pairs, cap_warnings = candidates(ctx.items, ctx.vectors, decided)
    cached, jobs = verify_plan(pairs, ctx.items, ctx.bodies, ctx.secrets, ctx.verdict_cache, ctx.verifier_model)
    if jobs and ctx.on_verify:  # before the first paid call
        ctx.on_verify(*announce_cost(jobs))
    return {
        "verdicts": [ctx.safe_overlap(o) for o in cached],
        "pair_jobs": [(ctx.sid(j["a"].id), ctx.sid(j["b"].id)) for j in jobs],
        "warnings": ctx.safe_warnings("overlaps", cap_warnings),
    }


def route_pairs(state: State) -> list[Send] | str:
    """Second conditional edge + Send fan-out: one `verify` branch per pair the cache could not answer."""
    return [Send("verify", {"a_id": a, "b_id": b}) for a, b in state["pair_jobs"]] or "verdicts_done"


@_guarded
def verify(state: _PairJob, runtime: Runtime[Context]) -> dict[str, Any]:
    ctx = runtime.context
    assert ctx.verifier  # only reached through a Send from plan_pairs
    job = pair_job(ctx.item(state["a_id"]), ctx.item(state["b_id"]), ctx.bodies, ctx.secrets, ctx.verifier_model)
    result = check_one(job, ctx.verifier)
    if "warnings" in result:
        return {"warnings": ctx.safe_warnings("overlaps", result["warnings"])}
    # The paid reply is model output and may echo a secret or carry extra fields: save only a redacted copy that still parses.
    replies = {key: clean for key, reply in result["replies"].items() if _parse(clean := ctx.safe(reply))}
    return {"verdicts": [ctx.safe_overlap(o) for o in result["overlaps"]], "verdict_replies": replies}


@_guarded
def verdicts_done(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    ctx = runtime.context
    return {"warnings": ctx.safe_warnings("overlaps", verify_flush(ctx.verdict_cache, state["verdict_replies"]))}


@_guarded
def assemble(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    """Multi-source join: `add_edge([...], "assemble")` waits until all three branches have finished.
    Puts the Overlaps and warnings into today's fixed order, so parallel finishing order never shows."""
    ctx = runtime.context
    stages = defaultdict(list, state["warnings"])
    warnings = [
        *sorted(stages["labels"]),
        *stages["cluster"],
        *stages["costs"],
        *sorted(stages["overlaps"]),
    ]
    if ctx.offline:
        warnings.append("Offline: no labels or model-checked Overlaps; token costs shown only if already cached.")
    overlaps = sorted([*state["local_overlaps"], *state["verdicts"]], key=lambda o: (ctx.rid(o.a_id), ctx.rid(o.b_id)))
    return {"final_overlaps": overlaps, "final_warnings": warnings}


def build_graph(checkpointer: Any = None) -> Any:  # shortcut: Any for the compiled graph and saver, their generics are noise here
    graph = StateGraph(
        State, context_schema=Context
    )  # pragma: no mutate  (the Runtime annotations on the nodes imply it; it documents the split)
    for node in (plan_labels, label, labels_done, costs, local_overlaps, plan_pairs, verify, verdicts_done, assemble):
        graph.add_node(node)
    graph.add_node("cluster", cluster_items)
    # Parallel branches: three edges out of START run in the same step.
    graph.add_edge(START, "costs")
    graph.add_edge(START, "plan_labels")
    graph.add_edge(START, "local_overlaps")
    graph.add_conditional_edges(
        "plan_labels", route_labels, ["label", "labels_done"]
    )  # pragma: no mutate  (the path list only labels the drawn graph)
    graph.add_edge("label", "labels_done")
    graph.add_edge("labels_done", "cluster")
    graph.add_edge("local_overlaps", "plan_pairs")
    graph.add_conditional_edges("plan_pairs", route_pairs, ["verify", "verdicts_done"])  # pragma: no mutate  (only labels the drawn graph)
    graph.add_edge("verify", "verdicts_done")
    graph.add_edge(["cluster", "costs", "verdicts_done"], "assemble")
    graph.add_edge("assemble", END)
    return graph.compile(checkpointer=checkpointer)


def thread_id(context: Context) -> str:
    """Names this scan for the checkpointer. Hashes only (of redacted text): for each Item its id, scope, name and description and
    its body (the verifier reads bodies); the text hooks inject; the size of CLAUDE.md; then the model ids and which stages are on.
    The same setup after a crash gets the same thread and resumes; any change gets a new thread and starts fresh."""
    hooks = static_hook_texts(context.config_dir, context.items)
    memory = Path(context.config_dir) / MEMORY_FILE
    parts = [
        *sorted(
            f"{cache_key(i.id, context.secrets)}:{i.scope}:{cache_key(_prompt(i), context.secrets)}:"
            f"{cache_key(context.bodies.get(i.id, ''), context.secrets)}"
            for i in context.items
        ),
        *sorted(f"{context.sid(id_)}={cache_key(repr(text), context.secrets)}" for id_, text in hooks.items()),
        str(memory.stat().st_size if memory.is_file() else None),
        context.label_model,
        context.verifier_model,
        *(str(flag) for flag in (bool(context.llm), bool(context.verifier), bool(context.counter), bool(context.embedder))),
        str(context.offline),
        str(context.count_bodies),
        str(context.cluster_threshold),
    ]
    return "scan:" + hashlib.sha256("\0".join(parts).encode()).hexdigest()  # pragma: no mutate  (any separator keeps the parts apart)


class _Progress:
    """Turns the graph's per-node updates into stderr-style lines: "labelled 12/40", "verified 9/31"."""

    def __init__(self, say: Callable[[str], None], total: dict[str, int]):
        self.say, self.done, self.total = say, {"label": 0, "verify": 0}, total

    def __call__(self, updates: dict[str, Any]) -> None:
        for node, update in updates.items():
            if node == "plan_labels" and update:
                self.total["label"] = len(update["label_jobs"])
            elif node == "plan_pairs" and update:
                self.total["verify"] = len(update["pair_jobs"])
            elif node in ("label", "verify"):
                self.done[node] += 1
                self.say(f"{'labelled' if node == 'label' else 'verified'} {self.done[node]}/{self.total[node]}")


def _stream(
    graph: Any, start: State | None, context: Context, config: Any, progress: Callable[[str], None] | None, total: dict[str, int]
) -> State:
    """Runs the graph with `stream`, not `invoke`: the "updates" chunks (one per finished node) drive the progress lines and the
    "values" chunks end with the final State. durability="sync" saves each step before the next starts."""
    tracker = _Progress(progress, total) if progress else None
    final: State = {}  # pragma: no mutate  (a graph always ends with a "values" chunk)
    options: Any = {"durability": "sync"} if "configurable" in config else {}  # durability needs a checkpointer
    for mode, chunk in graph.stream(start, config, context=context, stream_mode=["updates", "values"], **options):
        if mode == "values":
            final = chunk
        elif tracker:
            tracker(chunk)
    return context.restore(final)


def _unchecked(context: Context, config: Any, progress: Callable[[str], None] | None) -> State:
    """The checkpoint file could not be used: run from the start without one, and say so (a fixed message, never the error text)."""
    config.pop("configurable", None)
    state = _stream(build_graph(), {"label_jobs": [], "pair_jobs": []}, context, config, progress, {})
    state["final_warnings"] = [*state["final_warnings"], CHECKPOINT_WARNING]
    return state


def _salvage(saver: Any, tid: str, context: Context) -> None:
    """Cost rule: before a saved scan is thrown away, its paid replies (including those of branches that finished in a step that
    never completed: LangGraph keeps them as pending writes) go into the label and verdict caches, so an edit to one file
    repeats only that file's call. Only 64-hex keys with string values are accepted, and the text is redacted again."""
    try:
        saved = saver.get_tuple({"configurable": {"thread_id": tid}})
        if saved is None:
            return
        found: dict[str, dict[str, Any]] = {"label_replies": {}, "verdict_replies": {}}
        sources = [saved.checkpoint["channel_values"], *({channel: value} for _, channel, value in saved.pending_writes or [])]
        for source in sources:
            for channel, kept in found.items():
                value = source.get(channel)
                if isinstance(value, dict):
                    kept |= {
                        k: context.safe(v) for k, v in value.items() if isinstance(k, str) and CACHE_KEY.fullmatch(k) and isinstance(v, str)
                    }
        label_flush(context.label_cache, found["label_replies"])
        verify_flush(context.verdict_cache, found["verdict_replies"])
    except Exception:  # a damaged old checkpoint must not stop the scan
        return


def _drop_threads(saver: Any, context: Context, keep: str | None = None) -> None:
    """Delete every saved scan except `keep`, salvaging their paid replies first."""
    for old in {c.config["configurable"]["thread_id"] for c in saver.list(None)} - {keep}:
        _salvage(saver, old, context)
        saver.delete_thread(old)


def run(context: Context, checkpoint: Path | None = None, progress: Callable[[str], None] | None = None) -> State:
    """Compiled per call (cheap) so the wiring in build_graph is exercised, and mutation-tested, by every scan.

    LangGraph lesson, checkpointer + thread_id: with a checkpointer the graph saves its State after every step, under a
    `thread_id`. If the process dies, `invoke(None, config)` / `stream(None, config)` with the same thread_id resumes from the last
    saved step and keeps the results of branches that had finished, so paid label and verify calls are not repeated. (Passing a
    new input instead would start a new run on that thread.) Only State is saved; the Context is handed in again on every run.
    No `checkpoint` path: nothing is written. The thread is deleted when the scan succeeds, so the file holds at most one
    unfinished scan. The cache is never worth a failed scan: a locked file (another scan is using it), a SQLite error or an
    unreadable file means the scan runs without a checkpoint, with a fixed warning."""
    start: State = {"label_jobs": [], "pair_jobs": []}  # the reducer keys (labels, verdicts, warnings...) start empty by themselves
    config: Any = {"max_concurrency": MAX_CONCURRENCY}
    if checkpoint is None:
        return _stream(build_graph(), start, context, config, progress, {})
    try:
        saver = open_checkpointer(checkpoint, STATE_TYPES, lock=True)
    except (OSError, sqlite3.Error):
        return _unchecked(context, config, progress)
    try:
        graph, tid = build_graph(saver), thread_id(context)
        config["configurable"] = {"thread_id": tid}
        try:
            snapshot = graph.get_state(config)  # reading a corrupt or foreign file can fail in many ways
            resuming = bool(snapshot.next)
            # a resumed run replays the finished branches' results as updates: the count restarts at 0, the totals come from the plan
            total = {"label": len(snapshot.values.get("label_jobs", [])), "verify": len(snapshot.values.get("pair_jobs", []))}
            if not resuming:  # a different or finished scan's leftovers go, so the file holds at most one unfinished scan
                _drop_threads(saver, context)
        except Exception:
            return _unchecked(context, config, progress)
        if resuming and progress:
            progress("resuming an interrupted scan")
        try:
            state = _stream(graph, None if resuming else start, context, config, progress, total)
        except sqlite3.Error:
            return _unchecked(context, config, progress)
        except Exception:
            try:
                _salvage(saver, tid, context)
                saver.delete_thread(tid)  # a failed scan leaves nothing behind (the error text is redacted, but it is not needed)
            except sqlite3.Error:
                pass
            if not resuming:
                raise
            return _unchecked(context, config, progress)  # the saved step no longer fits this graph: start over
        try:
            saver.delete_thread(tid)
        except sqlite3.Error:  # the next scan clears it
            pass
        return state
    finally:
        close_checkpointer(saver)
