# Plan: explore UX after the first real-setup test (missing Items, warnings, search, cluster focus, scope, labels)

Status: plan only, 2026-11-04. Nothing here is built. Planner read AGENTS.md, CLAUDE.md, the tracker, DESIGN.md, graph-app.md,
graph-references.md, `claude_code.py`, `server.py`, `cluster.py`, `embeddings.py`, `usage.py` (walk only), `layout.ts`, `paint.ts`,
`model.ts`, `StarMap.tsx`, `Atlas.tsx`, `TopBar.tsx`, and `origin/codex/ticket-11` (`chat.py`, `docs/plans/chat.md`,
`docs/research/sqlite-retrieval.md`). The real `~/.claude` and `~/.claude.json` were **not** read (AGENTS.md hard rule); section A
rests on the code plus the official docs (code.claude.com/docs/en/mcp, /plugins-reference, /settings, /managed-mcp), and gives a
counts-only script for the user to run.

Decisions that need the user's approval are marked **[approve]**. Everything is free and local unless marked **[paid, opt-in]**.

## A. Missing Items

### What the adapter reads today (`claude_code.py`)
- `<config>/skills/*/SKILL.md`, `<config>/skills/synced/*/*/SKILL.md`, `<config>/agents/*.md`, `<config>/.mcp.json`, hooks in
  `<config>/settings.json`; the same under each plugin root found by globbing `plugins/cache/*/*/*/.claude-plugin/plugin.json`.

### What Claude Code actually loads, and the gaps
| Source (docs) | Read? | Gap |
|---|---|---|
| User-scope MCP: `~/.claude.json` top-level `mcpServers` (at `$HOME`, outside `~/.claude`) | No | **Main cause of "only 1 MCP server".** `<config>/.mcp.json` is not a documented location. |
| Local-scope MCP: `~/.claude.json` `projects["<abs path>"].mcpServers` | No | per-project; see G and the `--project` note below |
| Project MCP: `<project>/.mcp.json` | No | needs a project path |
| Managed: `/Library/Application Support/ClaudeCode/managed-mcp.json` | No | rare; read names only if present |
| Plugin `.mcp.json` | Yes, but `json.loads(...)["mcpServers"]` raises KeyError on a file without the wrapper | crash-prone |
| Plugin `plugin.json` `mcpServers` (inline object, path string, or list; `.mcpb`/`.dxt` bundles) | No | plugin servers missed |
| Plugin `plugin.json` `skills`/`agents`/`commands` extra paths | No | Items missed |
| `commands/*.md` (user and plugin slash commands) | No | **a whole kind is missing**; many plugins ship only commands |
| Plugins whose `installPath` is outside `plugins/cache/` (local-directory marketplaces) | No: the glob only looks in `cache/` | whole plugins missed (docs do not state where installPath may point; the script below checks) |
| `enabledPlugins` (`name@marketplace`) in user/project/local settings | No | a disabled plugin is shown as if live |
| claude.ai connectors (Gmail, Drive, Calendar, Docs) | No | **not on disk**: fetched from the account at sign-in (docs). The current "url => connector" rule is wrong: a url server is a remote MCP server, so the scan's "1 connector" is a mislabelled remote server. |

Connectors, free and local: transcripts (already walked by `usage.py`) record tool names like `mcp__claude_ai_Gmail__search_threads`
and `mcp__plugin_<plugin>_<server>__<tool>`. The usage reader can credit `mcp__claude_ai_<Name>__*` to a connector Item it creates
("claude.ai connector, seen in transcripts; not stored on disk"), name only, cost unknown. It cannot see a connector never used in
the window; the Legend/notice says so. `ENABLE_CLAUDEAI_MCP_SERVERS=false` or `disableClaudeAiConnectors` mean none load; the
adapter reads only the boolean `disableClaudeAiConnectors` from settings (never the environment, per AGENTS.md).

### "Mapo"
No plugin of that name is known to the docs, and the planner cannot look. Most likely one of: a CLI on PATH (the brief's example,
Mole, is a macOS cleaner CLI, not a Claude plugin); a plugin installed from a local-directory marketplace (missed by the cache glob);
a plugin disabled in `enabledPlugins`; a project-scope install; or something whose skill was skipped for no description (that
warning already names it). The counts-only script answers which, without printing any name.

### Counts-only diagnostic (user runs it; prints integers and fixed labels only)
Save as `/tmp/cc_counts.py`, read it, run `python3 -I /tmp/cc_counts.py`. It never prints keys, names, paths or values.
```python
import json, pathlib as P
h = P.Path.home(); c = h / ".claude"; j = lambda p: json.loads(p.read_text()) if p.exists() else {}
cj = j(h / ".claude.json"); ip = j(c / "plugins/installed_plugins.json").get("plugins", {})
paths = [P.Path(e["installPath"]) for v in ip.values() for e in v if "installPath" in e]
man = [p for p in paths if (p / ".claude-plugin/plugin.json").exists()]
print("user_scope_mcp", len(cj.get("mcpServers", {})))
print("local_scope_mcp", sum(len(v.get("mcpServers", {})) for v in cj.get("projects", {}).values()))
print("installed_entries", len(paths), "outside_cache", sum("plugins/cache" not in str(p) for p in paths))
print("plugin_json_inline_mcp", sum("mcpServers" in j(p / ".claude-plugin/plugin.json") for p in man))
print("plugin_mcp_json_no_wrapper", sum((p / ".mcp.json").exists() and "mcpServers" not in j(p / ".mcp.json") for p in man))
print("command_files", len(list(c.glob("commands/*.md"))) + sum(len(list(p.glob("commands/*.md"))) for p in man))
print("disabled_plugins", sum(v is False for v in j(c / "settings.json").get("enabledPlugins", {}).values()))
print("mapo_seen", int(any("mapo" in s.lower() for s in [*ip, *(p.name for p in paths)])))
```

### Fix spec (test-first, invented fixtures under `tests/fixtures/`, through `scan()`)
1. **Shape-only server reader** `_servers(mapping, scope) -> Items`, used for every source. Description = `stdio: <basename(command)>`
   (args are dropped: tokens often sit in args) or `<type or http>: <scheme>://<host>` (no userinfo, path, query or port).
   `env` and `headers` are never read into an Item. Fixture plants `sk-ant-PLANTED` in env, headers, an arg and a url query; assert
   it is absent from the scan JSON, report, and every recorded provider input.
2. `~/.claude.json`: `<config>/.claude.json` if present, else `<config>.parent/.claude.json` when the config dir is named `.claude`.
   Parse in memory, take only `mcpServers` keys plus shape; ids `claude-code:mcp_server:user/<name>`. Never print or log the file.
   `read_secrets` gains nothing from it (no values are taken), so nothing new to redact. Opus security review required.
3. Plugin servers: `.mcp.json` with or without the wrapper; `plugin.json` `mcpServers` inline, path or list; bundles counted as
   `bundle` with unknown shape. A malformed file is a warning, never a crash (fixture: no wrapper, bad JSON).
4. Plugins from every `installPath` in `installed_plugins.json` (inside or outside cache), still one manifest per plugin.
5. New kind `command` from `commands/*.md` (frontmatter `description`, else first non-empty line; name = filename stem), user and
   plugin, plus `plugin.json` extra `skills`/`agents`/`commands` paths (resolved inside the plugin root only; symlinks out refused).
   Frontend: a glyph and legend entry for `command` (shares starlight, new shape; dataviz check).
6. `enabledPlugins`: a disabled plugin and its contents stay in the scan with `disabled: true` (dimmed, hollow ring), never removed.
7. Connector Items from transcript tool names (in `usage.py`, after the existing per-block validation); remove the url=>connector rule
   (url servers become `mcp_server` with `remote` in the description).
8. Not done here: project `.mcp.json` and local scope. They come with `scan --project PATH` in G (same reader).

### "Why is X not shown"
Search "nothing found" state (C) says, in order: (a) "Mentioned in a scan warning: ..." if the query appears in any warning (zero
schema change; covers skipped Items); (b) "Not scanned: CLIs on your PATH, claude.ai connectors you have not used in the last N days,
project-only servers (scan with --project)"; (c) the scan's counts by kind. No guessing that X exists.

## B. Warnings

| Warning (today) | Class | Severity | Shown as |
|---|---|---|---|
| `Offline: no labels ...` | mode, not a warning | info | **removed from the count**; the top bar already says "offline scan"; a tooltip carries the sentence |
| `frontmatter is not valid YAML, read ... leniently (<abs path>)` | informational | low | grouped: "2 files have loose frontmatter; read anyway (Claude Code also loads them)" + the ~ paths, copy-path button, and the fix hint "quote the description" |
| `skipped <kind> with no name / no description (<path>)` | **actionable** | high: the Item is missing from the map | "Not on the map: 1 skill has no description" + path |
| `usage: skipped N malformed lines` / `N files (B too big, S symlinks, U unreadable)` | informational | low | one "Usage reading" group, counts only (already fixed on main by #26 + residuals; the viewer showed an older scan) |
| `could not label/verify/count ...`, `could not cluster items` | degraded | medium | "Partly offline: 3 labels failed" grouped by stage, Item names kept |
| `could not save the ... cache` | **actionable** | medium | "Cache not writable: next scan will pay again" + path |

- Paths: the adapter writes `~/...` (home replaced by `~`) at the source in `_frontmatter` and skip warnings, so the scan JSON never
  holds the username. One helper `_shown(path)`; test asserts no `str(Path.home())` in the JSON.
- Grouping is a pure `groupWarnings(strings)` in `model.ts` keyed on the stable prefixes above; a Python test pins those prefixes
  (a contract test) so a reworded warning fails CI rather than falling into "Other".
- UI: the button shows only actionable + degraded counts ("2 to look at"); informational groups sit collapsed under them; each group
  has icon + text (never colour alone), a count, up to 5 paths with "and N more". "Link to the file": copy path (`~` form). No
  `vscode://` link: it needs the absolute path and opens an editor on the user's setup (the app never edits it).
- Public Snapshot (#13): drops `warnings` entirely (paths, Item names in failures, usage counts). Keep that; add a test there that
  a planted `~/` path and a planted warning text are absent.

## C. Natural-language search (free-first)

**Pipeline per query** (one backend, `src/constellation/retrieve.py`, shared with #11):
1. Exact and prefix name match (the current client `search()` stays for instant 0 ms feedback on every keystroke).
2. FTS5 BM25 over name, description, label, kind (porter tokenizer) plus a trigram FTS5 table for substrings and small typos.
   Query is tokenized and quoted, bound as a parameter (reuse #11's rule: never run user FTS syntax).
3. Local semantic: bge-small (already used by `scan`) on **raw** unit vectors (not the centred clustering vectors;
   `sqlite-retrieval.md` warns), cosine against each Item's `name: description`.
4. Fuse with Reciprocal Rank Fusion (k=60); exact name always first; stable id tie break. Top 8.
5. "Why it matched", one short line: `name starts with "pdf"`, `description mentions "slides"`, `close in meaning (strong|weak)`,
   `in cluster "Documents"`. Never a raw score.
6. "Did you mean": `difflib.get_close_matches` over name tokens (stdlib) when every list is empty or weak.
7. Clusters are searchable too (a "Clusters" group); picking one runs cluster focus (D).

**Where vectors live**: computed in memory at server start in a background thread, keyed by the scan file's sha256, rebuilt when it
changes. ~250 Items x 384 floats is ~0.4 MB in memory, ~1-3 s to embed on CPU once the model is cached. **Not** in the scan JSON
(~2 MB of floats; a public Snapshot would have to strip them; vectors of unsanitised text could leak). No disk cache at this scale.
Without the `local` extra or before warm-up, steps 1-2 run alone and the UI says nothing (no error).

**API**: `GET /api/search?q=` (<=200 chars, `local_only`), returns `[{id, why}]` ids only. The query never leaves the machine; no
query log. Frontend debounces 120 ms, merges server results under the instant ones ("Related" group), aborts stale requests.
**Latency budget**: instant tier <5 ms; server tier p95 <60 ms warm (embed one query ~10-20 ms + 250 dot products + FTS); measured
in a test with a fake embedder for logic and once by hand for real numbers.

**Shared with #11**: #11 builds an FTS5 table per chat request in `_retrieve`. After #11 merges, move that into `retrieve.py`
(`Index.from_scan(data, embed=None)`, `Index.query(q, k)`), used by `/api/search` and chat `_retrieve`. Do not start this before
#11 is on main (same file, `server.py`). **[approve]** #11's plan says "no new embeddings in the first version"; adding local
vectors to the shared index is a new decision (privacy-neutral: local only), recorded in the tracker.

**Eval**: 30 invented queries against `demo-250.json` (synonyms "make slides" -> pptx skill, typos "shadnc", paraphrases), recall@5
for FTS-only vs hybrid; hybrid is adopted only if it wins. A model query rewrite is **future, [paid, opt-in], [approve]**, not here.

## D. Cluster focus

**Entry**: click a cluster name on the canvas; pick a cluster in search; Enter on a focused name. The painter records each drawn
name's screen box on the cluster (`c.box`); `StarMap` hit-tests it in `onBackgroundClick` and sets `cursor: pointer` on hover over
a box (names never sit on stars, so no clash with node clicks).

**Camera**: force-graph's `zoom(k, ms)` and `centerAt(x, y, ms)` are two uncoupled tween.js Quadratic.Out tweens, which drift
sideways mid-flight. Instead drive one rAF flight like the existing wheel handler: `d3-interpolate`'s `interpolateZoom` (van Wijk
smooth zoom, rho 1.2) from the current view to the target, eased with `d3-ease` `easeCubicInOut`, duration
`clamp(interp.duration * 0.8, 700, 1300) ms`; each frame `g.zoom(k, 0)` + `g.centerAt(x, y, 0)`. Both packages are already in the
tree via d3-zoom; add them explicitly at that version. **[approve]** small deviation from "d3-zoom transition": same d3 family,
coupled path. Any wheel, pointerdown or key cancels the flight. Reduced motion: jump, 140 ms fade of the dimming only. scroll-craft
was consulted for easing only: in-out cubic, no overshoot, no bounce.

**Target**: pure `focusView(cluster, insets, W, H) -> {x, y, k}` in `layout.ts`: fit the circle into the sky left free by the top
bar, the card and any inspector, `k <= fitK * 10`; for the huge "Other" region the same rule.

**During and after**: `focus.cluster = c` in `paint.ts`: other clusters' stars ease to 0.12 (a bit above `--fade` so context stays),
their halos to 0.2, their names hide; links leaving the cluster dim. Member names come in by the existing semantic-zoom priority,
staggered 25 ms each by cost then degree (max ~400 ms), so labels appear as the camera lands, not before.

**Cluster card** (left slot, the same slot as Brief and Chat: one occupant, others collapse to their pills; DESIGN.md glass):
name (Newsreader italic), "18 Items", kind mix as glyph + count chips; always-on total "12,340 tokens known, 7 of 18 unknown"
(never 0, never summed over unknown); top 5 members by cost reusing the Brief bar rows (click -> Inspector); Overlaps inside by
verdict with pairs (click -> `selectPair`); if usage exists "6 not seen in 86 transcripts over 4 days" with the window caveat; Item
list (all members, kind glyph, cost) as the accessible equivalent of the canvas. Data is all client-side from the model; no API.

**Return**: breadcrumb in the top bar "Constellation / Documents" (root click returns); Esc closes the Inspector first, then exits
the cluster (flies back to the fitted view); browser Back via `history.pushState` with `#cluster=<slug>` (also a deep link).
Keyboard: search -> Enter; inside a cluster, arrow keys step among members only; Tab reaches the card list. The aria-live line
says "Documents, 18 Items".

**Panels**: >=960 px card left + Inspector right; 641-959 they alternate (existing rule); phone: card is the bottom sheet at 40dvh,
the camera frames above it; picking a member swaps to the Inspector sheet with a "Back to Documents" button.
**Performance**: one full paint per frame for ~60-80 frames, same as wheel zoom today; skip name placement for dimmed clusters while
flying. Budget <8 ms per frame at 250 Items (dev `performance.mark`).
**layout:check additions**: for every cluster in `demo-250.json` at desktop and phone: `focusView` k within zoom limits, the circle
inside the free sky with the card inset, on-screen radius >= 120 px desktop / 90 px phone, and the flight path's first and last
frames match the start and target views.

## E. Use cases (ranked by value / effort)

| # | Idea | Value | Effort | Privacy / cost |
|---|---|---|---|---|
| 1 | Session-start budget meter: always-on total (known + unknown count) and what the top 5 cost | high | S (data exists) | local, free |
| 2 | "If I remove these N, I save X": tick rows in Brief/cluster card, live total, into the checklist | high | S (`frees` exists) | local |
| 3 | What changed since last scan: added/removed/changed Items and cost delta | high | M (keep previous scan file) | local; Snapshot excludes |
| 4 | Stale/unused view: never seen in window, ranked by cost, with the short-window caveat | high | S (usage exists) | local; Snapshot drops usage |
| 5 | Global vs project-local suggestions (G) | high | M | local; per-project data never leaves |
| 6 | Trigger collisions: skills whose descriptions would fire on the same prompt (#18) | med | M (embeddings exist) | local; verifier opt-in paid |
| 7 | Health score: one number from cost, duplicates, unused, broken frontmatter, with "why" | med | S | local; risk of gamification, keep the parts visible |
| 8 | Export cleanup checklist as a reviewable shell script (`mv` to a backup dir, never `rm`) | med | S | local; the user runs it, the app still never edits |
| 9 | Shareable Snapshot (#13) | med | in flight | sanitised, drops warnings/usage |
| 10 | Risky-hook hygiene: hooks that curl/eval/run from /tmp | med | M | local, static only |

Do next: 1 and 2 together (one small ticket), then 4, then 3. G after the per-project usage extension is reviewed.

## G. Global vs project-local Suggestions (cheap)

**Signals, local only, in order**
1. Per-project usage: `usage.py` already walks `~/.claude/projects/<dir>/`. Count uses per `(item, project_key)`. The key is the
   folder name, kept in memory and in a new local-only field `usage_by_project: {item_id: {pkey: count}}` where `pkey` is an opaque
   `p1..pN` in the scan JSON plus a separate local map `projects: {pN: label}`. **[approve]** label = the last path segment of the
   decoded folder name (e.g. `constellation`), shown in the local app only; the encoded folder name is lossy (`-` for `/`) so
   the label is a hint, not a path. Never sent to a provider, never in a warning, dropped by #13 Snapshot (both fields).
2. Concentration rules over the window: `>= 80%` of uses in one project and `>= 3` uses -> "move to <label>/.claude/..."; used in
   `>= 3` projects -> "keep global"; 0 uses -> the existing `remove_unused` Suggestion, ranked by always-on cost; everything else
   -> no Suggestion.
3. Specificity tie-breaker for low-evidence Items: cosine of the Item's raw vector to a fixed list of ~40 invented stack anchors
   ("Next.js", "Django", "Stripe", "LaTeX", ...) vs generic anchors ("writing", "code review"); a high stack score with 1-2 uses in
   one project nudges to "probably project-local, low confidence". Local, free.
4. Scope facts: plugin contents move as a plugin (Suggestion says "enable plugin X only in <project>'s .claude/settings.json
   `enabledPlugins`"), user skills/agents/commands move as files. MCP servers: "move to <project>/.mcp.json or local scope".

**As a Suggestion**: new kind `move_to_project` in `suggestions.py` (content-derived id, `tokens_saved` = the Item's always-on cost,
saved in every other project's sessions; unknown stays unknown). Reason text, e.g. "Used 9 times, all in constellation, over 4 days.
Move ~/.claude/skills/x to constellation/.claude/skills/x." It flows through `review`, the Brief (a "Scope" group), and the
checklist line; the app never moves anything.
**Confidence tiers** (shown as words): high = window >= 14 days and >= 5 uses; medium = >= 3 uses; low = specificity only. With today's
~4-day window everything is at most medium, and the Brief says "based on 4 days of transcripts; Claude Code deletes older ones".
Minimum evidence: no move Suggestion under 3 uses.
**[paid, opt-in]** middle cases only (medium tier, specificity between thresholds): one cached Haiku verdict "generic or
stack-specific?" from the Item's redacted name + description, through `guarded*` and the label cache pattern (sha of redacted
prompt + model id, 0600). Never project names, counts or transcript text. Off unless `--scope-verdicts`; dry run shows the prompt.
**Opus privacy checklist for the #20 extension**: project keys never in warnings, report text sent anywhere, provider inputs or
caches; Snapshot drops `usage_by_project` and `projects`; labels derived only from folder names (no reading project files); the
pinned-descriptor walk is unchanged; a planted project name is absent from every recorded provider call and every cache file.
**Tests**: invented `projects/` trees (3 projects, 4 Items: one single-project, one spread, one unused, one ambiguous), boundary
tests at 79/80% and 2/3 uses, window-day tiers, Snapshot stripping, recording fakes for the opt-in verdict.

## H. Labels and halo

**Label rules**
- Hierarchy: cluster names 13-17 px Newsreader italic (`--halo-name`); Item names 11-12 px Inter 450 (`--text-2`), focused/hovered
  Item 12 px 550 `--text`. Cluster names fade out between z 1.2-1.8 (keep), and in cluster focus the focused name moves to the card.
- Zoom: fitted view = cluster names + hub names (degree >= 4); z >= 1.3 leaves; in cluster focus all members of that cluster.
- Collision: keep the greedy placer; truncate Item names over 22 chars with an ellipsis on the canvas (full name in hover and card).
- Contrast: every canvas name keeps the 4 px night stroke; checked >= 4.5:1 on the halo (already 11.2+ for cluster names).
- Hover label: a small DOM tooltip next to the hovered star: kind glyph + name + "1,240 tokens always on" or "cost unknown"
  + one-line label. DOM, not canvas, so it is crisp and screen-reader-free (the inspector is the accessible path).

**Halo bug**: `paint.ts pre()` draws each halo at `c.x, c.y` with radius `c.r`, set once by `layout()` (comment: "the circle itself
is fixed"); cluster-name placement also uses `c.x, c.y`. Dragging a star moves it (and, through links, its neighbours), but nothing
moves the halo, so it stays home. There is no cluster drag; "dragging a cluster" is dragging a hub. **Fix: the halo follows the live
offset with smoothing.** Pure `haloOf(c) -> {x, y, r}` in `layout.ts`: centre = home `(c.x, c.y)` + (live member mean - home member
mean, from `sx/sy`); radius = `max(c.r, min(1.4 c.r, farthest member + r + GAP))`; `paint.ts` eases toward it with `FEEL.labelMs`
and uses it for the halo and the name. At rest the offset is exactly 0, so the picture is unchanged. Rejected: dragging a hub drags
the whole cluster (changes the interaction and fights the fixed homes); hiding the halo while dragging (loses the context the drag
is about). `layout:check`: after layout, `haloOf(c)` equals `(c.x, c.y, c.r)` for every cluster; moving one member by (d, 0)
shifts the centre by d / n; radius never exceeds 1.4 c.r.

**What the graph is built from**: React 19 + Vite + TypeScript, `react-force-graph-2d` (force-graph) drawing on one HTML canvas,
d3-force for the settle and drag springs, our own painter (`paint.ts`) for glow, halos and atlas lettering, Tailwind + shadcn/ui
(cmdk, Radix popover) for the chrome. **Motion** (`motion` package) is worth adding only for the DOM panels (cluster card enter/exit,
Brief/Chat/card slot swap, sheet drag on phones) if CSS transitions start needing layout animation or gesture springs; it does
nothing for the canvas, so start with CSS and add Motion in the cluster-card ticket only if the slot swap looks wrong. **Three.js /
WebGL is not needed**: 250 Items paint in a few ms on 2D canvas and the idle loop already stops; WebGL pays off at thousands of
nodes (then sigma.js or cosmos.gl, per CLAUDE.md) or for a landing-page hero (#15, staged `threejs-skills`).

## F. Tickets

| T | Ticket | Files | Model / agent | Order |
|---|---|---|---|---|
| T1 | Counts-only diagnostic: user runs the A script, answers recorded (numbers only) in the tracker | none | user + Sonnet to record | first, parallel |
| T2 | Shape-only MCP reader + `~/.claude.json` user scope + plugin `.mcp.json`/`plugin.json` servers + drop url=>connector | `claude_code.py`, tests | **Opus design + security review**, Sonnet implements | after T1 |
| T3 | `command` kind, plugin extra paths, installPath outside cache, `enabledPlugins` disabled flag | `claude_code.py`, `model.ts`, `Legend.tsx`, `paint.ts` glyph | Sonnet; dataviz check for the glyph | after T2 (same file) |
| T4 | Connector Items from transcript tool names | `usage.py`, tests | Sonnet, Opus review (transcripts) | parallel with T2 |
| T5 | Warnings: `~` paths at source, prefix contract test, `groupWarnings`, grouped popover, Offline as mode | `claude_code.py` (one helper), `model.ts`, `TopBar.tsx` | Sonnet | parallel; rebase onto T2 |
| T6 | Halo follows live offset + `layout:check` | `layout.ts`, `paint.ts`, metrics script | Sonnet | parallel, small, do early |
| T7 | Label rules + DOM hover tooltip with cost | `paint.ts`, `StarMap.tsx`, new `Hover.tsx` | Opus design note first (`docs/design/`), Sonnet refines with screenshots | after T6 (paint.ts) |
| T8 | Cluster focus: name hit-test, `focusView`, interpolateZoom flight, dimming, breadcrumb, Esc/Back, metrics | `paint.ts`, `StarMap.tsx`, `Atlas.tsx`, `TopBar.tsx`, `layout.ts` | Opus design (motion + card layout), Sonnet builds; `/prototype` the flight first | after T6; before or with T7 by one owner (paint.ts) |
| T9 | Cluster card + left-slot rule with Brief/Chat + phone sheet | new `ClusterCard.tsx`, `Atlas.tsx` | Sonnet (Motion only if CSS fails) | after T8 and #11 merge (Atlas.tsx) |
| T10 | `retrieve.py` shared index (move #11 FTS5), trigram, RRF, `/api/search`, eval set | `retrieve.py`, `chat.py`, `server.py`, tests | Opus decides vectors **[approve]**, Sonnet builds | after #11 on main |
| T11 | Search UI: Related group, why line, clusters group, did-you-mean, not-found hints (A) | `TopBar.tsx`, `Atlas.tsx` | Sonnet | after T10, T5 (TopBar) |
| T12 | Budget meter + "remove N save X" (E1+E2) | `Brief.tsx`, `brief.py` | Sonnet | after T9 (left slot) |
| T13 | Per-project usage (G1) | `usage.py`, models, #13 strip | **Opus plan + privacy review** | after T4 (usage.py) |
| T14 | `move_to_project` Suggestions + tiers + Brief Scope group; opt-in verdict later | `suggestions.py`, `brief.py`, `report.py` | Sonnet; Opus review; paid part needs approval | after T13 |

Parallel now: T1, T4, T5, T6. Same-file chains: `claude_code.py` T2 -> T3 (T5 touches one helper, rebase); `paint.ts` T6 -> T8 -> T7;
`Atlas.tsx` #11 -> T9 -> T11; `usage.py` T4 -> T13. Every ticket updates `docs/plan-tracker.md` in its commit; the three
**[approve]** items (vectors in the shared index, interpolateZoom flight, project labels) go to the user before T8, T10 and T13.
