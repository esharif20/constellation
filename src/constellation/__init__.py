from pathlib import Path

from .classify import classify
from .claude_code import read_items, read_secrets
from .cluster import DEFAULT_THRESHOLD, cluster
from .models import LLM, Cluster, Constellation, Embedder, Item
from .redact import ProviderError, guarded, guarded_embed


def scan(
    config_dir: Path,
    llm: LLM | None = None,
    embedder: Embedder | None = None,
    cluster_threshold: float = DEFAULT_THRESHOLD,
) -> Constellation:
    items, warnings, relations = read_items(config_dir)
    labels: dict[str, str] = {}
    clusters: list[Cluster] = []
    # The only place providers are called from: both are wrapped here, so everything they receive is redacted first.
    secrets = read_secrets(config_dir) if llm or embedder else set()
    if llm:
        labels, label_warnings = classify(items, guarded(llm, secrets))
        warnings += sorted(label_warnings)  # branches finish in any order; sorted keeps the output repeatable
    if embedder:  # clusters are built from name and description alone, so they need no model
        try:
            clusters = cluster(items, labels, guarded_embed(embedder, secrets), cluster_threshold)
        except ProviderError as error:
            warnings.append(f"could not cluster items: {error}")
    return Constellation(items, warnings, relations, labels, clusters)


__all__ = ["scan", "Cluster", "Constellation", "Item"]
