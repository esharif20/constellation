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
| D5 Suggestions | `interrupt()` per suggestion, approve or skip, writes `cleanup.md` | Open (#7) | never modifies user config |
| D6 Interface | chat on the left, graph on the right, served by FastAPI | Partly (#8 graph); chat open (#11) | |
| D7 CLI | **Typer** `scan, expand, open, export --public` | **Deviation, approved by the user (2026-11-03)**: `argparse` with `scan` and `open` | keep; revisit only if the CLI outgrows it |
| D8 Chat | tool-calling agent driving the graph | Open (#11) | |
| D10 Public demo | sanitised static Snapshot on Vercel | Open (#13, #14, #15) | |
| D11 Context cost | `always_on` and `on_use` tokens, node size = always_on | Counts done (#5); node size from cost open (#10) | |
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
