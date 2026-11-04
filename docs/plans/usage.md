# Plan: usage from transcripts (#20)

Goal: each skill, agent and MCP server Item gets a usage count and a last-used date, or "never seen", from the user's own
Claude Code session transcripts. Everything here is local and free. No transcript text leaves the reader, and none of it
is held in memory beyond the line being parsed.

Decisions that touch this ticket: Cost rule (zero paid calls; local work first), Privacy invariant (only kinds, names and
descriptions go to a provider), D5 Suggestions (#7 generator hook in `suggestions.py`), #19 report (`render_report` is
pure and works on the saved JSON), D11 (always-on cost is the ranking key). No deviation from the plan is needed. One open
point for #13: a public Snapshot must drop `usage` and `usage_window` (see "Later tickets").

## 1. Where transcripts live (observed layout, names only)

`<config_dir>/projects/<encoded-cwd>/<session-uuid>.jsonl`, plus subagent transcripts at
`<config_dir>/projects/<encoded-cwd>/<session-uuid>/subagents/*.jsonl`. Siblings that are NOT read: `tool-results/`,
`memory/`, anything else. On the author's machine: 132 files, median about 0.5 MB, largest about 20 MB, and one symlink
inside `projects/`. Claude Code deletes old sessions (`cleanupPeriodDays`, default 30), which is why the window note in §4
is required.

Only these two glob depths are read. Nothing else under `config_dir`, and nothing outside it.

## 2. Record shape and what counts as an invocation

The shape below is believed, not documented: the claude-code-guide agent confirmed it from memory, and only the
`mcp__<server>__<tool>` naming is documented. The implementer must not open real transcripts to check. The check happens
once at the end: the user runs `constellation scan` on the real setup and confirms by eye that the counts look plausible.

Every line is one JSON object with `type`, an ISO-8601 UTC `timestamp` (for example `2026-11-04T12:34:56.789Z`) and
`message.content`, which is a list of blocks. Four signals count:

| Signal | Where it appears | Credits |
|---|---|---|
| Skill tool | assistant block `{"type":"tool_use","name":"Skill","input":{"skill": S}}` | skill |
| Slash command | user content (string or text block) containing `<command-name>/S</command-name>` | skill |
| Subagent | assistant `tool_use` with `name` in `{"Agent","Task"}`, `input.subagent_type: S` | agent |
| MCP tool | assistant `tool_use` with `name` starting `mcp__` | mcp_server / connector |

Matching `S` (a skill or agent) to Item ids. Build the index once from `items`, never from transcripts:
- An Item with scope `""` is keyed by `name`. A synced skill (`synced/...`) is also keyed by its bare `name`.
- A plugin Item (id `claude-code:<kind>:<plugin>/<name>`) is keyed by `"<plugin>:<name>"`. It is also keyed by bare
  `name`, but only when no local Item of that kind has that name, because a bare name resolves to the local Item first.
- A key that maps to more than one id credits all of them, and the reader adds one warning:
  `"usage: N invocation names matched more than one Item; each was credited"`. The warning holds a count, not the names.

Matching MCP tool names: `mcp__<server>__<tool>`, and for plugin servers `mcp__plugin_<plugin>_<server>__<tool>`. Claude
Code replaces non-`[A-Za-z0-9_-]` characters with `_` in these segments. Each `mcp_server` or `connector` Item gets the
prefix `mcp__{norm(name)}__`, or for a plugin `mcp__plugin_{norm(plugin)}_{norm(name)}__`. The longest matching prefix
wins. The tool part is never stored: no `mcp_tool` Items exist until #9, so the server gets the credit. claude.ai
connectors (`mcp__claude_ai_*`) match nothing on disk and are dropped silently.

Not tracked: hooks (they fire on their own, transcripts do not record runs, and they add no always-on cost), plugins (the
report derives "used" from the `contains` relations if needed; skipped for now), commands (not Items yet). These kinds get
no `usage` key, which is different from count 0.

Dedup: a resumed or forked session can copy earlier lines into a new file, and one assistant message can span several
lines. Each `tool_use.id` is counted once. In memory the reader keeps only `blake2b(id, digest_size=8)` digests, never the
ids, and the set is dropped when `read_usage` returns. A slash command has no tool id, so it is deduped by the record
`uuid`, hashed the same way.

## 3. Module and interface

New `src/constellation/usage.py`, pure apart from reading files. It does not touch `overlaps.py`.

```python
@dataclass(frozen=True)          # in models.py
class Usage:
    count: int
    last_used: str | None        # "YYYY-MM-DD" (UTC); None iff count == 0

@dataclass(frozen=True)          # in models.py
class UsageWindow:
    files: int                   # transcript files actually read
    first: str | None            # earliest "YYYY-MM-DD" seen on any line; None if no files
    last: str | None
    skipped: int                 # files skipped: too big, unreadable, symlink

def read_usage(config_dir: Path, items: list[Item]) -> tuple[dict[str, Usage], UsageWindow, list[str]]
```

The signature differs from the brief's two-tuple on purpose. The window is structured data that #7 and #19 render, so it
should not be squeezed into a warning string. Output keys are always Item ids from `items`, and every tracked Item is
present (count 0 when never seen).

### Streaming parse (the privacy-critical loop)

```
for path in _transcripts(projects):                       # §5 scope guards
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)       # ELOOP -> skipped += 1
    if os.fstat(fd).st_size > FILE_CAP: skip              # FILE_CAP = 256 MiB
    with os.fdopen(fd, "rb") as f:
        while line := f.readline(LINE_CAP + 1):           # LINE_CAP = 8 MiB
            if len(line) > LINE_CAP and not line.endswith(b"\n"):
                _drain(f); oversize += 1; continue        # discard the rest of the line in chunks
            day = _DAY.search(line)                       # rb'"timestamp":\s*"(\d{4}-\d{2}-\d{2})T'
            ... widen window from day ...
            if b'"tool_use"' not in line and b"<command-name>" not in line:
                continue                                  # most lines are never JSON-parsed
            try: record = json.loads(line)
            except ValueError: malformed += 1; continue
            for item_id, key in _invocations(record, index): ...   # yields only ids from the index
```

Rules for the implementer:
- `_invocations` is a generator over one record that yields `(item_id, dedup_digest)`. Every `.get()` is type-checked
  (dict, list or str). On any wrong shape the record is skipped and `malformed` goes up by one. It never raises.
- The last-used date comes from the record's `timestamp`, taken as `[:10]` and checked with `date.fromisoformat`. A bad
  date means the invocation is counted but the date is not used.
- At the end the reader adds at most one aggregate warning per class, holding counts only:
  `"usage: skipped 3 malformed lines, 1 oversize line, 2 files (too big or unreadable)"`. A warning never contains a path
  below `projects/`, because the encoded-cwd directory name holds the user's project paths. The reader says "a transcript
  file", or gives just the count.
- `OSError` on open or read means skipped += 1, and the reader moves on.
- Values that leave the function: ints, `YYYY-MM-DD` strings built from regex digits, and Item ids from `items`. That
  bounded alphabet is the privacy proof, and test T15 asserts it structurally.

## 4. Model, JSON schema and wiring

- `models.Constellation` gets `usage: dict[str, Usage] = field(default_factory=dict)` and
  `usage_window: UsageWindow | None = None`. `asdict` serialises both, giving
  `"usage": {"claude-code:skill:tdd": {"count": 4, "last_used": "2026-11-02"}}` and
  `"usage_window": {"files": 132, "first": "2026-10-05", "last": "2026-11-04", "skipped": 0}`.
- `scan(..., usage: bool = True)`: after `read_items`, call `read_usage(config_dir, items)` when `usage` is true. It runs
  in offline mode too (it is local). It runs before any provider call and is never passed to `classify`, `verify`,
  `measure` or any guarded callable.
- CLI: `scan --no-usage` skips it. That is one argparse line, so a user who does not want transcripts touched can opt
  out. `config_dir` stays a required positional, and nothing defaults from `CLAUDE_CONFIG_DIR` or `HOME`.
- Frontend: `model.ts` gets optional `usage?` and `usage_window?` types later, in a frontend ticket. The app ignores
  unknown keys today, so nothing breaks. Out of scope here, because another agent owns `frontend/`.

## 5. Scope guards

- `projects = Path(config_dir) / "projects"`. If it is missing, return an empty window with `files=0` and no warning (a
  fresh install). If it is a symlink, skip it with a warning: `"usage: projects folder is a symlink; not read"`.
- `_transcripts` uses `os.scandir`. It descends only into entries where `is_dir(follow_symlinks=False)` is true. It
  takes `*.jsonl` entries where `is_file(follow_symlinks=False)` is true, and only at the two depths in §1. Sorted, so
  the result is the same every run.
- `O_NOFOLLOW` on open is the second guard against a symlink swapped in after scandir.
- The reader never reads the environment: `usage.py` imports neither `os.environ` nor `Path.home`, and test T13 traps
  both.
- No writes anywhere. No cache: re-reading is cheap, and a cache would be a second copy of usage on disk.

## 6. Suggestions (#7) and report (#19)

Both read only the saved JSON, so neither makes a network call, needs a key or costs anything. Usage never feeds a
prompt, so the content-hash caches and the "unchanged setup means zero paid calls" property are unaffected.

- `suggestions.py`: a new generator `_unused` in `GENERATORS`, and `Suggestion.kind` gains `"remove_unused"`. It
  produces one Suggestion per Item where `usage[id].count == 0`, but only when `usage_window.files > 0`. `tokens_saved`
  is the known always-on cost, or None when unknown (never 0). The reason reads: `"{name} was never seen in {files}
  transcripts ({first} to {last}). It costs {T} always-on tokens every session."`, with the cost part left out when
  unknown. The id is derived from kind plus Item id, as now. The existing sort already ranks it: known savings largest
  first, then unknown. An Item that is unused and also in a duplicate pair gets both Suggestions. They are separate
  decisions.
- `report.py`: a new section "Never used (in the transcripts scanned)" after the cost section. It lists the top N by
  always-on cost, then unknown cost, with lines in the form `name (kind)  T tokens`. The header note reads:
  `"Covers {files} transcript files from {first} to {last}. Sessions Claude Code has already deleted are not counted, so
  'never seen' only covers these."` With no `usage_window` the section says `"Usage was not read in this scan."`. With
  `files == 0` it says `"No transcripts found."`. `render_cleanup` gets a "## Never used" block. Both go through
  `redact()` as the other sections do. The golden outputs in `tests/fixtures/` are updated.

## 7. Tests (`tests/test_usage.py`, plus additions to `test_suggestions.py`, `test_report.py`, `test_cli.py`)

Fixtures are invented JSONL, written by a `write_transcript(dir, records)` helper under `tmp_path`. No real transcript is
ever read: a new autouse fixture in `conftest.py` wraps `usage.read_usage` and fails if the resolved `config_dir` is under
the real `Path.home() / ".claude"`.

- T1 A Skill `tool_use` gives count 2, and `last_used` is the later of two dates.
- T2 A slash command `<command-name>/tdd</command-name>` is counted, in both string and text-block content.
- T3 `"p:name"` credits the plugin-scoped id. A bare name credits the local Item when one exists, and the unique plugin
  Item when none does. An ambiguous name credits both and adds one count-only warning.
- T4 Subagents are matched through both `Agent` and `Task`.
- T5 MCP: a local server, a plugin server (`mcp__plugin_p_s__t`), a name with `-` or `.` normalised, the longest prefix
  winning, and `mcp__claude_ai_*` dropped.
- T6 A never-seen Item gets `Usage(0, None)`. Hooks and plugins have no key.
- T7 Window: `files`, `first` and `last` across main and `subagents/` files. A missing `projects/` gives files 0 and no
  warning. Files under `tool-results/` and `memory/` are ignored.
- T8 Malformed input: bad JSON, a non-dict line, non-list content, a non-dict input, a non-str skill, a bad timestamp
  and an empty file. No crash, one aggregate warning holding only counts.
- T9 A line of `LINE_CAP + 1` bytes is skipped and the next line is still counted. A line of exactly `LINE_CAP` bytes is
  parsed (boundary, for mutmut). Use `monkeypatch` to make `LINE_CAP` small.
- T10 A file over `FILE_CAP` (monkeypatched) is skipped and `skipped` is incremented. A file of exactly `FILE_CAP` is read.
- T11 An unreadable file (`chmod 000`, skipped when run as root) gives a warning and the other files are still read.
- T12 Symlinks: a symlinked `.jsonl` file, a symlinked project dir and a symlinked `projects/` all point at transcripts
  with invocations outside `tmp_path/config`. Each gives count 0 and is counted in `skipped` or warned about.
- T13 Scope: invocations planted in `config_dir.parent / "projects"`, in `$HOME/.claude/projects` (with `HOME` patched to
  a tmp dir) and in `$CLAUDE_CONFIG_DIR` are not counted. `os.environ` is patched to a mapping that raises on any access,
  and `Path.home` is patched to raise, both during the `read_usage` call.
- T14 Dedup: the same `tool_use.id` in two files counts once. Distinct ids count separately.
- T15 **Planted secret, end to end.** The fixture transcript holds a secret `sk-ant-PLANTED...` and a unique marker
  (`ZZQ-MARKER-7f3a`) in user text, in a tool_use `input` beside `skill`, in an unmatched `mcp__` tool name, in a
  `toolu_` id, in a `cwd` field, after the timestamp, and in the encoded-cwd directory name. The test runs the CLI `scan`
  with the recording fakes (`_record_*`, `tests/fakes.py`) for the llm, embedder, counter and verifier, then
  `report`, `review` (checkpoint DB bytes) and `--cleanup`. Assert that neither marker nor secret appears in: the output
  JSON bytes, any warning, report stdout, `cleanup.md`, the checkpoint DB, or any text a fake received. It also asserts
  the structure: every `usage` key is in the `read_items` ids, every value is `{"count": int, "last_used": None |
  r"\d{4}-\d{2}-\d{2}"}`, and the window fields are ints, None or dates.
- T16 Provider isolation: with usage present, the texts sent to the fakes are identical to a `usage=False` scan of the
  same config dir. This proves usage never reaches a prompt.
- T17 `scan --no-usage` and `scan(usage=False)`: no `usage` key data, `usage_window` is None, and `read_usage` is never
  called (spy).
- T18 Suggestions: `_unused` orders by cost, then unknown last. It yields nothing when `files == 0` or the window is
  absent, nothing for used Items or hooks, and gives a stable id across re-scans.
- T19 Report and cleanup goldens: the never-used section, the window note, "not read" and "No transcripts found".
- T20 A re-scan of an unchanged setup with usage on still makes zero paid calls (extend the existing cache test).

**mutmut:** add `src/constellation/usage.py` to `only_mutate`. The gate is zero survivors. The tests that kill the
mutants:
- The cap boundary tests (T9, T10) kill `>` vs `>=` and the cap constants. Patch the module constants; do not use real
  256 MiB files.
- The prefilter literals are killed by T1 and T2. If the prefilter itself is mutated away, only speed changes, which is
  equivalent behaviour. Mark that line `# pragma: no mutate (prefilter only; json path decides)` and name it in the
  review.
- `digest_size=8` mutants are equivalent. Mark them with a reason.
- Mutating `O_NOFOLLOW` away is killed only if scandir lets a symlink through. scandir already filters symlinks, so the
  flag is defence in depth. Mark it `# pragma: no mutate (defence in depth behind scandir filter)` and keep the race-free
  guard anyway.
- Every other `# pragma: no mutate` needs a one-line reason, and the reviewer checks each one.

## 8. Opus review checklist (security-sensitive diff)

1. No transcript-derived string reaches a return value, warning, log, exception message or file. Check every
   `append`, f-string and `raise` in `usage.py`. Only ints, regex-digit dates and Item ids from the index leave.
2. A raw line or record lives only inside one loop iteration. Look for a list, dict or closure that captures one, and for
   a debugging `print`. `json.loads` errors are caught without echoing the line (`str(e)` of a `JSONDecodeError` holds
   only a position, but check it is not used).
3. No path below `projects/` appears in any warning (encoded-cwd leaks project paths).
4. Scope: `projects` is the only root. scandir uses `follow_symlinks=False` at every level, the open uses `O_NOFOLLOW`,
   and there is no `os.environ`, `Path.home`, `expanduser` or `glob("**")`.
5. Caps are enforced before any buffering, `readline(limit)` is used, the drain discards in chunks, and nothing calls
   `read()` on the whole file.
6. `read_usage` is never wrapped by, or passed into, `guarded*`, `classify`, `verify` or `measure`, and usage is absent
   from every prompt template (T16).
7. The planted-secret test (T15) covers all sinks: JSON, report, cleanup, the review DB, and the fakes. The marker sits in
   every field, the file name and the dir name.
8. Suggestions and the report follow the "unknown cost is never 0" rule. "Never seen" is shown only with its window note.
9. The `pragma: no mutate` lines each have a valid reason. mutmut reports zero survivors.
10. Tracker diff: `docs/plan-tracker.md` gets a #20 section (new `usage` and `usage_window` fields, `--no-usage`, the
    #13 follow-up) and no undeclared stack change.

## Later tickets (not here)

- #13 Snapshot: drop `usage` and `usage_window`, or coarsen them, because activity dates are personal. Add this to #13's
  brief.
- #9: once `mcp_tool` Items exist, credit the tool as well as its server (the tool part of the name is already parsed
  and discarded).
- Frontend: show usage in the Inspector, and fade never-used nodes.

Skipped on purpose: a usage cache, per-plugin roll-up, timezone-local dates (dates are UTC), and hook run detection.
