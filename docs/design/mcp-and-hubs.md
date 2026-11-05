# MCP sources and cluster centres: diagnosis and fix plan

Status: diagnosis only, no code changed. Written from code, tests and invented data; no real config was read.

Owner observations on the real map, zoomed out:

- (A) Few cluster centres. Many small clusters look like loose rings of stars with no hub. The Vercel cluster has a big central hub and reads well.
- (B) "It says I only have one MCP server. I feel like I have more."

## Root causes

### (B) MCP servers

What the scanner reads today (`src/constellation/claude_code.py`):

| Source | Read? | Where |
|---|---|---|
| `~/.claude.json` `mcpServers` (user scope) | yes | `_read_claude_json`, :112-119 |
| `~/.claude.json` `projects[*].mcpServers` (local scope) | yes, as `local/<n>/` | :120-128 |
| `<config>/.mcp.json` | yes, though Claude Code does not read this file | `_read_root`, :230-234 |
| plugin root `.mcp.json` | yes, but only for plugins that have a `plugin.json` | :230-234 via :345 |
| `plugin.json` `mcpServers` (inline, file, `.mcpb`/`.dxt`) | yes | `_plugin_servers`, :131-147 |
| a repo's `.mcp.json` | **only the one repo passed with `--project`** | `_read_project`, :306-310 |
| the `.mcp.json` of every other project listed in `~/.claude.json` | **no** | - |
| approval state: `enabledMcpjsonServers`, `disabledMcpjsonServers`, `enableAllProjectMcpServers` (settings and `.claude.json` projects), `disabledMcpServers` | **no**, so a server is never marked off | - |
| servers connected through claude.ai (tool names `mcp__claude_ai_<Name>__*`) | **no Item**: they appear only in transcripts | `usage.py:118-122` drops any `mcp__` name with no matching prefix |
| managed `managed-mcp.json` (system dir) | no (rare; leave out) | - |

Root causes, most likely first:

1. **claude.ai connectors are never Items.** `usage.py:85` notes that "scans no longer produce connectors; they return with transcript-seen connectors", but that return was never built: `_block` (`usage.py:118-122`) looks an `mcp__` tool name up in the prefixes built at :85-89 from scanned `mcp_server` Items. A connector has no Item, so its calls are dropped without a word. A setup with several claude.ai connectors (Gmail, Drive, Calendar and so on) and one local server shows "one MCP server".
2. **Plugins without `.claude-plugin/plugin.json` are skipped.** `_plugin_manifests` (:282-294) only finds a plugin through `plugins/cache/*/*/*/.claude-plugin/plugin.json` (:286) or an installed path that has that file (:292). Claude Code's plugin manifest is optional: it falls back to the default folders and uses the folder name as the plugin name. A plugin that only ships `.mcp.json` (plus skills) is invisible, servers included. `read_items` also calls `json.loads(manifest.read_text())` with no guard (:337), so a malformed manifest crashes the scan instead of warning.
3. **Project `.mcp.json` files are read for one repo only.** `.claude.json` lists every project the owner has opened (the same map :120-128 walks), but only `--project PATH` reads a repo's `.mcp.json` (:306-310). Team servers checked into other repos never appear.
4. **No enabled/disabled state for servers.** Plugins honour `enabledPlugins` (:332, :349-351); servers do not. A project `.mcp.json` server the owner never approved, or one in a disabled list, would show as active once (3) is fixed. This is a labelling bug rather than a counting bug, but (3) makes it matter.
5. **The user scope goes silent outside `~/.claude`.** `_claude_json` (:97-109) returns None with no warning for a config dir not named `.claude` that has no `.claude.json` inside it (:103-104). That is the right privacy rule (a copy never reads the real home), but a scan of a copied or renamed dir drops every user-scope server and says nothing. Add a warning.

### (A) Cluster centres

1. **Hub is defined as "most Relations", and most Items have none.** `n.degree` is the count of distinct Relation neighbours (`frontend/src/graph/model.ts:120-133`). Pass B sorts members by degree so the hub takes the centre slot (`frontend/src/graph/layout.ts:82-92`). The only Relations the scanner emits are `contains` from a plugin to its contents (`claude_code.py:346`) and `triggers` from an `mcp_tool` hook to a server (:255). Skills, agents and commands in `~/.claude` have degree 0. A cluster made only of them has no hub: the spiral's first slot goes to whichever id sorts first, and every star has a similar cost-derived radius (`model.ts:135`), so the cluster looks like a ring with an empty middle.
2. **Clusters are semantic, not structural.** `cluster()` (`src/constellation/cluster.py:66-93`) groups by the embedding of `name: description` only. The plugin Item is embedded like any other, so it lands in its contents' cluster only when its own description sounds like them. Vercel works because its plugin and every skill share the same vocabulary. A plugin with mixed contents ends up in one cluster, or in "Other", while its members spread over several clusters with no hub.
3. **Cross-cluster links barely pull.** A `contains` link between two clusters has distance 120 and strength 0.02 (`layout.ts:31-32`). The home forces (`layout.ts:35-36`, 0.25 to 0.35) win, so a plugin in another cluster cannot act as a centre for its contents.
4. **Nothing pulls towards the circle's centre.** The only centring force is `contain` (`layout.ts:39-46`), which only stops at the rim. The homes are spiral slots that grow outwards (`layout.ts:87`). With no hub at slot 0, nothing marks the middle.
5. **Many small clusters.** The greedy leader at `CENTRED_THRESHOLD = 0.2` (`cluster.py:14`, tuned on one scan) produces many clusters of 3-6 Items. Small clusters get no "Other" fallback (that is for < 3 Items, `model.ts:102-110`), so each one is its own hubless ring. Retuning is a separate eval job, not part of this plan.

## Fix plan: four independent Sonnet slices

Each slice can land on its own, in any order. 1 and 2 answer (B); 3 and 4 answer (A).

### Slice 1: enumerate every local MCP source, with correct on/off labels (backend)

- `_plugin_manifests`: also find plugin roots with no manifest (`plugins/cache/<mkt>/<plugin>/<version>/` holding any of `skills/`, `agents/`, `commands/`, `.mcp.json`, `hooks/hooks.json`). Use the folder name as the plugin name, with the same "installed_plugins.json names it, else newest" rule. Guard the manifest parse (:337) with a warning.
- Project `.mcp.json` for every project key in `.claude.json` `projects` whose folder exists. Reuse `_add_servers` and the `local/<n>/` index, so the path never enters an id or a warning. Mark the Items `scope="project"` and skip a repo that `--project` already read.
- Approval state: a project `.mcp.json` server counts as enabled only if `enableAllProjectMcpServers` is true or it is in `enabledMcpjsonServers` (project entry in `.claude.json`, or settings); it is disabled if it is in `disabledMcpjsonServers`. A user or local server in a project's `disabledMcpServers` is disabled. Set `disabled=True` and keep the Item on the map, as for plugins (:350-351).
- Warn when user scope is skipped for a dir not named `.claude` (:103).
- Do not read `managed-mcp.json`.

Tests (`tests/test_mcp_sources.py`, invented fixtures in `tmp_path`):

- A manifest-less plugin with `.mcp.json` gives a plugin Item, a server Item and a `contains` Relation.
- A malformed `plugin.json` gives a warning, not a crash.
- Two projects in `.claude.json`, each with a `.mcp.json`, give `local/1/` and `local/2/` servers with `scope == "project"`. The project path appears nowhere in the scan JSON.
- Approval: an unapproved project server is `disabled`, an approved one is not, and `enableAllProjectMcpServers` turns every one on.
- A planted secret in a project `.mcp.json` `env`/`headers`/`url` does not survive anywhere (extend `test_no_planted_secret_survives_anywhere_in_the_scan`). `read_secrets` must also collect env values from those project files.
- A copied config dir warns that user scope was skipped.

### Slice 2: connectors seen only in transcripts (backend and a UI note)

- In `usage.py`, gather `mcp__<server>__` prefixes that match no Item. For a `claude_ai_<Name>` prefix, add a `connector` Item (`id claude-code:connector:claude.ai/<Name>`, `origin "claude.ai"`, description "Connected through claude.ai; seen only in transcripts, so its tools and cost are unknown"). Count it like any other usage. Any other unmatched prefix gives one warning with a count only (for example "3 MCP servers were called in transcripts but are not in your config").
- Usage runs after `read_items`. The connector Items must go into the scan before clustering, or into the "Other" cluster, so they get a place on the map. Check `scan_graph.py:219` for the order.
- Inspector and Receipt: for connectors, show the honest line "MCP servers connected through claude.ai are only seen in transcripts". With `--no-usage`, or no transcripts, show that connectors are not known.
- Privacy: transcripts are read locally. Only the server segment of a tool name is kept, never inputs or outputs. Connector names go through `redact` like other names.

Tests (`tests/test_usage*.py`): an invented transcript with `mcp__claude_ai_Gmail__search` gives one connector Item with usage count 1. An unknown `mcp__foo__x` gives a count-only warning. A tool input that holds a secret is never stored. A config server and a connector with the same name stay apart.

### Slice 3: plugins join their contents' cluster (backend, small)

After `cluster()` (`cluster.py:66`), a post-pass moves each plugin Item into the cluster that holds the most of its `contains` targets, if that cluster has at least 2 of them. Ties go to the larger cluster, then by name. `scan_graph.py:219` passes the relations in. This makes every plugin a structural hub of its main cluster, as Vercel already is. Labels do not change.

Tests (`tests/test_cluster.py`): an invented plugin whose description embeds far from its three skills ends up in their cluster. A plugin with one item per cluster stays where it was. Running twice gives the same result.

### Slice 4: every cluster of 3 or more gets a visible centre (frontend)

- Rule: if a cluster's top member has degree >= 2, it is the anchor (today's behaviour, now also true for plugins thanks to Slice 3). Otherwise the cluster gets a synthetic centre. This is a layout-only point at (c.x, c.y), not an Item: it is not selectable, not searchable and not counted, and it is aria-hidden. The cluster name already says what it is.
- `layout.ts` Pass B: when there is a synthetic centre, reserve slot 0 (start `used` at the centre's area), so members ring an actual middle. Add a weak centripetal force towards (c.x, c.y) for members of hubless clusters (strength about 0.04), on top of the homes. Use d3-force `forceRadial` or the existing `contain` pattern; do not hand-roll physics.
- `paint.ts`: draw the centre as a small soft core, with spokes to members at low alpha that fade as the user zooms in (the same easing as link alpha). Use the starlight colour, not a kind colour, so it never reads as an Item. Keep the colour and legend rules in `docs/design/graph-app.md`.
- Check by screenshots of the demo data at the fitted and 1.3x zoom (agent-browser). The existing layout metrics script must still pass its slot-gap and name-count checks; re-check `K` if slot 0 is reserved.

Tests (vitest, `frontend/src/graph/layout.test.ts`): every cluster of 3 or more has either an anchor member of degree >= 2 within 1 slot of the centre, or a synthetic centre exactly at (c.x, c.y) with no member closer than its claimed area. The synthetic centre is not in `model.nodes`, search or the Receipt. Layout is deterministic (two runs, same positions).

## Privacy checks (all slices)

- Only server names, transports and hosts are ever kept, through `_shape` and `redact`. Never `env`, `headers`, `args`, url userinfo, port, path or query, and never a project path (index only). Slice 1 extends the planted-secret test to the new sources.
- Nothing new is sent to a provider. Connector Items are embedded like other Items (name and description only, after redaction), which the privacy invariant already allows.
- New warnings carry counts or fixed text only, never file text, parser messages or paths (`<project>` placeholder rule, `claude_code.py:312-313`).

## Owner verification (run in a terminal, paste back only the numbers)

Count MCP servers per source. It prints numbers only, never names or values:

```sh
python3 - <<'EOF'
import json, os, glob
h = os.path.expanduser("~")
def load(p):
    try: return json.load(open(p))
    except Exception: return None
d = load(h + "/.claude.json") or {}
ps = d.get("projects") or {}
pv = [p for p in ps.values() if isinstance(p, dict)]
print("user-scope servers:", len(d.get("mcpServers") or {}))
print("local-scope servers:", sum(len(p.get("mcpServers") or {}) for p in pv))
files = [load(os.path.join(k, ".mcp.json")) for k in ps if os.path.isfile(os.path.join(k, ".mcp.json"))]
print("projects with .mcp.json:", len(files), "servers in them:", sum(len((f or {}).get("mcpServers") or {}) for f in files))
print("approval/disable entries:", sum(len(p.get(k) or []) for p in pv for k in ("enabledMcpjsonServers", "disabledMcpjsonServers", "disabledMcpServers")))
c = h + "/.claude/plugins/cache/*/*/*/"
print("plugin version dirs:", len(glob.glob(c)), "with plugin.json:", len(glob.glob(c + ".claude-plugin/plugin.json")), "with .mcp.json:", len(glob.glob(c + ".mcp.json")))
EOF
```

Count distinct claude.ai connectors seen in transcripts. It prints one number:

```sh
grep -rhoE '"name":"mcp__claude_ai_[A-Za-z0-9_-]+__' ~/.claude/projects 2>/dev/null | sed 's/__[^_]*$//' | sort -u | wc -l
```

Count MCP Items in the last scan, by kind:

```sh
python3 -c 'import json,os,collections;d=json.load(open(os.path.expanduser("~/constellation-real.json")));print(collections.Counter(i["kind"] for i in d["items"] if i["kind"] in ("mcp_server","connector")))'
```

What the numbers will show: if user plus local plus project servers is more than the scan count, Slice 1 is confirmed. If "plugin version dirs" is more than "with plugin.json", root cause (B2) is confirmed. A connector count above 0 confirms (B1).
