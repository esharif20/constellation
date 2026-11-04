# Usage reader: residual warnings on a real setup (follow-up to `usage.md`)

Diagnosed 2026-11-04 with a counts-only script (fixed labels and integers; no transcript text, names or paths left the
machine or entered any agent context).

## Findings

Real `projects/`: 147 `.jsonl` (two more than the earlier count, live sessions): 8 main transcripts at depth 1, 83 under
`<session>/subagents/`, 56 directly inside a `<session>/` folder, 1 symlink. The reader took 90 (8 + 83 − 1 symlink).

1. **Malformed lines are valid JSON, not corruption.** 0 JSON decode or Unicode errors, 0 truncated last lines, 0 BOM,
   0 NUL, 0 oversize. Every "malformed" line is a well-formed record the shape check rejects:
   - 20 `assistant` `tool_use` blocks named `Agent`/`Task` **without `input.subagent_type`**. That field is optional
     (omitted means the built-in general-purpose agent), so these are valid calls. This class is the reported 18
     (sessions grew since). The built-in agent is not an Item, so no Item usage is lost.
   - 114 records with no `message` dict (`attachment` 50, `system` 3, other types 61) that pass the byte prefilter
     because `"tool_use"` appears somewhere nested. The committed `usage.py` counts these too and reports
     **136 malformed** on this machine. The 18 the user saw came from a different working copy (its wording,
     "(0 too big, 1 unreadable)", is not in this branch). Treat that copy's changes as unknown and rebase this fix onto it.
   - Hidden usage: these rejected records contain 0 nested tracked (`Skill`/`Agent`/`Task`/`mcp__`) tool_use dicts
     besides the 20 above, and 0 tracked blocks sat next to a bad block in the same record. Nothing is undercounted
     today. A latent bug remains, though: `_matches` raises on the first bad block and drops the record's valid siblings.
2. **The skipped file is the symlink.** It sits in a `subagents/` folder, is more than a day old (not the live session),
   and points inside `projects/` at a regular file the reader already reads. Skipping it loses nothing. Following it
   would only double-read, and dedup by tool_use id would cancel that out. Decision: keep never following symlinks
   (no "inside projects/" exception; it adds a resolve-and-compare path for zero gain). Fix only the wording.
3. **The 56 unread files are the `<session>/*.jsonl` files at depth 2.** They contain 0 tracked tool_use blocks, so
   subagent usage is not undercounted (subagents are read from `subagents/`). No change to the depths.
4. Other things seen, all outside this fix: the `.venv` fails to import `langgraph` (`LangGraphDeprecatedSinceV10`;
   run `uv sync`), and the repo has broken branch refs plus broken worktree metadata (`git worktree prune` after a check).

## Fix spec (test-first through `scan()`, invented fixtures only)

Edit `src/constellation/usage.py` `_matches` / `read_usage` and `tests/test_usage.py`.

- F1 A record that is not a dict with a `message` dict, a `str` `type` and list content (user str content still
  becomes a text block) is **not an invocation record**: skip it silently. It is not malformed.
- F2 Validate per block. A bad block (non-dict, non-str `type`, tool_use with a non-str name/id or non-dict input,
  user text with a non-str text/uuid) adds 1 to malformed for that line (at most 1 per line), and the line's other
  valid blocks are still credited.
- F3 `Agent`/`Task` with `subagent_type` missing: valid, credits nothing, not malformed. A present but non-str
  `subagent_type`, or `Skill` with a non-str `skill`, is still a bad block.
- F4 Split `skipped` by cause: `too_big` (fstat size over FILE_CAP), `symlinks` (an `entry.is_symlink()` hit or an
  `O_NOFOLLOW` ELOOP), `unreadable` (any other OSError). `UsageWindow.skipped` stays the total. Warning:
  `usage: skipped {m} malformed lines, {o} oversize line, {k} files ({a} too big, {b} symlinks, {c} unreadable)`.

Tests (red first):
- T-R1 `attachment` record with a nested `{"type":"tool_use","name":"Skill",...}` and no `message`: count 0, no warning.
- T-R2 one assistant message: an `Agent` block without `subagent_type` plus a `Skill` block for a fixture skill.
  The skill counts 1, no warning.
- T-R3 the same message with a non-dict block in place of the Agent block: the skill counts 1, warning says 1 malformed.
- T-R4 the three causes, one fixture each (a symlinked subagent file pointing at a sibling transcript, `chmod 000`
  skipped as root, FILE_CAP monkeypatched to the file size minus 1): the exact warning strings, and window `skipped` equals 3.
- Update the existing warning-string asserts in `tests/test_usage.py` (lines 141, 176, 337, 391, 394, 436, 546),
  and recheck the malformed counts in T8 against F1/F3 (some of those lines become silent).
- Mutation gate: boundaries on the per-line malformed cap, and on each skip cause going to the right counter.

Update `docs/plans/usage.md` §T8/T12 and `docs/plan-tracker.md` (no deviation: wording and shape tolerance only).
