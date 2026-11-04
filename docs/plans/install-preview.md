# Install cost preview (#63): plan

Status: plan, 2026-11-04. No app code. Three tickets, merged in order P1 -> P2 -> P3. Every ticket ends by appending its own `## #63x` section to `docs/plan-tracker.md` (append only, at the end; on a rebase conflict keep both sections).

## Decisions (put these in every brief)

- **Input is a local directory only.** `constellation preview DIR`. The app never fetches the network. A git clone helper is **out of scope**: the user runs `git clone` themselves (README says so). No provider is imported or called; `load_env()` is not run for `preview` or `delta`.
- **Layouts read:** plugin (`DIR/.claude-plugin/plugin.json`), pack (`DIR/skills/`, `agents/`, `commands/`, `.mcp.json`, `hooks/hooks.json`), single skill (`DIR/SKILL.md`). Anything else: exit 2, "No plugin, skill pack or SKILL.md found in <name>."
- **Adapter reuse:** a new `read_pack()` in `claude_code.py` calls the existing `_read_root` / `_plugin_servers` with a non-empty scope (so `_inside` refuses outside symlinks). It never calls `_claude_json`, `_installed`, `read_lock` or `read_usage`. Bodies are dropped.
- **Tokens every session** (new decision, needs the user's nod): for skill, agent and command Items, the exact count when the same `name: description` text is already in the token-count cache (`costs.measure(..., counter=None)`, free), else an **estimate** `ceil(len(text.encode()) / 4)` shown as "estimated". MCP servers and hooks are **unknown** (tool list and hook output exist only after install), counted separately, never 0. The plugin Item itself is a container and is not counted.
- **Possible overlap, not an Overlap** (new decision): the saved scan holds no bodies and the verifier is paid, so the preview reports "possible overlap" only: same name and kind (always), and meaning similarity from the shared `retrieve.Index` vectors (`dot >= retrieve.SIMILAR`, best one per new Item, skill/agent/command only). A plugin name already in the scan sets `already_installed`.
- **The "after" delta** compares two saved scans: `constellation delta BEFORE AFTER`. No UI for the delta (CLI only, named as skipped).
- **Untrusted folder safety** (refuse the whole preview, exit 2, before anything is parsed): any symlink (file or dir) resolving outside DIR; any entry that is not a regular file, dir or symlink (a FIFO would block `read_text`); any `.md`/`.json` over 1 MB; more than 2,000 entries. `.git/` and `node_modules/` are pruned from the walk. Every name, description, pack name and warning goes through `_plain()` (drop Unicode category `C*`: ANSI escapes, bidi overrides, zero-width; collapse whitespace; name cap 80, description cap 200) and `redact()` with the pack's own `read_secrets(DIR)`. Absolute paths never appear in output (warnings have `str(DIR)` replaced by the pack name). Hook commands and MCP shapes are text only, never run. Description text is never sent to a model; React renders it as text nodes only.
- **Privacy:** nothing new leaves the machine. The preview file is separate from the scan and written 0600; `snapshot()` is an allowlist and drops any extra key (tested in P1).

## P1 (#63a) Read a pack safely and compute the preview. Size M. Python only.

Files: edit `src/constellation/claude_code.py` (add `read_pack` only; no existing function changes); new `src/constellation/preview.py`; new `tests/test_preview.py`; new invented fixture `tests/fixtures/preview_pack/pdf-kit/` (plugin.json `pdf-kit`, skills `trace-canvas` and `pdf-reader`, command `fold-beacon`, `.mcp.json` with one stdio server `pdfd`); edit `pyproject.toml` (`only_mutate` += `src/constellation/preview.py`).

```python
# claude_code.py
def read_pack(root: Path) -> tuple[str, str, list[Item], list[str], list[Relation]]:
    """(pack name, layout "plugin"|"pack"|"skill", items, warnings, relations); reads only inside root."""
# preview.py
MAX_ENTRIES = 2000; MAX_FILE_BYTES = 1_000_000
def check_tree(root: Path) -> str | None            # refusal reason (relative path named), or None
def _plain(text: str, cap: int) -> str
def preview(root: Path, scan: dict[str, Any] | None, embedder: Embedder | None = None,
            cost_cache: Path | None = None, vector_cache: Path | None = None) -> dict[str, Any]
```
Preview dict (also the file format): `{"version": 1, "pack": {"name", "layout"}, "items": [{"id", "kind", "name", "description", "always_on": int|None, "estimated": bool}], "counts": {kind: n}, "always_on": {"counted": int, "estimated": int, "unknown": int}, "overlaps": [{"new_id", "existing_id", "existing_name", "why": "same name"|"similar meaning"}], "already_installed": bool, "compared": bool, "note": str|None, "warnings": [str]}`. Index ids for pack Items are prefixed `new:` so they never collide with scan ids. `vector_cache` defaults to `retrieve.DEFAULT_CACHE` (already redirected by `conftest.py`).

TDD slices (write each test, see it fail, make it pass):
1. `test_plugin_pack_lists_its_items` - fixture pack: 5 Items (plugin, 2 skills, command, mcp_server), `layout == "plugin"`, `counts == {"plugin":1,"skill":2,"command":1,"mcp_server":1}`.
2. `test_skill_pack_and_single_skill_layouts` - tmp `skills/a/SKILL.md` gives `layout "pack"`; tmp `SKILL.md` alone gives `layout "skill"`, 1 Item.
3. `test_tokens_estimated_from_text_length` - skill `name: x`, description of 40 ASCII chars: `always_on == ceil(len("x: "+desc)/4)`, `estimated is True`; mcp_server `always_on is None`; totals `unknown == 1`.
4. `test_cached_count_is_used_and_marked_exact` - seed the cost cache with `cache_key("x: "+desc, set())` -> 123: `always_on == 123`, `estimated is False`, `counted == 123`.
5. `test_same_name_is_a_possible_overlap` - scan dict with skill `trace-canvas`: overlap `why == "same name"`, `existing_id` is the scan id; no embedder needed; `compared is True`.
6. `test_similar_meaning_uses_local_vectors` - invented concept embedder (as in `tests/fakes_search.py`): `pdf-reader` matches scan skill `pdf-tools`, `why == "similar meaning"`; with `embedder=None`, `note` says meaning-based overlap is off.
7. `test_already_installed_plugin` - scan holds `claude-code:plugin:pdf-kit`: `already_installed is True`.
8. `test_no_scan_means_not_compared` - `scan=None`: `compared is False`, `overlaps == []`.
9. `test_refuses_symlink_outside` - `skills/evil -> tmp/outside` and, separately, `.mcp.json -> outside file`: `check_tree` returns a reason naming `skills/evil`; `preview` raises `ValueError` with it; the outside file is never opened (monkeypatch `Path.read_text` to record paths; assert outside path absent).
10. `test_refuses_fifo_huge_and_too_many` - `os.mkfifo`, a 1,000,001-byte `SKILL.md`, 2,001 empty files: each refused.
11. `test_control_and_bidi_text_is_stripped` - description `"\x1b[31mred‮ evil​"` -> `"red evil"`; name of 120 chars capped at 80.
12. `test_no_absolute_path_and_secrets_redacted` - pack `.mcp.json` env holds a 12-char secret also in a description: `json.dumps(result)` contains neither `str(tmp_path)` nor the secret.
13. `test_snapshot_drops_preview_fields` - `snapshot({**demo_scan, "preview": result})` has no `preview` key and no `pdf-kit` text.
14. `test_malformed_pack_is_refused_not_crash` - `hooks/hooks.json` = `{"hooks": {"Stop": [{}]}}` and `plugin.json` without `name`: `ValueError("could not read the pack: malformed file")`.

Opus review must check: every path the adapter opens is under DIR after the walk (plugin.json, .mcp.json, settings.json, hooks.json, mcpServers file entries); no `~/.claude.json`, lockfile or transcript read; `_plain` covers C0/C1/Cf; no absolute path in output; bodies discarded; no provider import in `preview.py`.

Acceptance: [ ] 14 tests pass [ ] `read_items` diff is zero lines [ ] `preview.py` in `only_mutate`, mutmut clean [ ] no import of `anthropic_llm` in `preview.py` (`grep`).

## P2 (#63b) CLI `preview` and `delta`. Size S. Depends on P1.

Files: edit `src/constellation/cli.py` (two subparsers added after `review`, handlers `_preview`/`_delta` at the end, before `_write`; dispatched before `load_env()`); edit `preview.py` (`render_preview`, `delta`, `render_delta`); new `tests/test_cli_preview.py`; edit `README.md` (commands, "Files Constellation reads" row: "a folder you pass to `preview`, read only, nothing run").

```text
constellation preview DIR [--against constellation.json] [--out FILE] [--force]
constellation delta BEFORE AFTER
```
```python
def render_preview(p: dict[str, Any]) -> str
def delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]
#  {"added": [ids], "removed": [ids], "added_by_kind": {kind: n}, "always_on_known": int,  # sum known after - sum known before
#   "unknown_added": int, "new_overlaps": [{"a_id","b_id","verdict","reason"}]}
def render_delta(d: dict[str, Any], names: dict[str, str]) -> str
```
Embedder: `cli._local_embedder()` (None if fastembed missing). `--out` writes via `report.write_private` (0600); an existing file needs `--force`. Missing `--against` file: still exit 0, line "No saved scan at constellation.json, so overlap with your setup was not checked. Run `constellation scan` first."

Output copy (exact wording; the numbers here are illustrative, tests compute them from the fixture text with the P1 formula):
```text
pdf-kit (plugin): 5 Items - 2 skills, 1 command, 1 MCP server, 1 plugin
Every session: about 61 tokens (0 counted, 61 estimated from text length); 1 MCP server or hook unknown until installed
Possible overlap with your setup: 1
  trace-canvas (skill) and your trace-canvas (skill): same name
Nothing was run or sent. Hook commands and MCP servers are shown as text only.
```
Delta: `+5 Items, -0 (2 skills, 1 command, 1 MCP server, 1 plugin)` / `Every session: +61 known tokens; 3 added Items have unknown cost` / `New Overlaps with added Items: 1` then one line each.

TDD: 1 `test_preview_prints_summary` (fixture + `demo-250.json` copy: lines above, exit 0). 2 `test_preview_writes_private_file` (mode `0o600`, `--force` needed second time, exit 2). 3 `test_preview_never_touches_network_or_env` (monkeypatch `socket.socket.connect` to raise and `cli.load_env` to fail; exit 0). 4 `test_preview_refusal_exit_2` (outside symlink: stderr names `skills/evil`). 5 `test_preview_not_a_dir_or_empty` (exit 2, exact messages). 6 `test_delta_counts_added_removed_and_cost` (two invented scan dicts: `always_on_known == 61`, unknown counted, removed listed). 7 `test_delta_new_overlaps_only` (an Overlap in both scans is not listed).

Privacy: none new (reads two local files the user names; prints names only). Opus review not needed beyond P1's.

Acceptance: [ ] 7 tests [ ] `constellation preview --help` / `delta --help` text [ ] README updated [ ] no `load_env` on these paths.

## P3 (#63c) Preview panel in the Brief. Size M. Depends on P2.

Files: edit `server.py` (`create_app(..., preview: Path | None = None)` and `GET /api/preview` with `Depends(local_only)`: 404 when None or unreadable or not a dict with `items` list; the path is fixed at startup, never from the request); edit `cli.py` (`open --preview FILE`); new `tests/test_server_preview.py`; new `frontend/src/components/Preview.tsx`; edit `frontend/src/components/Brief.tsx` (one import, one `<Preview onItem={onItem} />` as the first child of the scroll area); new `docs/design/demo-preview.json` from `uv run constellation preview tests/fixtures/preview_pack/pdf-kit --against docs/design/demo-250.json --out docs/design/demo-preview.json`. **Must not touch** `Atlas.tsx`, `StarMap.tsx`, `Chat.tsx`, `chat.py`, `answer.py`, `model.ts` (the `PreviewData` type lives in `Preview.tsx`).

UI spec: Preview fetches `api/preview` itself (AbortController; any non-200 or bad shape renders nothing: no spinner, no error). Section above "Most expensive, always on", same type scale and tokens (`text-sm font-medium` heading, `text-xs text-text-3` notes, `font-mono tabular-nums` numbers, `glyph data-kind`, row buttons as in Brief, no colour literal, PALETTE only).
- Heading: `If you install {name}`; badge `Already installed` (shadcn Badge) when true.
- Line: `{n} Items · about {total} tokens every session`; note `{counted} counted, {estimated} estimated from text length`; when unknown > 0: `{unknown} MCP servers or hooks: unknown until installed`.
- Rows (up to 5, then `+ {k} more`): `{new name}` / `and your {existing name}` / tag `same name` or `similar meaning`; click calls `onItem(existing_id)`. Empty: `No overlap with your setup found.` Not compared: `Not compared with a saved scan.`
- Footer: `Read locally. Nothing was run or sent.`

TDD: 1 `test_preview_route_serves_file` (200, JSON equal). 2 `test_preview_route_404_without_flag_or_bad_file`. 3 `test_preview_route_is_local_only` (Host `evil.example:8765` gets 403, as `/api/brief` does). 4 `test_open_passes_preview` (fake `serve`, missing file exit 2).

Screenshots (demo data only, `constellation open docs/design/demo-250.json --preview docs/design/demo-preview.json --no-browser`, 1440x900 and 390x844): [ ] Brief open with preview section [ ] overlap row click selects `trace-canvas` on the map [ ] long pack name wraps (edit a copy to 60 chars) [ ] phone sheet scrolls to the cost section [ ] without `--preview` the Brief looks as before [ ] Brief collapsed.

Opus review: the route reads only the startup path, has `local_only`, and the panel renders description text as text (no `dangerouslySetInnerHTML`, no markdown).

Acceptance: [ ] 4 tests [ ] `npm run lint typecheck build layout:check chat:check` pass [ ] only the listed frontend files changed (`git diff --stat main`) [ ] 6 screenshots viewed.

## Skipped (named)

Git clone helper; UI for the delta; static hook byte weight for pack hooks (`hooks.static_hook_texts` only finds installed plugin roots); body-hash duplicates against the user's setup; MCP tool-list cost before install. Limit: a pack edited between `check_tree` and the read (TOCTOU) is not caught; the folder is the user's own choice.

## Validation script (whole batch, from the repo root)

```bash
uv sync --all-extras
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pytest -q tests/test_preview.py tests/test_cli_preview.py tests/test_server_preview.py
uv run pytest -q
uv run mutmut run --max-children 2 && uv run mutmut results   # prints nothing
uv run constellation preview tests/fixtures/preview_pack/pdf-kit --against docs/design/demo-250.json
uv run constellation delta docs/design/demo-offline.json docs/design/demo.json
git diff --stat main -- src/constellation/claude_code.py   # read_pack added only
npm --prefix frontend ci && npm --prefix frontend run lint && npm --prefix frontend run typecheck
npm --prefix frontend run build && npm --prefix frontend run layout:check && npm --prefix frontend run chat:check
uv run constellation open docs/design/demo-250.json --preview docs/design/demo-preview.json --no-browser  # then screenshot
```
