from pathlib import Path

from .classify import classify
from .claude_code import read_items, read_secrets
from .cluster import DEFAULT_THRESHOLD, cluster
from .models import LLM, Cluster, Constellation, Embedder, Item
from .redact import guarded, guarded_embed


def scan(
    config_dir: Path,
    llm: LLM | None = None,
    embedder: Embedder | None = None,
    cluster_threshold: float = DEFAULT_THRESHOLD,
) -> Constellation:
    items, warnings, relations = read_items(config_dir)
    labels: dict[str, str] = {}
    clusters: list[Cluster] = []
    if llm:
        # The only place providers are called from: both are wrapped here, so everything they receive is redacted first.
        secrets = read_secrets(config_dir)
        labels = classify(items, guarded(llm, secrets))
        if embedder:  # clusters are named from labels, so they need both providers
            clusters = cluster(items, labels, guarded_embed(embedder, secrets), cluster_threshold)
    return Constellation(items, warnings, relations, labels, clusters)


__all__ = ["scan", "Cluster", "Constellation", "Item"]
