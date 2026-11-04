# Plan tracker

The approved plan (decisions D1 to D17) lives outside the repo at `~/.claude/plans/pasted-content-id-d61b-i-think-modular-fog.md`.
This file is the in-repo copy of its status. Update it in every ticket (see "Plan alignment" in CLAUDE.md). A decision that changed is
recorded as a **deviation** with the reason, and the user approves it, instead of drifting silently.

| Decision | Plan | Status | Notes |
|---|---|---|---|
| D1 Source adapter seam | Claude Code only, adapter seam | Done (#2, #4) | ADR 0001 |
| D2 Expansion on demand | click or `expand` opens an Item | Open (#9) | ADR 0002 |
| D3 Overlaps | hash + wrapper, embeddings propose, Sonnet verifies, ~20 labelled pairs | Done (#6), verified on the real setup | plan in `docs/plans/overlaps.md`. **Privacy amendment (user decided):** the verifier gets names, descriptions and local signals only; file bodies never go to a model. Verifier is `claude-sonnet-5-5` via the SDK (D15). Real setup: `stop-slop`, `shadcn` and `skill-creator` all surface as duplicates. Real-model eval (2026-11-04, claude-sonnet-5-5, 20 invented pairs, ~$0.20): 19 of 20 verdicts correct, flagged precision 1.00, recall 0.93; the one miss labelled an "overlap" pair "distinct". The pairs are invented by us, so this is a regression guard, not proof |
| D4 Privacy | redaction before every provider call, reused by the Snapshot | Done for scan (#3, #5); Snapshot export open (#13) | covers LLM, embedder and counter |
| D5 Suggestions | `interrupt()` per suggestion, approve or skip, writes `cleanup.md` | Done (#7) | `constellation review`; never modifies user config |
| D6 Interface | chat on the left, graph on the right, served by FastAPI | Graph done (#8); free local answers done (#11 phase 1) | Optional local generation deferred |
| D7 CLI | **Typer** `scan, expand, open, export --public` | **Deviation, approved by the user (2026-11-03)**: `argparse` with `scan` and `open` | keep; revisit only if the CLI outgrows it |
| D8 Chat | tool-calling agent driving the graph | Free local routing, retrieval and graph actions done (#11 phase 1) | Model synthesis deferred by user direction |
| D10 Public demo | sanitised static Snapshot on Vercel | Open (#13, #14, #15) | |
| D11 Context cost | `always_on` and `on_use` tokens, node size = always_on | Counts done (#5); node size from cost done on the canvas (#10 phase 1: area-proportional, p95 cRef, unknown hollow dashed); Inspector (cost rows, Overlaps grouped by verdict with reasons and clickable partners) and Legend (size scale, unknown, duplicate/wraps/overlaps keys) done in #10 phase 2, pending review; `--overlap` token added to index.css; late-font repaint fixed (wake on document.fonts.ready) | |
| D12 Chat agent build | prebuilt `create_react_agent`, maybe rebuilt as a `StateGraph` | **Deviation approved 2026-11-04:** fixed local `StateGraph` first (#11) | User chose free first; optional local synthesis later |
| D13 Graph UI | `react-force-graph-2d`, d3-force on canvas, tuned physics, glow, fallback d3-force + PixiJS | Done (#8) | `react-force-graph-2d`, glow nodes, hover fade, zoom labels |
| D14 Frontend | Vite + React + TS + Tailwind + shadcn/ui, served by FastAPI, static export | Done (#8) | rebuilt in the planned stack; first version was vanilla JS and was replaced |
| D15 Models | Haiku 5.5 for volume, Sonnet 5.5 verifier, via `langchain-anthropic` | **Deviation, approved by the user (2026-11-03)**: Anthropic SDK called directly | keep; switch only if a LangChain feature is needed |
| D16 Working mode | AI writes code, user stays in the loop, `/tdd` | Active | |

## Ideas added after the plan (2026-11-03)

Filed as tickets, all local-first and free by default (see the Cost rule in CLAUDE.md):

- #16 label cache, #17 offline mode, #18 ambiguity ranking plus trigger collisions
- #19 `constellation report` (terminal-first use; the `/constellation` plugin #12 wraps it)
- transcript usage ("never used" Items), session-start weight, and the whole scan as one LangGraph graph with a checkpointer (tickets below)

Not filed yet: reachability (which MCP servers a session can really reach), security hygiene (risky hooks), drift over time (comes with the checkpointer).

## Review notes (2026-11-04)

- #6 merged. Known judgement calls from the Opus review, not fixed: ~~the verdict cache key ignores the verifier model id~~ (fixed in #16: the model id is mixed into the key); `CANDIDATE_THRESHOLD = 0.5` assumes centred vectors, which only apply from 10 Items up; a `wrapper` verdict without a `wraps` field quietly treats A as the wrapper.
- Privacy decision made (user chose option 3): the #5 token counter sends only always-on text by default; skill bodies go to the counting endpoint only with `--count-bodies`. Recorded in CLAUDE.md "Privacy invariant".
- #8 design pass merged (Vite + React + TS + Tailwind + shadcn, react-force-graph-2d). D13 and D14 are no longer deviations. Rough edges for the Sonnet polish pass are listed in `docs/design/graph-app.md`.

## #16 label cache and #17 offline mode (2026-11-04, branch `ticket-16-17`)

- #16: `classify()` caches each label in `~/.cache/constellation/labels.json` (0600), keyed by the sha256 of the redacted prompt plus the model id; a re-scan labels only new or changed Items, and a changed prompt template invalidates old entries. The same model-id salt now keys the verdict cache (the #6 review finding). Token-count keys are unchanged (no salt), so existing caches stay valid.
- #17: `scan --offline`, or no `ANTHROPIC_API_KEY`, makes no provider calls (it used to exit 2). `scan(offline=True)` ignores any llm, counter and verifier, reads token costs from the cache only, and adds an "Offline: ..." warning, which is how the output JSON marks labels as absent (no schema change, the app already treats `labels` as optional). `--offline --count-bodies` exits 2. No new decision or deviation.
- Tests: `tests/conftest.py` now redirects all three default cache paths to a temp dir, so no test touches the real `~/.cache`.

## #19 terminal report (2026-11-04, branch `ticket-19-report`)

- `constellation report [FILE] [--top N] [--all] [--cleanup FILE [--force]]` prints a plain-text report of a saved scan from the JSON only (no network, key or cost). The logic is the pure `render_report(data, *, top, color, width, show_all)` in `report.py`, also reused by the `/constellation` plugin (#12); `render_cleanup` backs the markdown checklist.
- Sections: counts, top Items by always-on cost (unknown cost is never counted as 0), Overlaps by verdict, warnings. Suggestions (#7) are left out until that ticket lands. Descriptions, reasons and warnings go through `redact()` by pattern rules only (the scan file records no secrets).
- Tests: `tests/test_report.py` plus golden outputs under `tests/fixtures/`; `report.py` is in mutmut `only_mutate` with zero survivors.

## #21 session-start weight (2026-11-04, branch `worktree-agent-ab5aa8a9f3d2a3f9a`)

- `hooks.py` sizes SessionStart and UserPromptSubmit hooks statically, running nothing: literal `echo`/`printf` text, or a script file at an absolute path (or `${CLAUDE_PLUGIN_ROOT}`) that resolves inside the config dir (symlinks out are unknown). Anything with shell expansion, chaining, redirection, a relative or missing path, or an `mcp_tool` hook is `unknown`, never 0.
- Result: `Constellation.hook_weights` (Item id -> `Weight(bytes, tokens)`, additive). Bytes are always shown (free, local). Tokens only with `--count-bodies` (or already cached; offline reads the cache only), through the existing guarded counter and cache via `costs.count_texts`, so an unchanged setup makes zero calls and the planted secret never reaches the counter.
- Report: a "Session-start weight" section per hook plus a lower-bound total. Hook `Cost` stays unknown (hook node size is unchanged). Script size is a proxy for what a script injects, not its runtime output.
- Open: the Item inspector (#10) display is frontend work, not done here. `hooks.py` is in mutmut `only_mutate`, zero survivors.

## #7 Suggestions with approve/skip and resume (2026-11-04, branch `ticket-7-impl`)

- `constellation review [FILE] [--out cleanup.md] [--force]` runs after a scan, on the saved JSON only (no network, key or cost). `suggestions.py` turns duplicate and wrapper Overlaps into Suggestions (content-derived ids, largest known saving first, unknown savings never 0). `review.py` is the LangGraph graph: one `interrupt()` per undecided Suggestion, answers merged by a reducer, state saved by the official `SqliteSaver` (new dependency `langgraph-checkpoint-sqlite`, pinned `>=3.1,<3.1.3` so the release is over two weeks old).
- Resume: the plan's assumption held. A new process on the same SQLite file and thread sees the pause (`get_state`), and a fresh `invoke` replaces the stale pause while keeping `decisions`, so the fallback (resume the pending id via `get_state`) was not needed.
- Privacy: the checkpoint (0600, `~/.cache/constellation/review.sqlite`) holds only Suggestion ids and answers; a test plants a secret in a description and a reason and greps the DB bytes. The approved checklist reuses `render_cleanup(approved=...)` and the shared `write_private` writer (0600, no overwrite without `--force`).
- A test snapshots a copied config dir (bytes and mtimes) around `scan` and `review`: unchanged. `suggestions.py` is in mutmut `only_mutate`. Not done by design: applying a Suggestion, web endpoints (#10/#11), usage-based Suggestions (#20), scan as one graph (#22).

## #24 design system (2026-11-04, branch `worktree-agent-a663f86a43a7be524`)

- Status: implemented per `docs/design/DESIGN.md` steps 1-9 (Linear structure, Claude type voice). Fontsource packages Newsreader, Inter Variable and JetBrains Mono, pinned 5.3.0 (2026-07-19), replace the vendored Instrument Serif. shadcn tokens remapped, explicit radius scale, flat surface ladder, indigo accent. Stack unchanged.
- **Deviation from Linear (documented in DESIGN.md):** primary button hover/pressed is `#5560cc`, not `#828fff`, because white on `#828fff` is 2.87:1 (fails AA); `#5560cc` is 5.34:1. `#828fff` is used only as ring and accent text.
- `paint.ts`: only font loading changed (load canvas-only faces, clear the cluster-name width cache, extend the repaint window once fonts are ready). No colour literals changed.
- Metrics: first-load JS 77.87 kB gzip (unchanged); latin font files on first view about 116 KB (Inter 48, Newsreader 22+24, JetBrains Mono 21), under the 130 KB budget; fontsource also emits other unicode-range subsets, fetched only on demand.
- Not verified: inspector, warnings popover, empty/failed/loading and focus-state screenshots, offline reload, and `layout:check` with the real fonts (the script uses its own measurements, so cluster-name fit with Newsreader needs an eye check).

## Approvals and state, 2026-11-04 (user)

- **Deviation approved:** #25 adds `POST /api/checklist` (one row into a private 0600 checklist file under `~/.cache/constellation/`; never edits the user's setup; id-only input; localhost-only) and a localhost-address check on `GET /api/constellation` too. See `docs/plans/first-screen.md`.
- Approved earlier today: primary hover `#5560cc` (AA contrast), Newsreader as the serif.
- Merged to main: #24 (design system), #10 canvas half and panel half (needs closing comment after review).
- Plans written, not built: `docs/plans/first-screen.md` (#25), `docs/plans/usage.md` (#20; #13 must drop or coarsen usage dates in the public Snapshot).
- Order to finish: #25, #20 (Opus security review of the diff), #21 (in flight), #9, #11, then #12, #13, #23; defer #14, #15, #18, #22.

## #20 usage from transcripts (2026-11-04, branch `codex/ticket-20`)

- Implemented: local streaming `usage.py`, additive `usage` and `usage_window` fields, `scan --no-usage`, saved-JSON unused Suggestions and report/checklist sections. Usage runs before providers, including offline, and never feeds their inputs or caches.
- Fixture tests cover matching, deduplication, dates, size boundaries, malformed shapes, symlinks, provider isolation, unchanged paid caches, and planted secrets across JSON, report, checklist, review DB and recording providers. No real transcripts were read.
- Security review caught excluded `memory/` and `tool-results/` subtrees, recursive JSON, strict shape checks and positional model compatibility; these are fixed. **Deviation approved by the user (2026-11-04):** replace path-based traversal with pinned directory descriptors (`O_DIRECTORY | O_NOFOLLOW`, relative child opens and `scandir(fd)`) to close the reproduced ancestor-directory swap race. The plan is amended, with swap and descriptor-cleanup regression tests.
- #13 follow-up: public Snapshots must drop `usage` and `usage_window`, or coarsen dates. Frontend usage display remains a separate ticket.
- Agent instructions now require cost-aware model/effort selection and isolated worktree/branch ownership for parallel repo work. Installed five missing upstream Codex skills and documented sources, adaptations and gaps in `docs/agents/codex-skills.md`; browser runtime and the original dataviz package remain unverified.

- Final gates: `uv run --all-extras` Ruff check, format check, mypy and pytest passed (400 passed, 2 paid/eval tests deselected); mutation run passed (2,382 killed), and `mutmut results` printed nothing. Independent security re-review found no remaining actionable traversal issue after FIFO rejection and read-failure cleanup tests. Frontend lint, build and layout checks also passed. Real-setup plausibility, browser runtime and an external Opus review were not verified.
- Mutation review: the plan-required prefilter marker does not suppress invocation-token literal mutations (confirmed generated and killed). Removing the entire filter could broaden malformed-line diagnostics, so its speed-only equivalence claim applies only to invocation results, not warning totals. Other exemptions cover the prescribed digest length, an unused initial key, and redundant entry symlink flags after explicit rejection. Actual descriptor-open flags have no exemption.

- Follow-up using Matt Pocock’s code-review skill: parallel Standards and Spec reviews ran in isolated worktrees. Standards found no actionable issue; Spec found one P2: an entry metadata error ended traversal of healthy siblings. Fixed by catching errors per entry; public `scan()` regressions cover `is_symlink`, `is_file` and `is_dir` failures. No remaining actionable review findings. Matt Pocock’s TDD, implement and code-review skill installations and metadata were rechecked; no duplicate installation was needed.

## #25 first screen and useful cost visualization (2026-11-04)

- Implemented and reviewed on `codex/ticket-25`: server-ranked top costs and duplicate/wrapper pairs, graph selection/pair framing, private id-only checklist writes, `open --checklist`, localhost/origin guards and unknown-cost counters. Added `review_cost` without changing review generators; #20's unused Suggestions stay outside the pair list.
- The user requested a useful visualization: known cost rows now show static proportional bars alongside token counts, without new data, provider calls or client ranking. At 641–959px the Brief and inspector take turns on selection/reopening so they cannot cover both selected stars; the approved plan records this responsive clarification. Wide desktop retains both panels and phone retains its sheet.
- Parallel Standards and security/spec reviews found three P2 issues, all fixed and rechecked: checklist savings lost when rows fell outside the top five; metadata spoofing checklist IDs; and overlapping panels at narrow desktop widths. Checklist unknown rows are explicitly reported and recounted after a scan changes.
- Gates: Ruff check/format, mypy, 453 tests (2 paid/eval tests deselected), mutmut (2,541 killed; results empty), frontend lint/build/layout all passed. Demo-only browser checks include 1440px, 700px and 390px, add/error states, offline/unknown/static fallback, keyboard/pill, pair selection and resizing. Root verified compiled UI against the real local Python API using only copied demo data and a temporary private checklist; no page errors.
- Not verified: real scans, Safari/Firefox, real touch or screen readers, and an external Opus review. No paid calls or real setup reads were used.
- User authorized review/merge: #20 was fast-forwarded into local `main` at `aac28a4`; #25 was fast-forwarded into local `main` at `7a68f50`. Nothing was pushed to main and no issue was closed. #11's contract, #12's plugin preview and #13's Snapshot privacy foundation remain isolated on their ticket branches until their remaining decisions/integrations are resolved.

## #11 chat preparation (2026-11-04, branch `codex/ticket-11`)

- Proposed contract in `docs/plans/chat.md`; no implementation or provider calls yet. Retrieval and graph actions use known Item ids and public API tests with a fake model.
- Integrate after #25's server/UI changes; Expansion delegates to #9. Real-model chat needs an explicit privacy/cost decision about redacted questions and per-interaction calls, since the existing policy only permits Item metadata/short local signals and changed-Item costs.

## #11 historical model cost research (2026-11-04)

- Historical model research considered redacted questions and bounded relevant metadata. The #11 review restores the original AGENTS.md/CLAUDE.md privacy and cost rules without any chat exception; chat is fully local and free. Hardware baseline: M1 Mac, 16GB unified memory. No paid calls, model downloads or real setup reads were made.
- Research and arithmetic are in `docs/research/chat-models.md`: optional qwen3:4b/Ollama local trial, existing Haiku 5.5 hosted option, and no extra hosted SDK merely for marginal savings. Current official rates imply about $0.275/1000 answers at 1500 input +250 total output tokens; this is an illustrative estimate, not actual spend or a dollar cap.
- Historical research proposed synthesis budgets and provider-adapter tests. The current `docs/plans/chat.md` supersedes that proposal with deterministic zero-call operations and a local memory cache only; usage remains local-only, preserving #20.
- Historical D12 proposal considered one synthesis call. The implemented D12 amendment uses a fixed local graph with no synthesis or provider adapter; generation remains unapproved future work.

## #11 free-first decision and SQLite baseline (2026-11-04)

- User chose free-first chat and optional fully local generation later, targeting machines with at least 16GB unified memory. Hosted model execution is unapproved and deferred; chat is fully local and free, with no generation adapter or automatic model installation.
- D12 staging amendment: implement a fixed local routing/retrieval/answer/action workflow first rather than an initial multi-call model agent. Optional local synthesis remains future work requiring a separately reviewed contract under the original privacy/cost rules. The implemented stage follows the user's explicit free-first direction.
- Selected stdlib SQLite FTS5/BM25 for the first metadata retrieval baseline with in-memory indexing/caching, guarded HTTP input and known-id graph actions. The runtime's FTS5 smoke query passed on invented metadata. `sqlite-vec` is a candidate only after measured semantic retrieval gains justify local embeddings/extension loading; see `docs/research/sqlite-retrieval.md`.
- Implementation is now starting on isolated backend/UI worktrees; current docs do not claim #11 complete. No runtime model, embedding download, real setup scan or paid call was used for this decision.

## #11 free local answers (2026-11-04, branch `codex/ticket-11`)

- Implemented the approved free-first phase: explicit `POST /api/chat`, bounded validated input, redacted metadata retrieval with in-memory SQLite FTS5/BM25, fixed LangGraph routing/retrieval/answers and known-id graph actions. Costs, counts, known duplicate/wrapper pairs, usage and Item explanations use saved local data. Unsupported semantic matches and cost totals are explained honestly.
- Models remain off, with no provider adapter, credential read, model download or automatic hosted fallback. LangSmith tracing is explicitly disabled. Short responses use a bounded 128-entry memory cache; no questions, retrieval index or conversations are persisted. Usage remains local-only.
- UI starts collapsed, sends only on explicit submission, retains selected context and highlights/focuses matching Items (the review removes `filter` from the action contract). Chat and Brief alternate on the left; narrow screens retain the inspector coexistence rule. Automatic map refits update zoom bounds while manual camera positioning survives panel toggles.
- Backend/UI implementation and privacy review ran in isolated worktrees. Regression checks cover query framing, unrelated selection, scoped on-use costs, redaction before shortening, FTS syntax, cache invalidation/concurrency and disabled telemetry. Final review also caught misleading global copy after an empty scoped result and remote/static question submission before API availability detection; both were fixed and independently rechecked before the commit.
- 16GB is the supported design baseline. Optional small local generation and semantic embeddings/`sqlite-vec` are deferred; actual M1 memory/latency/quality are unmeasured. #9 Expansion and the remaining #13 static export are separate work.

- Mutation audit: SQLite statement exclusions cover equivalent lower/upper-case variants; malformed-statement variants were observed killed before the exclusions. No generated mutation isolates SQL ranking/column/LIMIT semantics, so HTTP relevance/boundary tests supply that coverage. An early tracing-toggle mutant bypassed the recording client and attempted a failed LangSmith upload of invented fixture metadata; the fixture now intercepts the fallback factory and blocks real client initialization/HTTP transport. No real setup/transcript data or paid model call was involved. The final mutation run uses the corrected isolation.

- Final combined gates: Ruff check and format check, mypy (20 source files), pytest (510 passed, 2 eval tests deselected), all 3,256 mutants killed with `mutmut results` empty, and frontend lint/build/layout passed. The first broad mutation run had two suspicious pre-existing brief/usage results; forcing those individually killed both, with no source/test exemptions added for them.
- Demo-only integrated browser verification used the compiled UI with the real local Python API: grounded cost answers, selected Item explanations at 700px, graph actions, explicit-submit request counting (zero on open/type, one on submit), 390px/desktop layouts and no page errors. The remote/static guard separately proved zero serialization and zero requests; localhost/127.0.0.1 and older-local-API fallback were checked. Independent final security review confirmed both findings resolved.
- Not verified: optional local-model memory/latency/quality on an actual M1, semantic retrieval accuracy, real scans, Safari/Firefox, physical touch or screen readers. No model adapter or download was added, nothing was pushed, and no issue was closed.

## Inspector usage and session-start weight (2026-11-04, branch `worktree-agent-a1538319abfe9e181`)

- Frontend only. `model.ts` gets optional `usage`, `usage_window`, `hook_weights` types; `Inspector.tsx` gets a Usage panel: "N uses, last D" or "Never seen in the N transcripts scanned" (count 0, from the window), "not tracked" for kinds with no usage entry (hooks, plugins; different from 0), and for prompt-time hooks a Session-start weight row (bytes; tokens or "tokens not counted"; "unknown" when bytes unknown, never 0).
- Unused-by-cost list in the Brief: **skipped by design**. `first-screen.md` keeps `remove_unused` out of the Brief pair list and the Brief API (`brief()`) carries no unused rows; adding one needs a server and plan change (a follow-up ticket), not a client-side ranking.
- Demo: `docs/design/make-demo.mjs` adds invented `usage`, `usage_window`, `hook_weights` to `demo-250.json` from a third seeded stream (existing names, Relations and Overlaps unchanged).
- #13 reminder: public Snapshots must still drop `usage`/`usage_window` (the inspector shows nothing for them when absent).
- Not verified: real scans, Safari/Firefox, screen readers.

## #26 usage reader trustworthiness (2026-11-04, branch `worktree-agent-a5b2432b72409ecbc`)

- Real-scan evidence from the user (counts only): 122 malformed lines, 1 skipped file, 86 files over 2026-11-01..2026-11-04, 23 Items with usage, 171 never seen.
- 1. Records with no top-level `message`, or whose `type` is not `user`/`assistant`, give no matches and are not counted malformed; only prefiltered lines can count as malformed.
- 2. Ambiguity is decided per name lookup: two clear slash commands in one message no longer warn; an ambiguous name beside a clear one still does.
- 3. The skipped-files warning splits the reason: `N files (B too big, U unreadable)`, counts only. The report note gives the day span and skipped count and says Claude Code deletes old transcripts, so 'never seen' is not proof of non-use; the `remove_unused` reason (shown by `review`) carries the same caveat. No `cli.py` change was needed.
- 4. The config dir is resolved once before pinning, so a symlinked config dir is read; a symlinked `projects/` is still refused.
- 5. Window dates come from each record's top-level `timestamp` only (every line is parsed for it); undated windows print no `None to None`.
- Gates: Ruff check/format, mypy, 459 tests (2 paid/eval deselected), mutmut 2,573 killed, results empty. No paid calls; no real transcripts read.
- Not verified: the real record shapes. After merge the user reruns a real scan to confirm the malformed count drops to zero or near it.

## #23 taste review (2026-11-04, branch `worktree-agent-a9082504e2a9f29e3`)

- Done: inspector (`--app`) and look-and-fix loop at 1440 and 390 on demo data only; before/after in `docs/design/screenshots/23-*`. Fixes: unlit star names hidden while something is lit (`paint.ts`), atlas marks on empty and failed states, nowrap code pill. No deviations; no new dependencies or assets. Findings that conflict with DESIGN.md or the star-atlas direction, and ideas not built, are recorded in `docs/design/graph-app.md`.
- Gates: lint, build, `layout:check` (thresholds unchanged) and pytest (453 passed) pass.

## Coordination and integration order (2026-11-04, user approved)

- Codex and Claude take separate tickets/branches; distinct subtasks within one ticket use separate branches/worktrees and explicit ownership. Reserve Astra for critical or unusually complex debugging.
- Stabilize repository metadata, integrate #11 and #12 while retaining the newer Inspector/usage/taste/phone-default changes, implement #9, finish #13, then prepare #14. #29 stays with Claude. #15 is deferred.
- Cloud eviction affected Git objects, refs and worktree metadata. A separate recovery clone combines remote objects with checksum-verified resident local objects. Protected main/Claude29/#9/#11/#12/#13 histories are complete; a historical layout-plan docs tree was reconstructed to its exact original hash. Source edits and active indexes are preserved. Remaining unrecoverable placeholders require explicit reporting, not guessed branch targets.
- #11 integration retains the first-visit phone Brief collapse from main alongside the collapsed Chat panel; documentation retains both agents' ticket histories. Combined integration gates passed: Ruff check/format, mypy, 517 tests (2 eval deselected), 3,288 mutants killed with results empty, frontend lint/build/layout. Two suspicious existing cluster/cost results were killed on isolated rerun. Demo browser verification retained the first-visit phone collapse, local usage coverage, selected explanations and Inspector usage display without page errors.

- Repository recovery retained all 33 readable branch tips and 28 resident indexes byte-for-byte. Seven old unreadable branch-tip placeholders and four historical object placeholders remain unresolved and are preserved outside Git discovery paths; this is not a claim of complete historical recovery. Active protected histories are complete in a separate local recovery clone.

## #11 review handoff (2026-11-04, latest user workflow)

- Work moved to `~/dev/constellation-wt/codex-11` in the fresh clone. The merge of main through `3b0be88` completed before the user switched to push-only handoff; no later merges are made. Newer usage-residual changes on origin/main remain for Claude to integrate and review.
- AGENTS.md now records Astra for critical/complex debugging, separate branches for distinct subtasks, the fresh checkout/worktree paths, and ticket-branch-only push followed by stop/report. Claude owns reviews, merging, frontend work and hosting; #29 is untouched and #15 remains deferred.
- Free local answers are implemented. Model chat is still off: no hosted/local inference adapter or paid chat call was added. Optional local generation, real M1 model benchmarks, semantic retrieval quality, Safari/Firefox, real touch and screen readers remain unverified.
- Data/process disclosure: no real setup/transcript read or configured user MCP server was started. Demo-only local FastAPI/browser processes and isolated plugin validation ran during development. One early tracing-toggle mutant attempted a failed LangSmith upload of invented metadata; corrected tests intercept the fallback client and block real tracing transport. Public model/SQLite documentation was researched; no model inference or model download occurred.
- Fresh-clone npm ci, frontend lint/build/layout passed. npm reported 16 existing audit advisories (2 low, 14 moderate); dependency remediation is outside this Python handoff and remains for Claude.

- Final fresh-clone handoff gates: Ruff check/format, mypy, pytest 517 passed (2 eval deselected), full mutation gate 3,288 killed with results empty, and npm ci/lint/build/layout all passed. Two suspicious existing Suggestion mutants were killed on single-worker rerun with no code/test exclusions added. Only the ticket branch is pushed; no merge or issue closure follows this handoff.

## #11 review fixes (2026-11-04, branch `codex/ticket-11`)

- Restored the original main privacy invariant and cost rule in AGENTS.md/CLAUDE.md and removed the chat exception. Preserved unrelated model-selection and isolated-worktree rules. Chat remains fully local and free.
- Replaced the single intent-switch answer node with real LangGraph conditional edges to search, explain, focus, top-cost, count, Overlap and usage operations. HTTP tests preserve grounded answers, scope and known-id graph actions.
- **Review correction authorized by the user:** removed `filter` from the API/frontend action contract instead of adding canvas hiding behavior. Filter-worded requests highlight matching Items; the UI no longer claims filtering. The plan records this minimal choice.
- Added a pre-JSON Content-Length guard for chat requests above 16,384 bytes and exact boundary/malformed-JSON HTTP regressions. Chat's open section has an id; only the open collapse control references it. A public-component render check verifies open/collapsed ARIA references without starting an HTTP server.
- Red evidence: oversized HTTP tests failed with 200/422 before the guard, the filter contract regression returned `filter`, `Focus this` returned highlight instead of focus, and the rendered collapsed component failed on a missing `chat-title` controlled region. No new mutation exclusions were added. Equivalent empty-action argument mutants were removed by omitting redundant empty arguments to the response helper.
- Final gates: `uv run --all-extras` Ruff check/format, mypy, pytest (520 passed, 2 paid/eval tests deselected), and mutmut run (3,345 killed; `mutmut results` empty) passed. Frontend lint/build/layout and `chat:check` passed. The graph refactor required clearing stale generated mutation test mappings before the full run; no coverage or code exclusions were added.
- Not verified: optional model memory/latency/quality, real scans, screen readers, physical touch or a fresh browser interaction pass; public-component rendering checks the ARIA fix. No provider data was sent, real setup or credential file read, or configured user server started. The renderer uses Vite without HTTP or WebSocket listeners; earlier test iterations may have opened its transient HMR listener, closed in `finally`. No background process remains. Nothing was merged, rebased, pushed or closed in this review-fix handoff.
