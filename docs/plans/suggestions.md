# Plan: Suggestions with approve/skip and resume (#7, D5)

Goal: turn the Overlaps in a saved scan into Suggestions, ask about them one at a time (approve, skip, quit), remember every answer in a LangGraph checkpoint, and write the approved ones to `cleanup.md`. Constellation never edits or deletes user config. The only file it writes is the checklist.

## Shape: a `review` step after the scan, not inside `scan()`

`constellation review [FILE]` reads a saved `constellation.json`. It does not read the config directory. This means:
- a scan never waits on a human, so scans stay scriptable, and #22 can later wrap `scan()` in one graph without a human pause in the middle;
- review makes no network calls, needs no key and costs nothing (Cost rule);
- #22 can attach the review graph to the scan graph as a subgraph node later. Nothing here blocks that.

## Suggestion model (`src/constellation/suggestions.py`, pure, mutation-tested)

```
Decision = Literal["approve", "skip"]
@dataclass(frozen=True)
class Suggestion:
    id: str                    # sha256(kind + "\0" + "\0".join(item_ids))[:12]
    kind: Literal["remove_duplicate", "use_underlying"]
    item_ids: tuple[str, ...]  # duplicate: sorted; wrapper: (wrapper, wrapped)
    reason: str                # plain English, redact()ed
    tokens_saved: int | None   # None = unknown, never 0
def suggest(data: dict[str, Any]) -> list[Suggestion]
GENERATORS: list[Callable[[dict[str, Any]], list[Suggestion]]]
```
- It works on the saved JSON dict, the same input as `report.py`. Item ids (`claude-code:skill:...`) are already stable across scans, so the content-derived id is too, and old decisions still apply after a re-scan.
- `_duplicates`: every Overlap with verdict `duplicate` (hash or verifier) gives "Remove one of these two: A and B. <reason>". `tokens_saved` is the smaller of the two always-on costs, or `None` if either cost is unknown.
- `_wrappers`: verdict `wrapper` gives "A only calls B; consider using B directly." `tokens_saved` is A's always-on cost, or `None`.
- Order: known `tokens_saved` first, largest first, then unknown, ties broken by id. The same input always gives the same order.
- #20 (usage from transcripts) adds `_unused_always_on` to `GENERATORS`. It is not shipped now. `overlap` and `distinct` verdicts produce nothing.

## The review graph (`src/constellation/review.py`)

```
class ReviewState(TypedDict):
    suggestions: list[str]                                  # ids for this run; each new invoke replaces it
    decisions: Annotated[dict[str, Decision], _merge]       # _merge = lambda a, b: {**a, **b}
def build_review_graph(checkpointer: BaseCheckpointSaver) -> CompiledStateGraph
def open_checkpointer(path: Path = DEFAULT_CHECKPOINT) -> SqliteSaver   # creates the file 0600, chmods an existing one
def thread_id(file: Path) -> str                                       # "review:" + str(file.resolve())
```
Graph: `START -> ask`. A conditional edge loops `ask -> ask` while any id is undecided, then goes to `END`. `ask` finds the first undecided id, calls `answer = interrupt(id)`, and returns `{"decisions": {id: answer}}`. Each answer is its own checkpointed step, so a crash loses at most the question on screen.

Privacy: the checkpoint holds only ids and decisions. The interrupt payload is the id, not text. The CLI looks up the reason locally. `DEFAULT_CHECKPOINT = ~/.cache/constellation/review.sqlite`. `tests/conftest.py` redirects it to a temp path, like the other caches.

### LangGraph concepts exercised
- **`interrupt(value)`** stops the graph inside a node, saves state, and hands `value` back to the caller as `result["__interrupt__"]`.
- **`Command(resume=answer)`** continues a stopped graph. The paused `interrupt()` call returns `answer`, and the node runs on.
- **Checkpointer (`SqliteSaver`)** saves the state after every step to a file, so the state outlives the process. `InMemorySaver` is the same thing in RAM and is used in unit tests.
- **Thread id** (`config={"configurable": {"thread_id": ...}}`) names one saved conversation. One thread per scan file path, so decisions build up across sittings and re-scans.
- **Reducer** (`Annotated[..., _merge]`): `decisions` is merged, not replaced, so old answers survive a new run.
- **Resume after restart**: a new process opens the same SQLite file and thread. It can call `Command(resume=...)` on a pause left by another process (the web path), or `invoke` fresh input, which keeps the saved `decisions` and so re-asks nothing (the CLI path). `get_state(config)` shows what is paused.
- **`recursion_limit`**: a loop edge counts each pass as a step. Pass `len(suggestions) * 2 + 10`, because the default of 25 is too low.

## CLI session (`cli.main`)

```
review [FILE=constellation.json] [--out cleanup.md] [--force]
def main(..., decide: Callable[[Suggestion], str] | None = None)   # returns "a", "s" or "q"; default reads stdin
```
Loop: `result = graph.invoke({"suggestions": ids}, cfg)`. While `__interrupt__` is set, show the Suggestion (names, reason, tokens or "unknown") and read a/s/q. `q` or Ctrl+C breaks the loop and leaves the thread paused. Otherwise run `graph.invoke(Command(resume="approve"|"skip"), cfg)`. At the end, or on q, write `cleanup.md` from every approved id still present, and print "N approved, M skipped, K left".

`cleanup.md` comes from the existing `report.render_cleanup(data, *, top, approved: list[Suggestion] | None = None)`. With `approved` set, its "Duplicates" section becomes "## Approved Suggestions", one line per approval: `- [ ] <reason> Saves about N always-on tokens. (id abc123def456)`. The "never edits your config" header stays. `approved=None` keeps today's `report --cleanup` output byte for byte, so the golden files are unchanged. Writing reuses #19's rules (0600, refuses to overwrite without `--force`). Moving that writer into a shared helper is the one refactor here.

## Web resume (sketch only, UI is #10/#11)
`POST /review` starts a thread or continues one and returns `{suggestion}`, or `{done}`. `POST /review/decide {answer}` runs `Command(resume=answer)` on the same thread and SQLite file and returns the next Suggestion. A thread paused in the terminal can be finished in the browser.

## Tests and seams
- `tests/test_suggestions.py` (pure): one Suggestion per duplicate or wrapper; stable ids across reordered input; unknown cost stays `None`; ordering; reasons redacted. Add `suggestions.py` to mutmut `only_mutate` and kill every mutant.
- `tests/test_review.py` (graph with a temp SQLite file): approve and skip are recorded. In the restart test, process A pauses and its graph object is dropped. Process B builds a new graph on the same file, `Command(resume="approve")` lands, and the next pause is the next id. A fresh invoke after the run finishes asks nothing. The checkpoint file is mode 0600 and contains no reason text.
- `tests/test_cli_review.py` (`cli.main` with an injected `decide` returning a scripted list): approved lines appear in `cleanup.md`, skipped ones do not. Quitting and then re-running `main` starts at the same Suggestion. Missing file exits 2. A Constellation without Overlaps prints "No Suggestions".
- `tests/test_scan.py`: a tree snapshot (paths, bytes, mtimes) of a copied fixture config is identical after `cli.main(["scan", ...])`. This covers the acceptance check that the scan never writes to the config directory.

## Slices (red, then green, in order; Sonnet)
1. `Suggestion` and `suggest()` with `_duplicates`. 2. `_wrappers`, `tokens_saved`, ordering. 3. mutmut on `suggestions.py`.
4. Add `langgraph-checkpoint-sqlite`; `open_checkpointer` (0600) and its conftest redirect.
5. `build_review_graph`: the loop, interrupt and reducer (InMemorySaver). 6. Restart and resume test on SQLite.
7. `render_cleanup(approved=...)` plus the shared writer. 8. `review` command with injected `decide`. 9. Scan-never-writes test. 10. README, plan tracker D5, glossary check.

Slices 1-3, slice 4 and slice 9 can run in parallel. Slice 7 needs slice 1. Slice 8 needs slices 5 and 7.

## Risks
- Invoking fresh input on a thread paused at an interrupt has to drop the stale pause and keep `decisions`. Slice 6 proves this first. If it fails, the CLI calls `get_state` and resumes the pending id instead.
- `recursion_limit` on large setups (covered by a test with 30 Suggestions).
- New dependency `langgraph-checkpoint-sqlite` (official, small). Plain `InMemorySaver` cannot survive a restart.

## Out of scope
Applying any Suggestion. The web UI and endpoints (#10), chat (#11), usage-based Suggestions (#20), the scan as one graph (#22), suggestions for `overlap` verdicts, and a Suggestions section in `render_report`.
