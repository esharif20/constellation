# Per-project usage, move-to-project Suggestions, global vs repo view (#43, #44, #59)

Source: `docs/plans/explore-ux.md` sections F (T13, T14) and G. Owner decisions (2026-11-04): project names are local-only
(never to a provider, never in a warning, dropped from the Snapshot); the usage reader keeps only ids, counts and dates and reads
transcript text for nothing else; agents and tests never read real transcripts or a real `~/.claude`.
Order note: #34 (connectors, also `usage.py`) is still open. Whichever of #34 and ticket A lands first, the other rebases.

## 1. Data model (contract commit, made first by the orchestrator, ~20 lines, no logic)

- `Item.scope: str = "global"`. `"project"` for Items read from `--project PATH` and for `local/<n>/` MCP servers.
- `Item.project: str | None = None`. The opaque key of the project an Item lives in, when known (only `--project` Items in v1).
- `Constellation.projects: dict[str, str]`: opaque key `p1..pN` -> display label. Local only.
- `Constellation.usage_by_project: dict[str, dict[str, Usage]]`: Item id -> key -> `Usage(count, last_used)`. Same `Usage` type,
  so it can only hold counts and digit dates. Kept apart from `usage`, so nothing that reads `usage` today (chat, report) sees keys.
- `Constellation.current_project: str | None`: the key of `--project PATH`, else None.
- `scan(..., project: Path | None = None)` passes `project` to `read_items` and `read_usage` (both accept and ignore it in the
  contract commit). `read_usage` returns a 4th value `ProjectUsage(projects, by_project, current)`, empty in the contract commit.
- Suggestion gains `project: str | None = None` (key, never a label) and `confidence: str | None = None` (`"high"`/`"medium"`).

## 2. Project identity (ticket A)

- The key source is the depth-1 folder name under `<config>/projects/`. Claude Code names it after the session's working dir with
  every non-alphanumeric character turned into `-` (assumed; tests use invented names, a mismatch only costs a label).
- `_walk` also yields the depth-1 folder name; it stays in memory inside `read_usage`. Keys `p1..pN` follow sorted folder order
  (ordinals, never a hash: a short path hash is guessable). Folders with no tracked invocation still get a key only if they are
  the current project; others are left out.
- Label (**[approve] deviation**): plan G says "last segment of the decoded folder name", which breaks hyphenated names
  (`plan-43-44` -> `44`). Proposed: if the folder equals `encode(--project PATH)`, label = `PATH.name`; else the folder name with
  the encoded home prefix (`encode(Path.home())`) and leading `-` removed, e.g. `dev-constellation`. Then `redact()`, cap 60
  chars, and `-` fallback to `project N`. Never the username. If the owner says no, use plan G's rule unchanged.
- Counting: wherever `read_usage` credits `usage[id_]`, it also credits `by_project[id_][key]` with the same day. Dedup (`seen`)
  stays global. The pinned-descriptor walk, caps, symlink refusal and warnings are unchanged; warnings stay counts-only.

## 3. Repo scan (ticket B, #59)

- `read_items(config_dir, lockfile, project)`: when given, `_read_root(PATH/.claude, "project/", ...)` (skills, agents, commands,
  hooks in `.claude/settings.json`), plus `PATH/.mcp.json` with scope `project/`. Ids `claude-code:<kind>:project/<name>`, no path.
  Mark those Items `scope="project"`, `project=current key`. `local/<n>/` MCP servers get `scope="project"`, `project=None`.
- `read_secrets` adds `PATH/.claude/settings.json` env and `PATH/.mcp.json` env values, so project secrets are redacted too.
- Warnings from the project root show `<project>/...`, never the absolute or `~` path. Also fix the existing leak in
  `claude_code.py` line 217 (`({path})` prints the raw path; use `_shown`).
- The non-empty scope means `_inside` already refuses symlinks that leave the project root.
- `cli.py`: `scan --project PATH` (must be a directory; else exit 2 with a fixed message).

## 4. Move-to-project Suggestions (ticket C, #44). Deterministic, local, free.

Inputs from the scan JSON only: `usage_by_project`, `usage`, `usage_window`, `costs`, `items`, `relations`.
- Eligible: `scope == "global"`, not disabled, kind `skill`/`agent`/`mcp_server`, not inside a plugin. A plugin is judged as one
  Item: sum its contents' per-project counts; the move is "enable it only in that project's settings".
- `total` = sum over projects; `top` = the project with most uses (ties: no Suggestion).
- Rule: `total >= 3` and `top / total >= 0.8` -> `move_to_project`, `project = top`. Boundaries: 4/5 yes, 3/4 no, 2/2 no, 3/3 yes.
- Used in 3 or more projects, or below the rule: no Suggestion. 0 uses: the existing `remove_unused` stays as is.
- Skip when the same kind and name already exists with `scope="project"` in `top` (it is a copy, not a move).
- Confidence: high = window span >= 14 days and `total >= 5`; medium = everything else that passes the rule. Low (specificity
  anchors, plan G 3) and the paid `--scope-verdicts` Haiku verdict are **not built**; the paid part needs separate approval.
- `tokens_saved` = the Item's always-on cost (saved in sessions outside that project); unknown stays None. Id from kind + Item id.
- Reason text has **no label**: "Used 9 times over 12 days, 8 of them in one project. Move it into that project's .claude/
  folder." So report, checklist file and any future provider path cannot carry a name. `brief.py` adds a "Scope" group and, for
  the local app only, a `project_label` field looked up from `data["projects"]`. `report.py` prints "one project" (terminal output
  may be pasted or, as a plugin, enters Claude's context). The window caveat ("based on N days; Claude Code deletes older ones")
  goes on the group.

## 5. UI and Ask hooks (ticket D)

- `model.ts`: read `scope`, `project`, `projects`, `usage_by_project`, `current_project` (all optional).
- Scope filter in the top bar: All / Global / This repo (This repo only when `current_project` is set). It dims out-of-scope stars
  like the existing focus dim; no new layout. Inspector: per-project rows "9 in dev-constellation, 1 in another" (labels local).
- Brief: the Scope group with confidence as a word, never a percentage bar.
- Ask (chat.py/answer.py belong to the Ask tickets, not touched here): the scope filter hands Ask the in-scope Item ids the same
  way a selection does. Handoff rule for Ask: never put `projects`, `usage_by_project`, `Item.project` or labels in any provider
  payload; "global vs this repo" questions answer from `Item.scope` locally.
- Demo data: `make-demo.mjs` adds invented projects (`alpha-shop`, `thesis`), appended after the other streams.

## 6. Plugin vs standalone

- Standalone (`constellation scan [--project PATH]`, `open`): usage is on, so per-project counts, labels and move Suggestions
  appear in the local app. Without `--project` there is no "This repo" view; per-project usage still works.
- Plugin (`/constellation:constellation`): SKILL.md stays `--offline --no-usage`; add `--project` with the session's working dir
  as one more quoted literal argument. Result: global vs repo split in the report and app, no transcript data, no labels, no move
  Suggestions. Turning usage on in plugin mode would put counts into Claude's context and needs owner approval first.

## 7. Privacy analysis and what the Opus review must check

What is new on disk: labels and per-project counts in the scan JSON (already written 0600). What can reveal a folder name:
the label (approved, local only). What must hold:
1. A planted folder name and its label never appear in warnings, report text, the cleanup checklist, Suggestion reasons, any
   recorded provider input (llm, embedder, verifier, counter), any cache file, or `snapshot(data)` output.
2. `snapshot()` needs no change (it allowlists Item fields and top-level keys), but a test proves `scope`, `project`, `projects`,
   `usage_by_project`, `current_project` are absent.
3. Transcripts: still only ids, counts and top-level dates leave `_parse`; the folder name is the only new value, used for the key.
4. `--project` path: never in an Item id, name, description or warning; project secrets are in `read_secrets`.
5. Labels never read project files; a key is an ordinal, not a hash of a path.
6. Chat: `clean` still builds Items from id/name/kind/description only; `usage` holds no keys.

## 8. Tests (invented data only, through `scan()`, `cli.main`, `render_report` and the HTTP API; HOME is a tmp dir)

- A: tmp config with `projects/` for 3 invented folders (`-tmp-home-dev-alpha`, `...-beta`, `...-gamma-x`), 4 Items: single-project,
  spread over 3, unused, ambiguous (two Items one name). Assert keys, labels (hyphenated name kept), counts, last dates,
  `current_project` for a matching `--project`. Privacy: planted folder `-tmp-home-zzsecretclient`, check point 7.1.
- B: tmp repo with `.claude/skills/x`, `.claude/agents/y`, `.mcp.json` with an env secret, a skill with bad frontmatter and a
  symlink out; assert ids, scope, redacted secret, `<project>` in warnings and no tmp path anywhere in the JSON.
- C: pure dict fixtures for each boundary (4/5, 3/4, 2/2, 3/3, ties, 3 projects), tiers at 13 vs 14 days and 4 vs 5 uses,
  plugin aggregation, already-in-project skip, label absent from every reason, report and checklist.
- D: `npm run lint && build && layout:check`, screenshots of the filter and Scope group on demo data.
- All gates incl. mutmut with zero survivors (boundary tests above are what kill the threshold mutants).

## 9. Tickets (each its own worktree and branch from the contract commit)

| Ticket | Owns | Size | Model / review |
|---|---|---|---|
| 0 contract | `models.py`, `__init__.py` signature, `suggestions.py` dataclass fields only | XS | orchestrator, first |
| A per-project usage (#43) | `usage.py`, `__init__.py` wiring, `tests/test_usage_projects.py` | M | Sonnet; Opus privacy review |
| B repo scan (#59) | `claude_code.py`, `cli.py`, `plugin/constellation/skills/`, `tests/test_scan_project.py` | M | Sonnet; Opus review |
| C move Suggestions (#44) | `suggestions.py`, `brief.py`, `report.py`, `tests/test_suggestions_move.py` | M | Sonnet; Opus review |
| D UI | `frontend/src/**`, `docs/design/make-demo.mjs` and demos | M | Claude UI skills set, screenshots |

A, B, C and D run in parallel; each adds its section to `docs/plan-tracker.md` (append only, to avoid conflicts). Merge order:
0, A, B, C, D. Nobody touches `chat.py` or `answer.py`.
