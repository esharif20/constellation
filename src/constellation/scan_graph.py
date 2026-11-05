"""The whole scan as one LangGraph graph (#22). Nodes call the same functions scan() always called; only the wiring is new.

Privacy: `State` is what a checkpointer would save, so it holds ids, cache keys, labels, numbers and model replies only.
Everything with file text in it (Items, bodies, vectors, secrets) lives in `Context`, which LangGraph never saves."""

import operator
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Send

from .classify import MAX_CONCURRENCY, _prompt, label_flush, label_one, label_plan
from .cluster import cluster
from .costs import cache_key, count_texts, measure
from .hooks import static_hook_texts
from .models import LLM, Cluster, Cost, Embedder, Item, Overlap, TokenCounter, Weight
from .overlaps import announce_cost, candidates, check_one, exact_duplicates, pair_job, verify_flush, verify_plan, wrappers


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

    def item(self, id_: str) -> Item:
        return next(i for i in self.items if i.id == id_)


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


def plan_labels(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    """Free and local: labels already cached are merged in; only the rest becomes a paid job."""
    ctx = runtime.context
    if not ctx.llm:
        return {}
    labels, todo = label_plan(ctx.items, ctx.secrets, ctx.label_cache, ctx.label_model)
    return {"labels": labels, "label_jobs": [i.id for i in todo]}


def route_labels(state: State) -> list[Send] | str:
    """Conditional edge + Send fan-out (map): one parallel `label` branch per Item left to label, or straight to `labels_done`.
    This is the cost rule as code: a paid node runs only for what free work could not decide."""
    return [Send("label", {"item_id": id_}) for id_ in state["label_jobs"]] or "labels_done"


def label(state: _LabelJob, runtime: Runtime[Context]) -> dict[str, Any]:
    ctx = runtime.context
    assert ctx.llm  # only reached through a Send from plan_labels
    item = ctx.item(state["item_id"])
    result = label_one(item, ctx.llm)
    if "warnings" in result:
        return {"warnings": {"labels": result["warnings"]}}
    key = cache_key(_prompt(item), ctx.secrets, ctx.label_model)
    return {"labels": result["labels"], "label_replies": {key: result["labels"][item.id]}}


def labels_done(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    """Join (reduce): runs after every label branch, or at once when there were none."""
    ctx = runtime.context
    return {"warnings": {"labels": label_flush(ctx.label_cache, state["label_replies"])}}


def cluster_items(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    """Waits for `labels_done` (a plain edge), because cluster names come from the labels."""
    ctx = runtime.context
    if not ctx.embedder:
        return {}
    if ctx.embed_error:
        return {"warnings": {"cluster": [f"could not cluster items: {ctx.embed_error}"]}}
    return {"clusters": cluster(ctx.items, state["labels"], ctx.vectors, ctx.centred, ctx.cluster_threshold)}


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
    return {"costs": costs, "hook_weights": weights, "warnings": {"costs": warnings}}


def local_overlaps(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    ctx = runtime.context
    return {"local_overlaps": [*exact_duplicates(ctx.items, ctx.bodies), *wrappers(ctx.items, ctx.bodies)]}


def plan_pairs(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    ctx = runtime.context
    if not ctx.verifier:
        return {}
    decided = {frozenset((o.a_id, o.b_id)) for o in state["local_overlaps"]}
    pairs, cap_warnings = candidates(ctx.items, ctx.vectors, decided)
    cached, jobs = verify_plan(pairs, ctx.items, ctx.bodies, ctx.secrets, ctx.verdict_cache, ctx.verifier_model)
    if jobs and ctx.on_verify:  # before the first paid call
        ctx.on_verify(*announce_cost(jobs))
    return {"verdicts": cached, "pair_jobs": [(j["a"].id, j["b"].id) for j in jobs], "warnings": {"overlaps": cap_warnings}}


def route_pairs(state: State) -> list[Send] | str:
    """Second conditional edge + Send fan-out: one `verify` branch per pair the cache could not answer."""
    return [Send("verify", {"a_id": a, "b_id": b}) for a, b in state["pair_jobs"]] or "verdicts_done"


def verify(state: _PairJob, runtime: Runtime[Context]) -> dict[str, Any]:
    ctx = runtime.context
    assert ctx.verifier  # only reached through a Send from plan_pairs
    job = pair_job(ctx.item(state["a_id"]), ctx.item(state["b_id"]), ctx.bodies, ctx.secrets, ctx.verifier_model)
    result = check_one(job, ctx.verifier)
    if "warnings" in result:
        return {"warnings": {"overlaps": result["warnings"]}}
    return {"verdicts": result["overlaps"], "verdict_replies": result["replies"]}


def verdicts_done(state: State, runtime: Runtime[Context]) -> dict[str, Any]:
    ctx = runtime.context
    return {"warnings": {"overlaps": verify_flush(ctx.verdict_cache, state["verdict_replies"])}}


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
    overlaps = sorted([*state["local_overlaps"], *state["verdicts"]], key=lambda o: (o.a_id, o.b_id))
    return {"final_overlaps": overlaps, "final_warnings": warnings}


def build_graph() -> Any:  # shortcut: Any for the compiled graph, its generics are noise here
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
    return graph.compile()


def run(context: Context) -> State:
    """Compiled per call (cheap) so the wiring in build_graph is exercised, and mutation-tested, by every scan."""
    start: State = {"label_jobs": [], "pair_jobs": []}  # the reducer keys (labels, verdicts, warnings...) start empty by themselves
    return build_graph().invoke(start, context=context, config={"max_concurrency": MAX_CONCURRENCY})  # type: ignore[no-any-return]
