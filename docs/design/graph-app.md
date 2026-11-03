# Graph app design note (ticket #8)

Static app in `src/constellation/static/` (index.html, app.js, style.css, vendored d3 7.9.0). No build step. **All styling tokens live in `style.css` `:root`**; app.js reads the `--k-*` colours, `--link*`, `--glow` and `--text` at start-up, so a restyle is a CSS edit.

## Palette
- Surface: near-black navy `#07090f` with a faint radial lift (`#0d1322`) behind the graph. Dark only for now.
- Colour encodes **kind** (skill, hook, agent, plugin, mcp server, connector): the dataviz default categorical palette, dark-mode column, assigned in a fixed order (`--k-*`). The scan has 27 clusters, far past the ~8 hues colour can carry, so clusters are expressed as spatial grouping (a weak centroid pull in the layout) and named in the inspector, not as colour.
- Links are a recessive slate; links of the focused node turn near-white. Glow is `shadowBlur` in the node's own colour.
- Text: primary `#e6edf9`, secondary `#94a1bd` (both clear 4.5:1 on the surface).

## Type
System sans stack (`--font`), so the app works offline with no font download. Small uppercase tracked labels only for HUD and inspector field names; the item name is the large element in the inspector. A restyle pass may swap in a vendored font via `--font`.

## Encoding
Node size = degree (radius 4 to 13, sqrt scale). A legend (kind and count) sits bottom-left, since colour alone must not carry identity; the inspector also prints the kind in text.

## Motion language
- Drag: the node is pinned to the pointer and the simulation is reheated (`alphaTarget 0.3`); on release the pin lifts and link springs pull it back.
- Hover: the node and its neighbours stay at full alpha, everything else eases to 0.1 (lerp per frame); connected links stay lit.
- Zoom: labels fade in between k 1.2 and 2.2; hubs (degree 4 and up) are labelled from the start; the focused node is always named, with a background-coloured halo so text stays legible over links.
- Click: 800 ms cubic in-out glide that centres the node (offset left of the inspector) and zooms to at least 1.8; the inspector slides in (260 ms). Relation rows in the inspector are buttons that glide to the other Item.
- `prefers-reduced-motion` removes CSS transitions; the canvas easing is state interpolation, not decoration.

## Why not sigma.js / react-force-graph
233 nodes on a 2D canvas with d3-force is smooth, has no build step, and keeps drag/zoom/force behaviour in well-known libraries. Revisit at several thousand nodes (WebGL via sigma.js).

## Known gaps for the next pass
Cluster regions are not drawn (only implied by layout); no keyboard navigation of nodes; no light theme; inspector shows all relations in one list; dense label overlap when focusing a large hub at high zoom.
