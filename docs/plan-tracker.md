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
| D6 Interface | chat on the left, graph on the right, served by FastAPI | Partly (#8 graph); chat open (#11) | |
| D7 CLI | **Typer** `scan, expand, open, export --public` | **Deviation, approved by the user (2026-11-03)**: `argparse` with `scan` and `open` | keep; revisit only if the CLI outgrows it |
| D8 Chat | tool-calling agent driving the graph | Open (#11) | |
| D10 Public demo | sanitised static Snapshot on Vercel | Open (#13, #14, #15) | |
| D11 Context cost | `always_on` and `on_use` tokens, node size = always_on | Counts done (#5); node size from cost done on the canvas (#10 phase 1: area-proportional, p95 cRef, unknown hollow dashed); Inspector (cost rows, Overlaps grouped by verdict with reasons and clickable partners) and Legend (size scale, unknown, duplicate/wraps/overlaps keys) done in #10 phase 2, pending review; `--overlap` token added to index.css; late-font repaint fixed (wake on document.fonts.ready) | |
| D12 Chat agent build | prebuilt `create_react_agent`, maybe rebuilt as a `StateGraph` | Open (#11) | |
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

- Final gates: `uv run --all-extras` Ruff check, format check, mypy and pytest passed (397 passed, 2 paid/eval tests deselected); mutation run passed (2,382 killed), and `mutmut results` printed nothing. Independent security re-review found no remaining actionable traversal issue after FIFO rejection and read-failure cleanup tests. Real-setup plausibility, frontend gates, browser runtime and an external Opus review were not verified.
- Mutation review: the plan-required prefilter marker does not suppress invocation-token literal mutations (confirmed generated and killed). Removing the entire filter could broaden malformed-line diagnostics, so its speed-only equivalence claim applies only to invocation results, not warning totals. Other exemptions cover the prescribed digest length, an unused initial key, and redundant entry symlink flags after explicit rejection. Actual descriptor-open flags have no exemption.
