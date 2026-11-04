# Plan: the whole scan as one LangGraph graph (#22) with ambiguity ranking (#18)

Goal: `scan()` keeps its signature and results, but inside it runs one `StateGraph` with routing, a checkpointer,
progress streaming and an optional human pause. #18 adds a free local ambiguity score that keeps clearly distinct
pairs away from the paid verifier. Tracker decisions that apply: D12/D15 (LangGraph `StateGraph`, Anthropic SDK direct),
#7's `SqliteSaver` pattern in `review.py`, #16/#17 caches and offline mode, the privacy invariant and cost rule.

## Proposed deviations (need the owner's nod before T1)
1. **Local reading runs before the graph, not as nodes.** `read_items`, `read_usage`, `static_hook_texts`, `read_secrets`
   and the local embeddings run in `scan()` and go into the graph's runtime *context*, which is never checkpointed.
   Reason: anything a node returns lands in the checkpoint file, and these outputs hold file bodies, raw descriptions
   and vectors. Re-reading on resume is free, so nothing is lost.
2. **Suggestions stay in `review`.** `Constellation` has no suggestions field and `review` already builds them from the
   saved JSON with its own interrupt graph. A scan node would compute something nobody reads.
3. **No "strong model" stage for labels.** A label is routed by cache hit or miss; a second label model costs more for nothing.
4. **#18 drops only the low end.** A pair with very high similarity is still undecided (duplicate or overlap?), so only
   pairs below the band skip the verifier. Pairs above it go first, then the band. Same-name pairs are always sent.

## Graph

```
scan(config_dir, ...)  prelude, local, free: read items/bodies/usage/hooks/secrets, embed  -> ScanContext (not saved)
  |
START --+--> costs ---------------------------------------------------------------+
        |                                                                         |
        +--> plan_labels --(cache miss: Send x N)--> label --> labels_done --+    |
        |          \--(nothing to do / offline)----------------> labels_done |    |
        |                                                                    v    |
        +--> local_overlaps (exact, wrappers) --> rank (#18) --+       cluster    |
                                                               |         |        |
               route_pairs (conditional edge, per pair):       |         |        |
                 cached / below band / no verifier -> skip ----+         |        |
                 band and --ask-pairs ----> ask (interrupt) ---+         |        |
                 to verify ---------(Send x M)--> verify --> verdicts_done        |
                                                                    |    |        |
                                          [cluster, costs, verdicts_done] --> assemble --> END
```
`cluster` waits on `labels_done` (cluster names use labels). `assemble` waits on all three (a multi-source edge).

## State (everything here is saved by the checkpointer, so ids, keys, numbers and model replies only)
- `label_jobs: list[str]` Item ids to label; `labels: Annotated[dict[str, str], or_]` (cached merged in by `plan_labels`)
- `label_replies: Annotated[dict[str, str], or_]` cache key -> reply, flushed to the label cache in `labels_done`
- `clusters: list[Cluster]`, `costs: dict[str, Cost]`, `hook_weights: dict[str, Weight]`
- `local_overlaps: list[Overlap]`; `ranked: list[tuple[str, str, float]]` (pair ids and ambiguity score)
- `routes: Annotated[list[tuple[str, str]], add]` (pair or Item id, one-line reason it stopped where it did)
- `verdicts: Annotated[list[Overlap], add]`, `verdict_replies: Annotated[dict[str, str], or_]`
- `warnings: Annotated[dict[str, list[str]], _merge_stage]` keyed by stage; `assemble` joins them in today's order
  (usage, labels sorted, cluster, costs, hooks, overlaps sorted, offline) so parallel finishing order never shows.
- `Send` payloads carry ids only; nodes rebuild prompts from the context. (Send packets are saved too.)
- Context (`context_schema`, not saved): items, bodies, relations, usage, vectors, secrets, guarded providers, cache paths,
  model ids, `on_verify`, the ask callback. Providers are functions anyway and cannot be serialised.
- Every string a node writes to state passes through `redact(text, secrets)` first (warnings, reasons, labels).

## Existing functions as nodes
| node | calls (unchanged) |
|---|---|
| `costs` | `measure`, `count_texts`, hook `Weight`s (as lines 56-67 of `__init__.py` today) |
| `plan_labels` / `label` / `labels_done` | `classify.py`: `_prompt`, `cache_key`, `_clean`, `load_cache`/`save_cache` |
| `cluster` | `cluster()` (vectors already in context from `item_vectors`) |
| `local_overlaps` | `exact_duplicates`, `wrappers` |
| `rank` | `candidates()` plus new `ambiguity()` in `overlaps.py` |
| `verify` / `verdicts_done` | `overlaps.py`: `_prompt`, `_parse`, `_overlap`, cache helpers |
| `assemble` | builds `Constellation`, sorts Overlaps, adds the offline warning |
`classify()` and `verify()` stay as public functions running the same branch nodes as a small subgraph, so their tests stay.

## #18 ambiguity score (local, free)
`ambiguity(a, b) -> float` from: centred cosine, description word overlap (Jaccard), shared headings, mention either way,
same name. Send to the verifier only when score >= `BAND_LOW`; order by score so `MAX_PAIRS` keeps the best. Tune
`BAND_LOW` on `tests/eval/overlap_pairs.py` (names and descriptions only, so tune the cosine and word terms there):
recall on non-distinct pairs must not drop below the current baseline. `on_verify` already counts only the pairs that
will be sent, so the printed estimate shrinks with no extra work. Each skipped pair gets a route reason
("below ambiguity band, 0.18 < 0.30"). Trigger collisions (the #18 comment) are a separate later ticket.

## Checkpointer: location and privacy
- File `~/.cache/constellation/scan.sqlite`, created 0600 by the existing `open_checkpointer` (move it from `review.py`
  to a shared helper; review keeps its own file). `conftest.py` redirects it like `review.sqlite`.
- Off by default in the library: `scan(..., checkpoint: Path | None = None)`. The CLI passes the default path. A dry
  run passes none (it must write nothing real). Offline uses it too (harmless, it only skips paid nodes).
- `thread_id = "scan:" + sha256(sorted label and verdict cache keys + model ids)`. Same inputs after a crash: same thread,
  finished branches are reused. Changed setup: new thread. On success the thread is deleted (`delete_thread`), so the
  file holds at most one unfinished scan. Keeping the last finished state for a "what changed" view is later work.
- Stored: ids, cache keys (hashes), labels, verdict reasons (model output, max 200 chars), cluster names, numbers,
  redacted warnings. Never: bodies, descriptions, prompts, vectors, transcript text.
- Unchanged scan = zero paid calls still comes from the label and verdict caches, not the checkpointer.

## What each concept teaches (explain in a code comment where it first appears)
- `StateGraph` + state schema: the whole pipeline is data flowing through named steps you can draw and inspect.
- Reducers (`or_`, `add`, `_merge_stage`): how parallel branches write the same key without overwriting each other.
- `Send` fan-out: map-reduce, one branch per Item or pair, capped by `max_concurrency`.
- Conditional edges: the cost rule as code; a paid node only runs for what a free step could not decide.
- Multi-source edges: a join that waits for several branches.
- Runtime context vs state: what is saved and what is not; the privacy boundary of a checkpointer.
- Checkpointer + `thread_id`: a crash resumes from the last finished step; finished branches' writes are kept.
- `interrupt()` / `Command(resume=...)`: the node re-runs from its top on resume, so it must make no paid call before
  `interrupt()`. Payload is pair ids only.
- Subgraphs: `classify()`/`verify()` reuse the branch nodes; the parent checkpointer covers them.
- `stream(stream_mode="updates")`: progress lines on stderr ("labelled 12/40", "verify: 9 sent, 31 skipped").

## Migration (each step ends with all gates green)
1. Record golden outputs from today's `scan()` on invented fixtures (`claude_config`, `overlap_config`) with the fakes in
   `tests/fakes.py`: offline, labels only, labels+embedder+verifier, `count_bodies`, a failing provider. Save as JSON.
2. Add `scan_graph.py` with the graph whose nodes call `classify()` and `verify()` whole; `scan()` invokes it. Golden green.
3. Lift the two fan-outs into the outer graph (ids-only `Send`), `classify()`/`verify()` become subgraph wrappers. Golden green.
4. Add context vs state split, checkpointer, thread id, `durability="sync"`, streaming to stderr in the CLI. Golden green.
5. #18: `ambiguity()` and band routing. Golden is regenerated for the verifier cases only, in its own commit, with the
   recall check in the same commit.
6. Optional pause: `scan(..., ask_pairs=callback)` and `--ask-pairs`; absent by default, so golden stays green.

## Test plan
- Golden: new `scan()` equals the recorded JSON for every case above (field by field, warnings in order).
- Resume: a fake verifier raises after k calls; second `scan()` with the same checkpoint makes exactly (jobs - k) calls.
- Unchanged: a second scan of the same fixture makes zero calls to any fake provider.
- Privacy: plant a secret in a description, a body and a provider reply; grep the checkpoint bytes for it and for the
  body text; assert mode 0600. Assert no `Send` payload or state key holds an `Item`.
- Routing: a pair below the band never reaches the fake verifier and has a route reason; same-name pairs always sent.
- Recall: `tests/eval/test_overlap_quality.py` style check that the band keeps every non-distinct labelled pair.
- Interrupt: the ask callback sees pair ids; "skip" sends nothing; a crash mid-pause resumes at the same pair.
- Dry run: no checkpoint file is created; printed prompts unchanged. Offline: no provider called.
- mutmut: add `scan_graph.py` to `only_mutate`; boundary tests on `BAND_LOW` and the route conditions.

## Risks
- Checkpoint leaks: the main risk. Context/state split, redaction on write and the grep test cover it.
- Pending writes on crash: verify with a spike that SqliteSaver keeps finished `Send` branches when a sibling raises
  (it should; up to `max_concurrency` in-flight calls are redone).
- Multi-source join after a skipped conditional branch: each skip path must still reach `labels_done`/`verdicts_done`.
- Warning order and Overlap order drift with parallelism: handled in `assemble`, caught by golden.
- Threshold overfitting on ~20 invented pairs: keep `BAND_LOW` low; recall over savings.
- Sync `SqliteSaver` with parallel branches: open with `check_same_thread=False` as `review.py` does.

## Tickets for Sonnet
| # | scope | files owned | size |
|---|---|---|---|
| T1 | golden fixtures, `scan_graph.py` with whole-function nodes, staged warnings reducer, `assemble` | `scan_graph.py` (new), `__init__.py`, `tests/test_scan_golden.py`, `tests/fixtures/golden/` | M |
| T2 | lift fan-outs, ids-only `Send`, context split, subgraph wrappers | `scan_graph.py`, `classify.py`, `overlaps.py` (verify only) | M |
| T3 | checkpointer, thread id, resume and privacy tests, streaming, CLI wiring | `scan_graph.py`, `review.py` (helper move), `cli.py`, `tests/conftest.py`, `tests/test_scan_resume.py` | M |
| T4 | #18 `ambiguity()`, band routing, route reasons, tuning and recall | `overlaps.py` (candidates/ambiguity), `scan_graph.py` (route), `tests/test_overlap_ambiguity.py`, `tests/eval/` | M |
| T5 | optional `interrupt()` on band pairs, `--ask-pairs` | `scan_graph.py`, `cli.py`, `tests/test_scan_ask.py` | S |
T1 -> T2 -> T3 in order (same file). T4 can start after T2. T5 after T3. Opus reviews T3 (writes a file of state).

## Tonight vs later
- Tonight: owner approves the four deviations; T1 and T2 (pure refactor, golden-protected, no new file written).
- Later: T3 (needs the privacy review), T4 (needs a careful tuning pass), T5, trigger collisions, "what changed since
  last time" (keep the last finished state), and a route field in the output JSON if stderr is not enough.
