from collections.abc import Callable
from pathlib import Path

from . import origins as origin_sources
from .claude_code import read_items, read_secrets
from .cluster import item_vectors
from .models import LLM, Cluster, Constellation, Embedder, ProjectUsage, TokenCounter
from .redact import ProviderError, guarded, guarded_count, guarded_embed
from .scan_graph import Context, run
from .usage import connector_items, read_usage


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
    origins: bool = True,
    lockfile: Path | None = None,
    project: Path | None = None,
    checkpoint: Path | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> Constellation:
    """`origins` reads where each Item came from, locally (the lockfile's `source` field only, at `lockfile`, else the skills CLI's own).
    `checkpoint` is a file to save the scan's progress in, so an interrupted scan resumes without repeating paid calls
    (none: nothing is written); it holds ids, hashes, labels and redacted model replies only, and is emptied when the scan
    succeeds. `on_progress` gets one line per step.
    `offline` makes no provider calls: any llm, counter and verifier given are ignored, and costs come from the cache alone."""
    if offline:
        llm = counter = verifier = None
    items, warnings, relations, bodies = read_items(config_dir, (lockfile or origin_sources.DEFAULT_LOCKFILE) if origins else None, project)
    usages, window, usage_warnings, by_project = (
        read_usage(config_dir, items, relations, project, Path.home()) if usage else ({}, None, [], ProjectUsage())
    )
    warnings += usage_warnings
    items += connector_items(usages)  # before labels and clusters, so a connector seen only in transcripts has a place on the map
    # The only place providers are called from: all are wrapped here, so everything they receive is redacted first.
    secrets = read_secrets(config_dir, project) if llm or embedder or counter or verifier or offline else set()
    vectors: dict[str, list[float]] = {}  # stays empty without an embedder, or when it fails
    centred = False
    embed_error = None
    if embedder:  # clusters are built from name and description alone, so they need no model
        try:
            vectors, centred = item_vectors(items, guarded_embed(embedder, secrets))
        except ProviderError as error:
            embed_error = str(error)
    context = Context(
        config_dir,
        items,
        bodies,
        secrets,
        guarded(llm, secrets) if llm else None,
        guarded(verifier, secrets) if verifier else None,
        guarded_count(counter, secrets) if counter else None,
        embedder,
        offline,
        count_bodies,
        vectors,
        centred,
        embed_error,
        cluster_threshold,
        cost_cache,
        label_cache,
        verdict_cache,
        label_model,
        verifier_model,
        on_verify,
        relations=relations,
    )
    state = run(context, checkpoint, on_progress)
    warnings += state["final_warnings"]
    # shortcut: user CLAUDE.md only, no @imports or project CLAUDE.md; upgrade when the scan reads projects (#43)
    memory = Path(config_dir) / "CLAUDE.md"
    try:
        memory_bytes = memory.stat().st_size if memory.is_file() else None  # stat only: the text is never opened
    except OSError:
        memory_bytes = None
    return Constellation(
        items,
        warnings,
        relations,
        state.get("labels", {}),
        state.get("clusters", []),
        state.get("costs", {}),
        state["final_overlaps"],
        usage=usages,
        usage_window=window,
        hook_weights=state["hook_weights"],
        projects=by_project.projects,
        usage_by_project=by_project.by_project,
        current_project=by_project.current,
        memory_bytes=memory_bytes,
    )


__all__ = ["scan", "Cluster", "Constellation", "Item"]
