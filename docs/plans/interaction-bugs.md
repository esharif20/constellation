# Interaction bugs #49 (map stuck dimmed) and #50 (cluster-name clicks)

Diagnosis only, on `main` at c052a18. All reproductions ran on `docs/design/demo-250.json` (served by
`constellation open … --port 8795`, plus `vite --port 5199` proxied to it so the dev-only `window.__cx` hook exists),
headless Chrome via Playwright, viewport 1440x900. Scripts stayed in the session scratchpad (not committed);
the implementer turns them into `frontend/scripts/interaction-check.mjs` (below).

## #49 Map stays dimmed

### Who writes the dim state

`paint.ts:108-125`: the map dims whenever `f = focus.preview ?? focus.hover ?? focus.selected` or `focus.matches` is
non-null (`lit` set; everything else eases to `--fade`), or `focus.cluster` is set. Writers:

| state | written by | cleared by |
| --- | --- | --- |
| `matches` (search) | `Atlas.tsx:52` from `query` | chip x (`Atlas.tsx:53`), Esc **only while the input has focus** (`TopBar.tsx:128`), choosing a result |
| `matches` (chat) | `Atlas.tsx:197` | chip x, chat close (`Atlas.tsx:56`), chat Reset |
| `hover` | force-graph `onNodeHover`, `onNodeDrag`, touch `onNodeClick` (`StarMap.tsx:391-405`) | force-graph `onNodeHover(null)`, `onNodeDragEnd` |
| `preview` | TopBar active row (`TopBar.tsx:111-113`), ClusterCard rows (`ClusterCard.tsx:57-60,122`), Inspector rows (`Inspector.tsx:166-169`) | `mouseleave`/`blur` of that row, `select`, `close`, `openChat` |
| `selected` | `Atlas.select`, `framePair` | `close()` (Esc), background click -> `onSelect(null)` |
| `cluster` | `enter`/`leave`/popstate | Esc, Back, click outside halo, zoom out |

The zoom-fade `wake()` loop is not involved: every case below keeps a non-null owner, so the painter is right to dim.

### Root causes (three independent ones, all reproduced)

1. **Highlights have no "back to normal" path from the map.** Click on empty sky ends in `onSelect(null)`
   (`StarMap.tsx:335`) -> `Atlas.select(null)` (`Atlas.tsx:139-150`), which never touches `query` or `chatMatches`.
   Esc on the map goes to `Atlas.tsx:188`: `close()` (`Atlas.tsx:177-181`) clears only selection and preview. Once the
   search input blurs (any click on the map), its own Esc handler is gone, and the query, the chip and the dim stay.
   The author's screenshot fits this exactly: 5 lit stars, each with the match ring (`paint.ts:282`, drawn only for
   `focus.matches`), no reticle (nothing selected), clusters with no match at 0.22.
2. **Hover is never released when the pointer leaves the canvas onto chrome.** force-graph samples the pointer only
   from `pointermove` on its own container and picks the hovered node from that last position
   (`node_modules/force-graph/dist/force-graph.mjs:1298-1318, 1176-1183, 1395`). The top bar, chat, card, Inspector,
   chip and Legend are siblings above the canvas, so moving straight from a star onto them leaves `hoverObj` and
   `focus.hover` on that star. Esc does not clear `focus.hover`; only moving back over empty canvas does.
3. **Preview survives the row that set it.** ClusterCard rows set `preview` on `mouseenter` and clear on
   `mouseleave`; leaving the cluster (Esc, Back, breadcrumb) unmounts the card under a still pointer, React fires no
   `mouseleave`, and `leave()` (`Atlas.tsx:114-120`) does not clear `preview`. The same applies to `enter()` on a hop.

### Reproduction results (dimmed Items of 243 after each step, 1.5 s settle)

| sequence | step | dim | owner left behind |
| --- | --- | --- | --- |
| A search | type "idle" | 233 | matches 10, chip "10 highlighted · from search" |
| | click empty sky | **233** | query "idle", chip still shown |
| | Esc, Esc again | **233** | unchanged |
| B chat (prod server) | "What costs the most?" | chip "5 highlighted · from chat" | |
| | click empty sky | **chip still shown** | chat open, matches kept |
| C hover | hover hub `tidy0` | 227 | hover |
| | pointer jumps onto the search box | **227** | `focus.hover = tidy0` |
| | Esc | **227** | unchanged; a later click on empty sky clears it (0) |
| D card | enter cluster, hover a card row | 242 | preview `bind-compass` |
| | Esc leaves the cluster | **242** | preview kept, no card, no cluster |
| | pointer moves on the canvas | **242** | still kept; a second Esc clears it (0) |

Chat through the vite proxy returns 403 (loopback origin check), so B ran against `127.0.0.1:8795` and read the chip.

### Fix spec (Sonnet)

- `Atlas.tsx`: `close()` also calls `clearHighlight()`; `select(n)` with `n === null` also calls `clearHighlight()`
  (the only null caller is the background click). Result: one Esc after chat/cluster/selection, and any click on empty
  sky, gives the normal view. Keep the Esc order of `cluster-focus.md` 8 (search input, Brief, chat, Inspector, cluster)
  and add "then the highlight" there and in `labels.md` where the chip is described.
- `Atlas.tsx`: `enter()` and `leave()` call `setPreview(null)`.
- `StarMap.tsx`: `onPointerLeave` on the wrap div: unless a node drag is in progress (a `dragging` ref set in
  `onNodeDrag`, cleared in `onNodeDragEnd`), set `focus.hover = null`, `focus.nameHover = null`, reset the cursor,
  `hideTip()`, `wake()`. Do not try to reach into force-graph's `hoverObj`.
- Check: `frontend/scripts/interaction-check.mjs` (pattern of `chat-cluster-check.mjs`, loopback URL only, demo data)
  runs A, C, D against `npm run dev` proxied to the demo server and asserts `__cx.model.nodes.filter(n => n.a < 0.5)`
  is empty after "click empty sky" and after one Esc; B runs against the built server and asserts the chip is gone
  after click empty sky. Expected after fix: every bold row above reads 0 / no chip.
- Screenshots (demo data only): before/after for A (search, click sky) and C (hover, pointer on search box), 1440 and 390 wide.

## #50 Cluster-name click needs several clicks

### How a name click travels

`pointerup` on force-graph's container -> next rAF -> if the shadow-canvas pick under the last pointer position is a
node, `onNodeClick`, else `onBackgroundClick` (`force-graph.mjs:1331-1351`) -> `StarMap.onBackground` ->
`painter.clusterAt` (`StarMap.tsx:325-330`, `paint.ts:484`) against `c.box`/`c.hit` set in the last painted frame
(`paint.ts:449-452`). The painted box and the clickable box are the same object, eased with the drawn position, so they
never drift apart; the failures are upstream of the hit-test.

### Root causes

1. **Primary: any pointer movement between down and up drops the click.** force-graph marks a drag on the first mouse
   `pointermove` while pressed, with no threshold (`force-graph.mjs:1305-1308`), and d3-zoom's `zoom` event on a 1 px
   pan sets the same flag (`:1272`); `pointerup` then returns without any click (`:1336-1338`). Cluster names are
   background clicks, so a hand that moves a pixel while pressing (normal on a trackpad or mouse) does nothing; the
   next, stiller click works. The 5 px `DRAG_CLICK_TOLERANCE_PX` only covers node drags.
2. **Secondary: the hit box reaches over stars.** `chooseSpot` keeps only the text box (`names.ts:33`, text height
   about 15-20 px) clear of star boxes, but the hit box is at least 44 px tall (`paint.ts:450`). In 50 of 72 measured
   names a star's pointer disc (`radius*1.2 + 6 px`, `paint.ts:305-309`) lies inside the hit box; a click there picks
   the star (`onNodeClick` wins), so the doc's claim "names never sit on stars" (`cluster-focus.md:109-110`) holds for
   the text, not the box. force-graph's pick also uses a shadow canvas refreshed at most every 800 ms
   (`force-graph.mjs:762, 1375`), so right after a zoom a star that has moved away can still take the click (1 case).
3. **By design, not a bug: names are unclickable during a flight in focus** (`paint.ts:413`, hidden while flying), and
   pointerdown lands the flight (`StarMap.tsx:250`). A click aimed at a name mid-flight lands the camera and the next
   click works. Overlapping boxes resolve to the first cluster in model order (`paint.ts:484`), seen once.

### Reproduction results (click on the centre of `c.box` unless noted; success = `focus.cluster` is that cluster)

| case | success |
| --- | --- |
| still click, zoom 1.0 / 1.25 / 1.4 x fitted, 0, 300, 1200 ms after the wheel | 71/72 (1 star at 1.4x, 300 ms: stale shadow canvas) |
| **1 px move between down and up, fitted view, settled** | **0/8** (nothing happens) |
| random point on the name's text, fitted view | 23/24 (1 went to an overlapping neighbour's name) |
| hop: in focus, another name 1800 ms after entering | 8/8 |
| hop: 400 ms after entering (still flying) | 0/8, no name is drawn or hittable |
| 1 px move on a star (comparison) | 3/4 selected |

### Fix spec (Sonnet)

- `StarMap.tsx`, in the existing wheel/pointerdown effect (`:222-253`): own the name click. On `pointerdown` store
  `{x, y, name: painter.clusterAt(x, y)}`; on `pointerup` (capture, same element), if `name` is set, the pointer moved
  at most 6 px (10 on `pointer: coarse`, the drag tolerance force-graph uses for nodes is 5), and `clusterAt` at the up
  point is the same cluster, set a `nameClick` ref and call `onCluster(name)`. `onBackground` and `onNodeClick`
  return early (and clear the ref) when `nameClick` is set, so the name wins over a star in its box and the enter
  never runs twice (a double `enter` would push two history entries). This fixes causes 1 and 2 together; leave
  force-graph, `chooseSpot` and the 44 px box alone. A real drag (> tolerance) still pans and does not enter.
- Optional, same change: `clusterAt` picks the hit box whose centre is nearest the point instead of the first.
- Check, in the same `interaction-check.mjs`: clicks on every hittable name at 1.0, 1.25, 1.4x, still and with a 1 px
  move, plus random text points; expect 100% (before: 0/8 with movement). Plus: a 20 px drag starting on a name pans
  and does not enter; a still click on a star outside any name box still selects it. Run `npm run layout:check` too.
- Screenshots: a name with the pointer cursor at 1.0x and 1.4x, and the entered cluster after a 1 px-jitter click.

## Related risks

- Clearing the highlight on any empty-sky click changes the search contract ("every match stays lit while
  typing"): a click on the map while the query is still wanted now drops it. The ticket asks for exactly this; record
  it in `docs/plan-tracker.md` as a decision and update `cluster-focus.md` 8 (Esc order, exit rules).
- After the `pointerleave` fix, force-graph's own `hoverObj` is still the old star: returning straight onto that same
  star fires no `onNodeHover`, so it is not lit until the pointer leaves it once. Acceptable; note it in the check.
- A name click handled on `pointerup` runs before force-graph's rAF click; any future handler that also reads
  `clusterAt` must check `nameClick` first.
- Chat checks cannot go through the vite proxy (403); keep the chat assertion on the built server.
