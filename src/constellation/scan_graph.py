"""The whole scan as one LangGraph graph (#22). Nodes call the same functions scan() always called; only the wiring is new.

Privacy: `State` is what the checkpointer saves to disk, so it holds ids, cache keys, labels, numbers and model replies only,
and every string a node puts into it goes through `Context.safe` (redact) first. Everything with file text in it (Items, bodies,
descriptions, vectors, project labels, secrets) lives in `Context`, which LangGraph never saves."""

import functools
import hashlib
import json
import operator
import re
import sqlite3
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langgraph.errors import GraphInterrupt
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, Send, interrupt

from . import selfcheck
from .checkpoint import Checkpointer, close_checkpointer, open_checkpointer
from .classify import MAX_CONCURRENCY, _prompt, label_flush, label_one, label_plan
from .costs import cache_key, count_texts, measure
from .grouping import WORDS_ONLY_WARNING, group_items
from .hooks import static_hook_texts
from .models import LLM, Cluster, Cost, Embedder, Item, Overlap, Relation, TokenCounter, Weight
from .overlaps import (
    BAND_LOW,
    MAX_PAIRS,
    _parse,
    announce_cost,
    check_one,
    exact_duplicates,
    pair_job,
    rank,
    verify_flush,
    verify_plan,
    wrappers,
)
from .overlaps import _prompt as _pair_prompt
from .redact import redact

DEFAULT_CHECKPOINT = Path.home() / ".cache" / "constellation" / "scan.sqlite"
STATE_TYPES = tuple(("constellation.models", name) for name in ("Cluster", "Cost", "Overlap", "Weight"))  # what State may hold
MEMORY_FILE = "CLAUDE.md"  # pragma: no mutate  (file names are case-insensitive on macOS, so a changed case cannot be told apart)
CACHE_KEY = re.compile(r"[0-9a-f]{64}")
QUOTED_PATH = re.compile(r"""(['"])(?:/|[A-Za-z]:\\)[^'"]*\1""")
CHECKPOINT_WARNING = "Ignored an unreadable or foreign scan checkpoint; this scan ran from the start."
REVIEW_THREAD_TAG = "review-ambiguous"
MAX_REVIEW_STEPS = MAX_PAIRS + 1  # the initial stream plus at most one resume per capped pair
PROMPT_CONTROLS = re.compile(r"[\x00-\x1f\x7f-\x9f]")
PROMPT_DESCRIPTION_LIMIT = 200
PAIR_CHOICES = ("skip", "same", "different")
HUMAN_VERDICTS = {1: ("duplicate", "Human review: same job."), 2: ("distinct", "Human review: different jobs.")}
REVIEW_SCHEMA = "CREATE TABLE IF NOT EXISTS pair_reviews (content_hash TEXT PRIMARY KEY, answer INTEGER NOT NULL)"
REVIEW_READ = "SELECT answer FROM pair_reviews WHERE content_hash = ?"
REVIEW_WRITE = "INSERT OR REPLACE INTO pair_reviews (content_hash, answer) VALUES (?, ?)"


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
    relations: list[Relation] = field(default_factory=list)
    ask_pairs: Callable[[str, str], str] | None = None
    review_cache: Checkpointer | None = field(default=None, repr=False)
    _reviewed: dict[str, int] = field(default_factory=dict, repr=False)  # accepted answers survive this call's checkpoint fallback
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


class _ReviewCallbackError(Exception):
    """Keeps a caller-side failure separate from a failed graph node, leaving its pause intact."""


def _guarded[F: Callable[..., Any]](node: F) -> F:  # keeps the node's own signature for LangGraph and mypy
    @functools.wraps(node)
    def guarded(state: Any, runtime: Runtime[Context]) -> Any:
        try:
            return node(state, runtime)
        except GraphInterrupt:
            raise  # interrupt() is graph control flow, not an error message to reconstruct
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
    ranked: list[tuple[str, str, float]]  # candidate Item id pairs with their local ambiguity score, best first
    routes: Annotated[list[tuple[str, str]], operator.add]  # (pair, one-line reason it was not sent to the verifier)
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
    labels = {ctx.rid(k): v for k, v in state["labels"].items()}
    warnings: list[str] = []
    modelled = bool(ctx.embedder) and not ctx.embed_error
    if not modelled:  # no local model (or it failed): word and structure signals only, never no groups at all
        if ctx.embed_error:
            warnings.append(f"could not cluster items: {ctx.embed_error}")
        warnings.append(WORDS_ONLY_WARNING + selfcheck.model_hint())
    found = group_items(
        ctx.items,
        ctx.relations,
        labels,
        ctx.vectors if modelled and ctx.centred else None,  # raw cosines of a few Items are all near 1: no signal
        ctx.cluster_threshold,
    )
    return {
        "clusters": [replace(c, name=ctx.safe(c.name), item_ids=tuple(ctx.sid(i) for i in c.item_ids)) for c in found],
        "warnings": ctx.safe_warnings("cluster", warnings),
    }


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
def rank_pairs(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    """Free, local: order the proposed pairs by ambiguity and keep the verdict-cache hits. Only pairs at or above BAND_LOW
    and not cached become paid jobs; each skipped pair gets a route reason (the cost rule, written down)."""
    ctx = runtime.context
    if not ctx.verifier:
        return {}
    decided = {frozenset((ctx.rid(o.a_id), ctx.rid(o.b_id))) for o in state["local_overlaps"]}
    ranked, cap_warnings = rank(ctx.items, ctx.vectors, ctx.bodies, decided)
    score = {(a, b): s for a, b, s in ranked}
    cached, jobs = verify_plan([(a, b) for a, b, _ in ranked], ctx.items, ctx.bodies, ctx.secrets, ctx.verdict_cache, ctx.verifier_model)
    sent = [j for j in jobs if score[j["a"].id, j["b"].id] >= BAND_LOW]
    skipped = [j for j in jobs if score[j["a"].id, j["b"].id] < BAND_LOW]
    if sent and ctx.on_verify and not ctx._reviewed:  # the maximum possible estimate precedes any human prompt
        ctx.on_verify(*announce_cost(sent))
    return {
        "ranked": [(ctx.sid(a), ctx.sid(b), s) for a, b, s in ranked],
        "routes": [
            (
                f"{ctx.sid(j['a'].id)} / {ctx.sid(j['b'].id)}",
                f"below ambiguity band, {score[j['a'].id, j['b'].id]:.2f} < {BAND_LOW:.2f}",
            )
            for j in skipped
        ],
        "verdicts": [ctx.safe_overlap(o) for o in cached],
        "pair_jobs": [(ctx.sid(j["a"].id), ctx.sid(j["b"].id)) for j in sent],
        "warnings": ctx.safe_warnings("overlaps", cap_warnings),
    }


def route_pairs(state: State) -> list[Send] | str:
    """Second conditional edge + Send fan-out: one `verify` branch per pair the cache could not answer."""
    return [Send("verify", {"a_id": a, "b_id": b}) for a, b in state["pair_jobs"]] or "verdicts_done"


def _cached_review(saver: Checkpointer | None, key: str) -> int | None:
    if saver is None:
        return None
    with saver.lock, saver.conn:
        row = saver.conn.execute(REVIEW_READ, (key,)).fetchone()
    if row is not None and type(row[0]) is int and row[0] in range(len(PAIR_CHOICES)):
        return row[0]
    return None


def _review_pair(ctx: Context, prompt: str, pair: tuple[str, str]) -> tuple[int | None, str | None]:
    """Only a content hash and a numeric choice are cached, transactionally in the private SQLite file."""
    saver = ctx.review_cache
    key = cache_key(prompt, ctx.secrets)  # human answers do not expire when the verifier model changes
    if saver is None:
        return ctx._reviewed.get(key), None
    cached = _cached_review(saver, key)
    if cached is not None:
        ctx._reviewed[key] = cached
        return cached, None
    # The node restarts on Command(resume=...). Nothing paid happens before this interrupt;
    # the payload is ids only, because LangGraph saves it along with the pending task.
    answer = interrupt(pair)
    if type(answer) is not int or answer not in range(len(PAIR_CHOICES)):
        raise ValueError
    ctx._reviewed[key] = answer
    try:
        with saver.lock, saver.conn:
            saver.conn.execute(REVIEW_WRITE, (key, answer))
    except sqlite3.Error:
        return answer, "Could not cache pair review; this scan keeps the answer, but a later scan may ask again."
    return answer, None


@_guarded
def verify(state: _PairJob, runtime: Runtime[Context]) -> dict[str, Any]:
    ctx = runtime.context
    assert ctx.verifier  # only reached through a Send from rank_pairs
    job = pair_job(ctx.item(state["a_id"]), ctx.item(state["b_id"]), ctx.bodies, ctx.secrets, ctx.verifier_model)
    reviewing = ctx.review_cache is not None or bool(ctx._reviewed)
    choice, warning = _review_pair(ctx, job["prompt"], (state["a_id"], state["b_id"])) if reviewing else (0, None)
    if choice:
        verdict, reason = HUMAN_VERDICTS[choice]
        reply = json.dumps({"verdict": verdict, "reason": reason})
        result = check_one(job, lambda _: reply)
        result["replies"] = {}  # human decisions belong only in pair_reviews, never in the model-salted cache
    else:
        result = check_one(job, ctx.verifier)
    warnings = ([warning] if warning else []) + result.get("warnings", [])
    if "warnings" in result:
        return {"warnings": ctx.safe_warnings("overlaps", warnings)}
    # The paid reply is model output and may echo a secret or carry extra fields: save only a redacted copy that still parses.
    replies = {key: clean for key, reply in result["replies"].items() if _parse(clean := ctx.safe(reply))}
    update: dict[str, Any] = {"verdicts": [ctx.safe_overlap(o) for o in result["overlaps"]], "verdict_replies": replies}
    if warnings:
        update["warnings"] = ctx.safe_warnings("overlaps", warnings)
    return update


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
    for node in (plan_labels, label, labels_done, costs, local_overlaps, rank_pairs, verify, verdicts_done, assemble):
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
    graph.add_edge("local_overlaps", "rank_pairs")
    graph.add_conditional_edges("rank_pairs", route_pairs, ["verify", "verdicts_done"])  # pragma: no mutate  (only labels the drawn graph)
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
        *([REVIEW_THREAD_TAG] if context.ask_pairs is not None else []),
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
            elif node == "rank_pairs" and update:
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
    current: Any = start

    def pending() -> Any:
        return next((pause for task in graph.get_state(config).tasks for pause in task.interrupts), None)

    pause = pending() if context.review_cache is not None else None
    if context.review_cache is not None and tracker:
        tracker.done["verify"] = sum(task.name == "verify" and task.result is not None for task in graph.get_state(config).tasks)
    if pause is not None and context.on_verify:
        pairs = graph.get_state(config).values["pair_jobs"]
        tokens = sum(len(_pair_prompt(context.item(a), context.item(b), context.bodies)) // 4 for a, b in pairs)
        context.on_verify(len(pairs), tokens)  # same rough estimate as announce_cost; a resumed pause does not re-run rank_pairs
    for _ in range(MAX_REVIEW_STEPS):
        if pause is not None:
            a, b = pause.value
            key = cache_key(_pair_prompt(context.item(a), context.item(b), context.bodies), context.secrets)
            choice = _cached_review(context.review_cache, key)
            if choice is None:
                if progress:
                    for id_ in (a, b):
                        item = context.item(id_)
                        name = PROMPT_CONTROLS.sub("", context.safe(item.name))
                        description = PROMPT_CONTROLS.sub("", context.safe(item.description))[:PROMPT_DESCRIPTION_LIMIT]
                        progress(f"{name}: {description}")
                assert context.ask_pairs is not None
                try:
                    answer = context.ask_pairs(a, b)
                    if type(answer) is not str or answer not in PAIR_CHOICES:
                        raise ValueError("Pair review must return same, different or skip")
                except Exception as error:
                    raise _ReviewCallbackError from error
                choice = PAIR_CHOICES.index(answer)
            # Validate before Command: even an invalid resume value is saved by the checkpointer.
            # An id map targets exactly one pause, never reusing its answer for another Send branch.
            context._reviewed[key] = choice  # keep it even if saving the resume command fails before the node runs
            current = Command(resume={pause.id: choice})
        for mode, chunk in graph.stream(current, config, context=context, stream_mode=["updates", "values"], **options):
            if mode == "values":
                final = chunk  # Return only after every pending interrupt has been drained below.
            elif tracker and not (context.review_cache is not None and chunk.get("__metadata__", {}).get("cached")):
                # Review resumes replay completed Send updates; count those once, including after reopening the checkpoint.
                tracker(chunk)
        pause = pending() if context.review_cache is not None else None
        if pause is None:
            return context.restore(final)
    raise RuntimeError("Scan review exceeded the maximum number of resume steps.")


def _unchecked(context: Context, config: Any, progress: Callable[[str], None] | None) -> State:
    """The checkpoint file could not be used: run from the start without one, and say so (a fixed message, never the error text)."""
    config.pop("configurable", None)
    state = _stream(build_graph(), {"label_jobs": [], "pair_jobs": []}, replace(context, review_cache=None), config, progress, {})
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
            if context.ask_pairs is not None:
                with saver.lock, saver.conn:
                    saver.conn.execute(REVIEW_SCHEMA)
                context = replace(context, review_cache=saver)
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
        except _ReviewCallbackError as error:
            assert error.__cause__ is not None
            raise error.__cause__ from None  # the callback is outside the graph; keep its pending pause
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
