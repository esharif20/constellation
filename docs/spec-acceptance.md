# Spec acceptance: issue #1 against main (2026-11-06)

Status: DONE (evidence named), PARTIAL, MISSING. "Test" means a file under `tests/`. Frontend feel has no unit tests by design
(checked by eye; screenshots in `docs/design/screenshots/`). Evidence was found by reading names and running the commands
below, not by re-running every test; the gates were run on this branch.

## User stories

| # | Story | Status | Evidence |
|---|---|---|---|
| 1 | One command scans | DONE | bare `constellation scan` (`test_cli.py`, `test_scan.py`) |
| 2 | Every Item kind a node | DONE | `claude_code.py`, `test_mcp_sources.py`, `test_scan.py` |
| 3 | Relations (contains, triggers, duplicates, wraps) | DONE | `test_scan.py`, `test_overlap_wrappers.py` |
| 4 | Clusters by purpose | DONE | `cluster.py`, `grouping.py`, `test_cluster.py`, `tests/eval/test_cluster_quality.py` |
| 5 | Node size = always-on cost | DONE | frontend `graph/`, tracker D11 (by eye) |
| 6 | Always-on and on-use cost | DONE | `test_costs.py`; on-use needs `--count-bodies`, else unknown (documented privacy exception) |
| 7 | Exact token counts | DONE | `anthropic_llm.py` `count_tokens`; free endpoint, needs a key (offline shows cached or unknown) |
| 8 | Cached counts | DONE | `test_costs.py::test_a_second_scan_of_an_unchanged_setup_makes_no_counting_calls` |
| 9 | Runtime hooks "unknown" | DONE | `test_costs.py::test_hook_costs_are_unknown_not_guessed` |
| 10 | Exact duplicates | DONE | `overlaps.exact_duplicates`, `test_overlap_*` |
| 11 | Wrappers not duplicates | DONE | `overlaps.wrappers`, `test_overlap_wrappers.py` |
| 12 | Overlap with plain-English reason | DONE | `overlaps.py`, `test_cli_overlaps.py` |
| 13 | Four verdicts only | DONE | `overlaps.VERDICTS`, `_parse` |
| 14 | Reason shown | DONE | `overlaps.py` MAX_REASON; inspector (frontend) |
| 15 | Measured on hand-labelled pairs | DONE (this pass) | 20 pairs in `tests/eval/overlap_pairs.py`; local band scored and recorded in README "How good is it". Real-verifier score still NOT recorded (needs a key, about $0.20; owner to run) |
| 16 | Nothing deleted or edited | DONE | AGENTS.md rule; `test_export_public.py` never writes inside `.claude`; `clean` only writes a checklist |
| 17 | Suggestions one at a time, approve/skip | DONE | `review.py`, `test_review.py`, `test_cli_review.py` |
| 18 | Approved written to checklist | DONE | `cleanup.py`, `test_cleanup*.py` |
| 19 | Paused scan resumes | DONE | `review.py` `interrupt` + SqliteSaver; `test_scan_resume.py`, `test_review.py` |
| 20 | Secrets never sent | DONE | `test_canary.py`, `test_redaction.py`, `test_env.py` |
| 21 | Secret shapes redacted before any call | DONE | `redact.py` `guarded*`, `test_redaction.py` |
| 22 | Open a node, fetch detail | DONE (CLI, API, inspector) | `expansion.py`, `test_expansion.py`; live real-server run still pending (tracker D2) |
| 23 | MCP tools listed on expand | DONE | `test_expansion.py::test_expansion_lists_sorted_tools_through_cli_and_http` |
| 24 | Unreachable shown, scan not failed | DONE | `test_expansion.py::test_unreachable_is_successful_result_and_no_partial_tools` |
| 25 | Hosted connectors single nodes | DONE | `usage.connector_items`, `test_usage_connectors.py`, `test_no_launch_for_connectors...` (connectors are derived from transcript use, so a never-used connector is not seen: known limit) |
| 26 | Drag with spring | DONE (by eye) | `frontend/src/graph/`, tracker D13 |
| 27 | Hover highlights neighbours | DONE (by eye) | same |
| 28 | Labels fade with zoom | DONE (by eye) | same |
| 29 | Click glides, shows summary/cost/Relations | DONE (by eye) | `Inspector.tsx`, `StarMap.tsx` |
| 30 | Dark glowing style | DONE (by eye) | `docs/design/DESIGN.md`; screenshots |
| 31 | Chat panel beside graph | DONE | `Chat.tsx`, `chat.py`, `test_chat*.py` |
| 32 | "Everything that touches email" highlights | DONE | `test_chat_answers.py`, `test_search.py` |
| 33 | Chat works by searching Items | DONE | `retrieve.py`, `test_search.py` |
| 34 | Explain any Item | DONE | `explain.py`, `test_explain.py` |
| 35 | Context-cost report from chat | DONE | `test_chat_answers.py` (cost), `answer.py` |
| 36 | Chat focuses/filters the graph | DONE | graph actions in `chat.py`, `test_chat.py` |
| 37 | CLI mirrors the actions | DONE | `cli.py`; spec list was scan, expand, open, export, now far wider (`test_cli_contract.py`) |
| 38 | One command opens graph and chat | DONE | `constellation open` (`test_server*.py`) |
| 39 | `/constellation` command in Claude Code | DONE (this pass) | `plugin/constellation` passes `claude plugin validate` (only warning: no icon). Spelling is `/constellation:constellation` (namespaced, approved earlier). SKILL.md was stale (required a config dir, wrote `constellation.json`, used `report`); now runs default `scan --offline --no-usage`, `status`, `open`. Live Claude session not run |
| 40 | Sanitised read-only Snapshot export | DONE | `public_export.py`, `snapshot.py`, `test_export_public.py`, `test_snapshot.py`. Free text is NOT anonymised (documented) |
| 41 | Snapshot checked for secrets | DONE | `test_snapshot.py`, `test_export_public.py`, `test_canary.py` |
| 42 | Recruiter link to interactive demo | MISSING | #14 open; nothing deployed. Static build exists, `constellation open demo` works locally |
| 43 | Scroll-driven landing page | MISSING | #15 open (blocked on #14); scroll-craft not used yet |
| 44 | New harness = new adapter only | DONE | ADR 0001, `claude_code.py` is the only harness-shaped module |
| 45 | Fan-out, verifier loop, approval pause in LangGraph | DONE | `scan_graph.py` (`Send` fan-out for labels and verifier, conditional edges, checkpointer), `review.py` (`interrupt`) |
| 46 | Each module explained as built | N/A | process rule, not a code criterion |

## Implementation decisions that drifted (all recorded in `docs/plan-tracker.md`)

- Chat in the Snapshot: spec and #13 say canned chat responses; the static site instead has no chat (search falls back to the local index, write/chat actions unavailable, `test_static_snapshot_api_guard_never_sends_search_questions_or_writes`). PARTIAL against #13.
- Expansions pre-run in the Snapshot: not found in `public_export.py`. PARTIAL/MISSING against #13.
- Chat agent: fixed local `StateGraph`, no model (D12 deviation). Models: Anthropic SDK directly (D15). CLI: argparse (D7).
- Spec said a "later iteration" for hand-built chat graph with grounding check: out of scope, not built.
- Commands in the spec (scan, expand, open, export) are a subset: `export --public` exists as `share` and `export`.

## Stale docs found and fixed in this pass

- `plugin/constellation/skills/constellation/SKILL.md` and the README "Claude Code plugin" section (explicit config dir, old default file).
- README had no accuracy section: added "How good is it".
- `constellation-cli` is the correct PyPI package name; the command is `constellation`; install lines in README and `install.sh` are consistent (package not yet on PyPI).

## Sub-issues

Can be closed (all criteria DONE, reviews merged): #2 to #8, #10, #11, #12 (already closed), #16 to #26, #29, #31 to #33. Already closed in GitHub.

Open and status:
- #9 Expansion: criteria 1, 2, 4 DONE (`test_expansion.py`); 3 DONE (`test_no_launch_for_connectors...`). Only a live real-server check is outstanding (tracker). Closable once the owner runs `constellation expand` against one real local MCP server.
- #13 Snapshot: loads without backend and no secrets DONE; canned chat and pre-run Expansions MISSING. Not closable.
- #14, #15, #27, #28: not started. #30, #45, #80: separate feature tickets, not part of spec acceptance.

## Larger gaps for the owner

1. Run the real Overlap verifier eval once (about $0.20) and put precision/recall in the README table.
2. Decide: canned chat and pre-run Expansions in the Snapshot (#13), or amend the spec to drop them.
3. Deploy the Snapshot (#14), then the landing page (#15). Nothing public exists yet.
4. Plugin: add an icon (validator warning) and try `/constellation:constellation` in a live session.
5. Issue #1 body still says the three-command interface and "Typer"-era wording; update it to the current command map.
