# Plan: author packs as a visible group, and better offline cluster names (#52)

Diagnosis of #52 (parent #1). No app code changed. Evidence comes from a counts-and-names-only script run with `python3 -I`
in the session scratchpad (skill folder names, symlink layout, lockfile `source` counts, and Item and cluster names from the
saved real scan). No file bodies, descriptions, environment or `~/.claude.json` were read. Only the public pack and skill names
already in the issue are written here. Other real names are left out (AGENTS.md).

## Findings

### 1. How the Matt Pocock skills are installed, and whether all of them are read
- They come from the `skills` CLI (`npx skills add mattpocock/skills`), not from a Claude Code plugin. That CLI clones each skill
  into `~/.agents/skills/<name>/` and symlinks it into `~/.claude/skills/<name>`. It records the origin in
  `~/.agents/.skill-lock.json`, with one entry per skill: `source` (`mattpocock/skills`), `sourceType` (`github`), `sourceUrl`,
  `pluginName` (`mattpocock-skills` on 27 of the 38 entries, empty on 11), `skillPath`, the hash and dates.
- On disk: `~/.claude/skills` has 79 entries. 49 are symlinks, all into `~/.agents/skills`, and none is broken. There are 72
  `skills/*/SKILL.md` and 17 `skills/synced/*/*/SKILL.md`. No SKILL.md sits at any deeper layout that the adapter would skip.
- The lockfile has 51 entries from 6 sources. 38 are `mattpocock/skills`. All 38 are symlinked, and all 38 are in the scan by name.
- Read vs on disk: the scan has 170 skills (72 top-level + 17 synced + 81 from plugins), which matches the disk exactly. The
  adapter follows the symlinks (`Path.glob` + `read_text`). The plugin-only symlink refusal in `_inside` does not apply to user
  skills. **Nothing is missing.**
- Plugins: 11 installed, 11 cache dirs and 9 known marketplaces. None of them matches `matt` or `pocock`. The lockfile's
  `pluginName` belongs to the skills CLI, not to Claude Code: there is no `installed_plugins.json` entry and no manifest. So
  **no Plugin Item is missing**. "The Matt Pocock plugin" does not exist as a plugin, and nothing in the scan records that the 38
  skills belong together.
- Why they cannot be found as a group: the 38 skills land in **17 different clusters**. That is correct, because clusters group
  by meaning and these are a mix of debugging, design, writing and setup skills. The only thing they share is their origin,
  and the Item model does not carry it: `Item.source` is the adapter (`claude-code`), not the pack.

### 2. Why the cluster is called "ask matt"
- The scan is offline (`labels` is empty: 0 labels). In `cluster.py` `cluster()`, with no labels, a cluster is named after
  the member whose vector is closest to the cluster centre (`items[by_closeness[0]].name`). The 3-member cluster
  {`ask-matt`, `setup-matt-pocock-skills`, one non-pack skill} is closest to `ask-matt`. Then `model.ts` `tidy()` turns
  `ask-matt` into `ask matt`. `classify.py` plays no part offline. The name is one member's name, so it reads like an Item, not
  a topic.
- The same rule names an 11-member cluster after one non-pack debugging skill, although that cluster holds `tdd`,
  `code-review` and `diagnosing-bugs`. 8 of the 37 clusters have 1 member and 6 have 2. Those 14 fold into "Other" in the UI
  (`buildModel`, `< 3`), so `scaffold-exercises` (a 1-member cluster) shows no cluster name at all.
- With an API key, a labelled scan (not run here, by request) changes only the text: a cluster takes the cached Haiku label
  (`classify._prompt`: "2 to 4 word topic") of its member nearest the centre, so "ask matt" becomes a short topic. Membership
  stays the same, the label still describes one member rather than the whole group, and nothing shows the pack. The first run
  costs one Haiku call per Item (about 251). After that, labels come from `~/.cache/constellation/labels.json`, so they are free.

### 3. Why a skill star can show without a cluster name at deep zoom
Per `labels.md` section 1 and `paint.ts` `clusterLabel`:
1. Above z 1.55, cluster names are hidden. Only the hovered or selected Item's cluster keeps its name (`focused`). This is why
   the selected `setup-matt-pocock-skills` star in the screenshot shows "ask matt" and the stars near it show none.
2. Clusters under 3 members are merged into "Other". The hover tooltip leaves out "Other" (labels.md 9.2), so those stars
   never carry a group name.
3. `chooseSpot` returns null when every rim spot hits a placed name or more than `allowed` stars (2 when focused), and then the
   name is skipped rather than nudged (labels.md 6).
4. The screenshot cuts the name with `...`. Main uses one `…` (`cutName`), so the viewer was running an older build.

## Fix spec (Sonnet implementer; test-first through `scan()` and the frontend checks; invented fixtures only)

### F1. Origin per Item (Python, `claude_code.py`, `models.py`)
- `Item.origin: str | None = None`, a short human string: the pack or plugin it came from. Leave `source` as the adapter.
- Set by `_read_root`:
  - plugin contents: `origin = meta["name"]`, also on the Plugin Item itself.
  - synced skills: `origin = "claude.ai"`. The synced sub-folder is never used, because it may be an account id.
  - user skill whose folder is a symlink: resolve it with `os.path.realpath`. If `<target>.parent.parent/.skill-lock.json`
    is a regular file, parse it in memory and take only `skills[<target folder name>]["source"]` if it is a string. Redact it,
    cap it at 60 characters, and drop it unless it matches `^[\w.@/-]+$`. Otherwise `origin = None`.
  - Never read `sourceUrl`, the hashes or the dates, and never put a path in `origin`.
  - A malformed lock gives one warning (`could not read skill lock: unreadable or not valid JSON`, with no text from the
    file). Add the new prefix to `RULES` in `model.ts` and to `tests/test_warning_contract.py`.
  - The lock is found next to the symlink target, never through `$HOME`, so fixtures never touch the real home (the same
    reason `_claude_json` checks the config dir's name).
- Serialise `origin` in the scan JSON (`models.py`, `server.py`). `snapshot.py` drops it, because it is an allowlist and the
  origin is not needed for sharing. Add a test that an Item with an origin comes out of `snapshot()` without one.
- Privacy: `origin` is never added to the `classify`, `verify` or embed inputs. It is local display data only, so no new
  provider data goes out. Before building, record the new local read (`.skill-lock.json`, `source` only) as a **decision** in
  `docs/plan-tracker.md`, and get the user's nod, since it is a file outside the config dir.
- Tests (`tests/test_scan.py`, fixtures under `tmp_path`):
  - (a) `agents/skills/pat-one/SKILL.md` and `pat-two`, symlinked from `config/skills/`, with a lock of
    `{"skills":{"pat-one":{"source":"pat/skills","sourceUrl":"https://x.invalid/sk-ant-PLANTED"}}}`. Assert that
    `pat-one.origin == "pat/skills"`, that `pat-two.origin is None`, and that `PLANTED` and `x.invalid` are not in the scan JSON.
  - (b) A lock that is not JSON gives the warning and does not crash.
  - (c) A lock `source` of `"../../etc"` or 200 characters is dropped or capped.
  - (d) A plugin skill gets its plugin's name. A synced skill gets `claude.ai`.
  - (e) A recorded fake llm and embedder never receive the origin string.

### F2. Cluster names from shared tokens (Python, `cluster.py`)
- `_common_name(names: list[str]) -> str | None`: split each member name on `[-_ .:/]` and lowercase it. Drop stop tokens
  (`skill(s)`, `setup`, `claude`, `code`, `the`, `a`, `me`, `my`, `use`, `using`, and tokens under 3 characters except
  `ai`/`ui`). Count each token once per member. Keep the tokens found in at least `max(2, ceil(n/3))` members, order them by
  count (desc), then by first appearance, take at most 2, and join them with a space. Return None when no token qualifies.
- In `cluster()`, offline (no labelled member): `name = _common_name(...) or nearest-member name`. A labelled scan keeps the
  Haiku label first, which is unchanged.
- Origin tiebreak: when 60% or more of a cluster's members share a non-None `origin`, and there is no common token, use
  `"<origin tail> · <nearest name>"`, where the tail is the part after the last `/`, for example `skills · ask-matt`. Skip this
  if the result looks worse in screenshots. It is optional, and the reviewer decides.
- Tests (`tests/test_cluster.py`, fake embedder):
  - {`ask-pat`, `setup-pat-skills`, `loop-me`} becomes `pat`.
  - {`alpha-review`, `beta-review`, `gamma-review`, `delta`} becomes `review`.
  - No shared token falls back to the nearest member's name.
  - Labels present still win.
  - Boundary for mutmut: a token in exactly `ceil(n/3)` members qualifies, and one fewer does not.
  - Stop tokens alone give None.

### F3. Show and find the origin (frontend, the UI skill set from CLAUDE.md, demo data only)
- `model.ts`: `Item.origin?: string`, and `packs: { origin: string; members: GNode[] }[]` in `Model`, sorted by count.
- `search.ts`: add `origin` to the haystack (tier 3), with the reason `"from <origin>"`. Searching `matt`, `pocock` or
  `mattpocock` then lists all 38 skills, because the tokens `mattpocock` and `skills` come from the origin.
- Inspector: a "From" row (`origin`, or "your skills folder" when it is None) whose button runs the search for that origin.
  Hover tooltip: the kind line becomes "Skill · <cluster> · <origin tail>" when there is an origin.
- Legend: a "Packs" section listing the origins with 3 or more members and their counts. Clicking one sets `focus.matches` to
  that pack, using the existing lit-match path, so it is not a new layout and the stars stay in their meaning clusters.
- `make-demo.mjs`: give 5 invented demo skills `origin: "demo/pack"`, and 3 plugin contents their plugin name.
- `layout:check`: the pack-match highlight lights exactly the pack's members.
- Screenshots: `demo.json` and `demo-offline.json` at 1440x900 and 390x844.

## Ticket splits
1. **#52a Origin field (Python)**: F1. Needs the user's nod on reading `.skill-lock.json` (`source` only). Opus review,
   because it reads a new file and touches the snapshot allowlist.
2. **#52b Common-token cluster names (Python)**: F2. No privacy change, and it is free. Can ship before #52a, without the
   origin tiebreak.
3. **#52c Pack visibility (frontend)**: F3. Depends on #52a. Uses the UI skill set and model split from CLAUDE.md.
4. **No ticket**: a labelled scan with the key improves the wording only. Tell the user it is worth running once (about 251
   Haiku calls, then cached), but it does not fix grouping by pack.
