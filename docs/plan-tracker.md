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

- Final gates: `uv run --all-extras` Ruff check, format check, mypy and pytest passed (400 passed, 2 paid/eval tests deselected); mutation run passed (2,382 killed), and `mutmut results` printed nothing. Independent security re-review found no remaining actionable traversal issue after FIFO rejection and read-failure cleanup tests. Frontend lint, build and layout checks also passed. Real-setup plausibility, browser runtime and an external Opus review were not verified.
- Mutation review: the plan-required prefilter marker does not suppress invocation-token literal mutations (confirmed generated and killed). Removing the entire filter could broaden malformed-line diagnostics, so its speed-only equivalence claim applies only to invocation results, not warning totals. Other exemptions cover the prescribed digest length, an unused initial key, and redundant entry symlink flags after explicit rejection. Actual descriptor-open flags have no exemption.

- Follow-up using Matt Pocock’s code-review skill: parallel Standards and Spec reviews ran in isolated worktrees. Standards found no actionable issue; Spec found one P2: an entry metadata error ended traversal of healthy siblings. Fixed by catching errors per entry; public `scan()` regressions cover `is_symlink`, `is_file` and `is_dir` failures. No remaining actionable review findings. Matt Pocock’s TDD, implement and code-review skill installations and metadata were rechecked; no duplicate installation was needed.

## #25 first screen and useful cost visualization (2026-11-04)

- Implemented and reviewed on `codex/ticket-25`: server-ranked top costs and duplicate/wrapper pairs, graph selection/pair framing, private id-only checklist writes, `open --checklist`, localhost/origin guards and unknown-cost counters. Added `review_cost` without changing review generators; #20's unused Suggestions stay outside the pair list.
- The user requested a useful visualization: known cost rows now show static proportional bars alongside token counts, without new data, provider calls or client ranking. At 641–959px the Brief and inspector take turns on selection/reopening so they cannot cover both selected stars; the approved plan records this responsive clarification. Wide desktop retains both panels and phone retains its sheet.
- Parallel Standards and security/spec reviews found three P2 issues, all fixed and rechecked: checklist savings lost when rows fell outside the top five; metadata spoofing checklist IDs; and overlapping panels at narrow desktop widths. Checklist unknown rows are explicitly reported and recounted after a scan changes.
- Gates: Ruff check/format, mypy, 453 tests (2 paid/eval tests deselected), mutmut (2,541 killed; results empty), frontend lint/build/layout all passed. Demo-only browser checks include 1440px, 700px and 390px, add/error states, offline/unknown/static fallback, keyboard/pill, pair selection and resizing. Root verified compiled UI against the real local Python API using only copied demo data and a temporary private checklist; no page errors.
- Not verified: real scans, Safari/Firefox, real touch or screen readers, and an external Opus review. No paid calls or real setup reads were used.
- User authorized review/merge: #20 was fast-forwarded into local `main` at `aac28a4`; #25 is ready for the same local merge. Nothing was pushed to main and no issue was closed. #11's contract, #12's plugin preview and #13's Snapshot privacy foundation remain isolated on their ticket branches until their remaining decisions/integrations are resolved.

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

## Usage reader residuals (2026-11-04, branch `claude/usage-residuals`, spec `docs/plans/usage-residuals.md`)

- Real-scan evidence (counts only, from the spec): the leftover "malformed" lines were valid JSON the shape check rejected, and the one skipped file is a symlink in a `subagents/` folder pointing at a file already read.
- R1 (non-message records stay silent) was already done in #26; kept, with a test for a nested `tool_use` in an `attachment`.
- R2: each content block is validated on its own; a bad block adds at most 1 malformed per line and the line's valid blocks are still credited.
- R3: `Agent`/`Task` with no `subagent_type` is valid and credits nothing; a present non-string value (or a `Skill` with a non-string `skill`) is still a bad block.
- R4: the skipped-files warning is `N files (B too big, S symlinks skipped on purpose, U unreadable)`. Symlinks are still never followed (no inside-`projects/` exception). Window `skipped` stays the total.
- No deviation from the plan. Gates: ruff check/format, mypy, pytest all green; mutmut zero survivors (one unrelated timing "suspicious" in brief.py cleared on rerun).
- Not verified: a real scan; the user reruns one to confirm the malformed count falls to near zero.

## #23 taste review (2026-11-04, branch `worktree-agent-a9082504e2a9f29e3`)

- Done: inspector (`--app`) and look-and-fix loop at 1440 and 390 on demo data only; before/after in `docs/design/screenshots/23-*`. Fixes: unlit star names hidden while something is lit (`paint.ts`), atlas marks on empty and failed states, nowrap code pill. No deviations; no new dependencies or assets. Findings that conflict with DESIGN.md or the star-atlas direction, and ideas not built, are recorded in `docs/design/graph-app.md`.
- Gates: lint, build, `layout:check` (thresholds unchanged) and pytest (453 passed) pass.

## #29 checklist hardening (2026-11-04, branch `claude/ticket-29`)

- Checklist adds now append one whole line with `O_APPEND` (no truncate, so a hand edit is never lost); a re-add chmods the file to 0600; the cache directory is created 0700; the path guard rejects any `.claude` folder, not only `~/.claude`.
- Plan behaviour kept (no code change): a duplicate whose cost is unknown has `removes=null`, saves nothing countable, and its row says "unknown".

## #36 halo follows the cluster (2026-11-04, branch `claude/ticket-36`, plan `docs/plans/explore-ux.md` section H, T6)

- `layout.ts` gains pure `haloOf(c)`: centre = home + (live member mean - rest mean), radius = `c.r` widened by how much the farthest member's reach grew past its rest reach, capped at 1.4 `c.r`. `layout()` records the rest mean and rest reach (`mx`, `my`, `fr`) per cluster, so at rest the halo is exactly `(c.x, c.y, c.r)`. `paint.ts` eases a per-cluster halo toward it with `FEEL.labelMs` and uses it for the glow and the cluster-name placement. No new dependency.
- Small deviation from the plan's formula (no approval needed, same behaviour): the plan's `farthest + r + GAP` already exceeds `c.r` at rest, so the radius is measured relative to the rest reach to keep the at-rest picture unchanged.
- `layout:check` adds `haloBad` (rest equals home; one member moved by d shifts the centre by d / n; radius within [r, 1.4 r]); all existing thresholds untouched and passing.
- Gates: lint, build, layout:check, pytest (469 passed). Dragging a hub on `demo-250.json` checked by eye with agent-browser: halo and name move with the members.
- Not verified: a before/after pair on the old build (the stashed rerun did not drag), touch drag, phone width.

## #35 warnings: ~ paths, grouping, Offline as a mode (2026-11-04, branch `claude/ticket-35`)

- Done, per `docs/plans/explore-ux.md` section B: `_shown(path)` in `claude_code.py` writes home paths as `~/...` in the frontmatter and skip warnings (a test pins that the scan holds no home folder). `groupWarnings` in `model.ts` groups by stable message prefix into actionable, degraded and info groups; the top bar button says "N to look at" (actionable + degraded only), info groups sit collapsed, up to 5 items with "and N more" and a copy-path button (`~` form). "Offline" is a mode: `Model.offlineNote` is the tooltip on "offline scan" and it never counts as a warning.
- Contract test `tests/test_warning_contract.py` pins the prefixes (emitted by `scan()` for the file-based ones, literal-in-source for provider/usage ones) and that `model.ts` still names each one. `layout:check` asserts `groupWarnings` on invented strings.
- Public Snapshot untouched (it already drops warnings). Warnings from other modules that quote an OS error with an absolute path (cache save failures) are not rewritten: not in the plan's source list. No deviations.
- Not verified: other themes/real long path lists; screenshots only on demo data with injected warnings at 1440 and 390.

## Search stopgap: forgiving client search (2026-11-04, branch `claude/search-stopgap`)

- STOPGAP, superseded by #40/#41 (the real natural-language search, `docs/plans/explore-ux.md` section C). Frontend only: `frontend/src/graph/search.ts` is a pure ranker (normalise, drop filler words only when something else remains, joined-token match so "pony tail" ~ "ponytail" ~ "pony-tail", edit distance 1 for tokens of 5+ characters, subsequence as the weakest tier; also reads description, kind and label). `model.ts` `search()` now delegates to it; `TopBar.tsx` shows a "Matched: ..." line under each result and a not-found hint. cmdk filtering was already off. No backend, no provider calls, no deviations.
- `layout:check` asserts the ranking on invented Items (ponytail spellings, typo, frontend design, nonsense -> empty).
- Not done (left to #40/#41): did-you-mean list, clusters group, semantic matching. Not verified: real scans; keyboard behaviour was unchanged by construction, not re-driven.

## #32 + #33 missing Items: MCP servers, commands, install paths, disabled plugins (2026-11-04, branch `claude/ticket-32`)

- Done (`docs/plans/explore-ux.md` section A, items 1-4, 5 partly, 6, 7 partly): MCP servers are read shape-only (`stdio: <basename of first word>` or `remote <type>: scheme://host`) from `~/.claude.json` (user scope id `user/<name>`; project/local scope id `local/<hash of path>/<name>`, the path never kept), config-dir `.mcp.json`, plugin `.mcp.json` (with or without the `mcpServers` wrapper) and `plugin.json` `mcpServers` (inline, file inside the plugin, or `.mcpb`/`.dxt` bundle = "bundle: shape unknown"). env, headers, args and url userinfo/port/path/query are never read into an Item. `~/.claude.json` is parsed in memory, only `mcpServers` taken; an unreadable file gives a fixed-text warning with no parser message. The url => connector rule is gone: url servers are `mcp_server`.
- `~/.claude.json` location: `<config>/.claude.json` if present (the `CLAUDE_CONFIG_DIR` case, where Claude Code keeps it inside the dir), else beside the config when the dir is named `.claude` (warns if missing there); any other dir never looks in its parent.
- New Item kind `command` (`commands/*.md`, user and plugin; description from frontmatter else first non-empty line). Plugins whose `installPath` is outside `plugins/cache` are found. `Item.disabled` (default false) is set on a plugin switched off in user `settings.json` `enabledPlugins`, and on everything it contains. Frontend: `command` kind (starlight, triangle glyph, legend entry), disabled stars dimmed with a hollow ring, legend note when any exist.
- `usage.py`: scopes `user/` and `local/` are the user's own, so `mcp__<name>__*` calls credit them (a test pins it).
- Not done, by design of this ticket: `plugin.json` extra `skills`/`agents`/`commands` paths (item 5 tail), connector Items from transcripts (item 7, in `usage.py`), project `.mcp.json` (G), project/local `enabledPlugins`. A disabled plugin's always-on cost is still counted in totals. Inspector does not yet say "disabled".
- No deviation from the plan. Both tickets landed on one branch in two commits because they share `claude_code.py`; commit 1 holds the Python for both.

### #32/#33 security review fixes (2026-11-04, branch `claude/ticket-32`)

- **DEVIATION (approved by the user, 2026-11-04): local-scope servers.** Plan section A item 8 says project `.mcp.json` and local scope wait for `scan --project PATH` (G). This branch reads `projects[*].mcpServers` from `~/.claude.json` now (shape only). Switch: `LOCAL_SCOPE` in `claude_code.py`; set it to `False` to drop them. Local ids are `local/<n>/<name>`, n a per-scan index over sorted project paths (no path-derived value).
- Stdio shape skips leading `NAME=value` words and never prints a word containing `=` (else `stdio: unknown`); a URL scheme is printed only if http, https, ws or wss (else `unknown`).
- Command bodies are no longer kept, so `--count-bodies` sends only skill and agent bodies, as on main. Command descriptions are capped at 200 chars, then redacted.
- A non-UTF-8 command file and a malformed `installed_plugins.json` entry give fixed-text warnings and the scan continues. A symlink inside a plugin that resolves outside it is refused (warning), for skills, agents and commands.
- `usage.py` decides plugin scope from the plugin's `contains` relations (a plugin named `user` is not user scope). `.claude.json` is read before the config root, and plugin `mcpServers` before the plugin's hooks, so hooks link to those servers (a user hook tries `user/<server>` too).
- Not fixed: a plugin named `user`, `local` or `synced` still shares an id prefix with that scope (ids can collide; first wins).

## #38 cluster focus (2026-11-04, branch `claude/ticket-38`, spec `docs/design/cluster-focus.md`, plan `docs/plans/explore-ux.md` D and H, T8 + the card half of T9)

- Done per the note's 10-step checklist: one camera owner (`fly`/`stopCamera` in `StarMap.tsx`, a custom rAF flight on d3 `interpolateZoom.rho(1.2)` with `easeCubicInOut`, 700 to 1300 ms by distance, 0 under reduced motion), pure `fitView`/`focusView` in `layout.ts`, flight path in `flight.ts`, `clusterSummary`/`rankMembers`/`slug` in `model.ts`, focus dimming and member names with cost lines in `paint.ts`, `ClusterCard.tsx`, breadcrumb and "N clusters" popover in `TopBar.tsx`, `backTo` on the Inspector, history (`#cluster=<slug>` push, hop replace, popstate, deep link) and the left-slot rule in `Atlas.tsx`.
- Decisions recorded (all approved by the user before the build): (1) custom d3 `interpolateZoom` flight, not force-graph's `zoom`/`centerAt` tweens; `glideTo` (search, Inspector rows, Brief pairs) now goes through the same `fly`. (2) CSS transitions for the card and sheets, no new `motion` dependency. (3) The card is in this ticket and lists the **top 3** costly members (plan D said 5; the user asked for 3). Plus the two extras from the note: leaving focus by zooming out below 0.5 x the focus zoom (state change only, no flight), and the "N clusters" list in the top bar.
- Dependencies: `d3-interpolate@3.0.2` and `d3-ease@3.0.2` (both already in the lock through d3-zoom, now explicit and pinned) and `@types/d3-interpolate@3.0.4`, `@types/d3-ease@3.0.2` (a month old). `d3-interpolate` is imported only by `flight.ts`, used from `StarMap`, so it loads with the Atlas chunk and not with first paint (importing it from `layout.ts` put +16 kB in the first-load chunk). `@types/d3-interpolate` does not declare `interpolateZoom.rho`; `flight.ts` casts it (exists at runtime).
- Bundle (npm run build): first-load `index` 244.18 -> 245.85 kB (gzip 79.10 -> 79.75); `Atlas` 318.53 -> 335.99 kB (gzip 108.69 -> 113.75); `Inspector` 7.46 -> 7.73 kB. CSS unchanged in size class.
- `layout:check`: new columns `focusK`, `focusOutside`, `focusSmall`, `focusCapped`, `focusPan`, `flightBad`, `flightMax`, `focusNamed`, `focusNamedMin`, `focusClash`; all pass on the three demos at 1440x900 and 390x844 (member-name share 90% / 45% on demo-250, floors 60 / 40); no existing threshold changed; `fitView` reproduces the old fit (same named counts, e.g. 14/19 on the phone). `clusterSummary` has an assert-based self-check.
- Small deviations from the note (no approval needed): focus label placement also refuses a name that would sit on another star (the metric already assumed it); the hit test treats a name as clickable at `zoomAlpha * la >= 0.25` (0.4 context alpha times a crowded 0.7 would otherwise never be clickable); the note's `FEEL.flightRho/flightMin/flightMax` live in `FLIGHT` in `flight.ts` (so the metrics script can import them without a DOM).
- Fixes found on the way: `linkPointerAreaPaint` is a no-op (a Relation line under a cluster name swallowed the click that enters it: force-graph only calls `onBackgroundClick` when no node or link is under the pointer); the `wake()` loop zeroed its handle on unmount (under React StrictMode in dev the loop never restarted, so fades froze); the 460 ms refit no longer fires while focused or flying.
- Frame time (dev-only `performance.mark` `cx-pre`..`cx-frame`, headless Chrome 1440x900, `demo-250.json`, one enter flight): median 1.1 ms, p95 2.4 ms, max 5.8 ms over 89 frames (budget 8 ms).
- Not verified: a real trackpad or touch pinch and drag, Safari and Firefox, screen readers on the live region and heading focus, a real (non-demo) scan, the flight feel on a 120 Hz display; the 700 and 390 px views were checked with demo data only.
