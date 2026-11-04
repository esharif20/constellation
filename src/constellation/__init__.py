from collections.abc import Callable
from pathlib import Path

from .classify import classify
from .claude_code import read_items, read_secrets
from .cluster import cluster, item_vectors
from .costs import count_texts, measure
from .hooks import static_hook_texts
from .models import LLM, Cluster, Constellation, Cost, Embedder, TokenCounter, Weight
from .overlaps import candidates, exact_duplicates, verify, wrappers
from .redact import ProviderError, guarded, guarded_count, guarded_embed
from .usage import read_usage


def scan(
    config_dir: Path,
    llm: LLM | None = None,
    embedder: Embedder | None = None,
    cluster_threshold: float | None = None,
    counter: TokenCounter | None = None,
    count_bodies: bool = False,
    cost_cache: Path | None = None,
    verifier: LLM | None = None,
    verdict_cache: Path | None = None,
    on_verify: Callable[[int, int], None] | None = None,
    label_cache: Path | None = None,
    label_model: str = "",
    verifier_model: str = "",
    offline: bool = False,
    usage: bool = True,
) -> Constellation:
    """`offline` makes no provider calls: any llm, counter and verifier given are ignored, and costs come from the cache alone."""
    if offline:
        llm = counter = verifier = None
    items, warnings, relations, bodies = read_items(config_dir)
    usages, window, usage_warnings = read_usage(config_dir, items, relations) if usage else ({}, None, [])
    warnings += usage_warnings
    labels: dict[str, str] = {}
    vectors: dict[str, list[float]] = {}  # stays empty without an embedder, or when it fails
    clusters: list[Cluster] = []
    # The only place providers are called from: both are wrapped here, so everything they receive is redacted first.
    secrets = read_secrets(config_dir) if llm or embedder or counter or verifier or offline else set()
    if llm:
        labels, label_warnings = classify(items, guarded(llm, secrets), secrets, label_cache, label_model)
        warnings += sorted(label_warnings)  # branches finish in any order; sorted keeps the output repeatable
    if embedder:  # clusters are built from name and description alone, so they need no model
        try:
            vectors, centred = item_vectors(items, guarded_embed(embedder, secrets))
            clusters = cluster(items, labels, vectors, centred, cluster_threshold)
        except ProviderError as error:
            warnings.append(f"could not cluster items: {error}")
    costs: dict[str, Cost] = {}
    guarded_counter = guarded_count(counter, secrets) if counter else None
    if counter or offline:
        costs, cost_warnings = measure(items, bodies if count_bodies else {}, guarded_counter, secrets, cost_cache)
        warnings += cost_warnings
    hook_texts = static_hook_texts(config_dir, items)
    weights = {id_: Weight(None if t is None else len(t.encode()), None) for id_, t in hook_texts.items()}
    if count_bodies and (counter or offline):  # hook text is file text, so it follows the same opt-in as skill bodies
        known_texts = {id_: t for id_, t in hook_texts.items() if t is not None}
        tokens, hook_warnings = count_texts(known_texts, guarded_counter, secrets, cost_cache)
        weights |= {id_: Weight(weights[id_].bytes, n) for id_, n in tokens.items()}
        warnings += hook_warnings
    overlaps = [*exact_duplicates(items, bodies), *wrappers(items, bodies)]
    if verifier:
        decided = {frozenset((o.a_id, o.b_id)) for o in overlaps}
        pairs, cap_warnings = candidates(items, vectors, decided)
        verdicts, verify_warnings = verify(
            pairs, items, bodies, guarded(verifier, secrets), secrets, verdict_cache, on_verify, verifier_model
        )
        overlaps += verdicts
        warnings += sorted(cap_warnings + verify_warnings)  # branches finish in any order; sorted keeps the output repeatable
    if offline:
        warnings.append("Offline: no labels or model-checked Overlaps; token costs shown only if already cached.")
    overlaps.sort(key=lambda o: (o.a_id, o.b_id))
    return Constellation(
        items, warnings, relations, labels, clusters, costs, overlaps, usage=usages, usage_window=window, hook_weights=weights
    )


__all__ = ["scan", "Cluster", "Constellation", "Item"]
