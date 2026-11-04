# Graph references (input to ticket #23, taste review)

Inspiration only. No assets, text or screenshots are copied or committed. Every claim below is paraphrased from the cited page or search result; where a source was thin it says so. Our baseline is `docs/design/graph-app.md`: dark star atlas, ~250 nodes, 36 clusters, cost-sized nodes, Overlap links, cluster names as spaced italic serif lettering, hover dims the rest to alpha 0.1, semantic zoom relative to the fitted view.

Method note: the research tooling was partly broken (context-mode sandbox failed; several product sites render client-side), so most facts come from official docs found via search, not from hands-on use of each product. Anything marked "unverified" should be checked in a real browser during #23.

## 1. Obsidian graph view

Sources: https://help.obsidian.md/plugins/graph , https://obsidian.md/help/plugins/graph

- Does well: a "text fade threshold" setting controls how transparent every node name is, so labels thin out with zoom instead of being on/off. Groups are defined by a search term plus a colour, so colour is user-driven rather than fixed. Local graph has a depth slider (each level adds notes connected to the previous level). Animate plays a time-lapse of the graph being built. Filters cover tags, orphans, existing files.
- Steal: a single "label density" control (fade threshold) exposed to the user. Our semantic zoom is fixed in `FEEL`; one slider in the legend popover costs little.

## 2. Cosmograph (cosmos.gl)

Sources: https://cosmograph.app/docs-widget/configuration/ , https://next.cosmograph.app/docs-lib/api/interfaces/CosmographConfig/

- Does well: GPU-rendered at large scale. Labels default to the most-connected nodes, with an override to force labels for chosen nodes. A single focused node gets a ring (white by default). Selection greys out unselected points and links through two separate opacity settings (points and links tuned independently). A timeline and histograms let you cross-select nodes by attribute, plus rectangular selection.
- Steal: separate dim levels for nodes and for edges. Today everything unfocused goes to 0.1; edges could drop to ~0.04 while stars stay ~0.12 so constellations still read as a sky.

## 3. Connected Papers

Sources: https://nesslabs.com/connected-papers , https://libguides.hkust.edu.hk/citation-chaining/connected-papers , https://www.wur.nl/en/show/Search-tip-20-Connected-papers.htm (colour/size details unverified, search found no node-size statement)

- Does well: position means similarity, not citations; colour shows age; lines mark stronger similarity. Two named side lists, "prior works" and "derivative works", turn the graph into a reading list. Built around one seed paper, so the first screen has an obvious centre.
- Steal: a ranked side list beside the graph. For us: "Top cost" and "Most overlap" lists in the inspector or legend that click through to the star. Also the explicit sentence that says what distance means (a one-line caption for what Overlap links and cluster proximity encode).

## 4. Litmaps

Sources: https://medium.com/litmaps/guide-to-litmaps-visualisations-95a9bc2cc9de , https://docs.litmaps.com/en/articles/9181490-use-and-edit-litmaps-visualization , https://libguides.hkust.edu.hk/citation-chaining/litmaps

- Does well: map has real axes (default x publication year, y citations; sources disagree on default node size, so check). Clicking an axis label switches what it means; a node-size legend at bottom left lets you change size encoding. "More like this" grows the same map.
- Steal: a click-to-change encoding control sitting on the legend: size by on-use cost, always-on cost, or degree. Keeps one canvas, three readings. (Respect the privacy rule: on-use cost stays "unknown" without `--count-bodies`.)

## 5. InfraNodus

Sources: https://infranodus.com/about/how-it-works , https://infranodus.com/tutorial/create-your-first-knowledge-graph , https://infranodus.com/use-case/network-analysis-visualization

- Does well: node size = betweenness centrality (bridges, not hubs); colour = Louvain cluster; Force Atlas layout. It flags "structural gaps", the empty space between two clusters that could be better connected. Label rules not described in the sources found (unverified).
- Steal: highlight bridge Items (high betweenness) as a different glyph glow, and optionally name the biggest gap between two constellations. Fits "Overlap" semantics: two clusters with many overlap links are the interesting story.

## 6. Kumu

Sources: https://docs.kumu.io/guides/focus , https://docs.kumu.io/guides/filter , https://docs.kumu.io/guides/views , https://docs.kumu.io/guides/decorate/data-driven-decorations

- Does well: separates Decorate (size, colour, shape from data) from Filter (hide by profile data) from Focus (hide the rest, step outward by degree). A "view" bundles all three and can be saved and switched by readers.
- Steal: focus-by-degree stepping. Select an Item, press a key to widen from 1 hop to 2 hops. We already have arrow stepping and neighbour lighting; adding "[ / ]" for hop depth is small. Saved named views are probably out of scope for a few hundred Items.

## 7. Neo4j Bloom

Sources: https://neo4j.com/docs/graph-intelligence-microsoft-fabric/user-guide/explore/ , https://neo4j.com/blog/developer/integrating-graph-data-visualizations-no-code-workflows-bloom-2-0/ (the "inspector" and exact legend behaviour were not confirmed by the sources found)

- Does well: legend is not a key but a control panel: it lists each category and relationship type with its style, and edits size, colour and caption there; supports rule-based styling. Search phrases are saved plain-language queries. The scene contains only what you searched or expanded, not the whole database.
- Steal: make our legend interactive, so clicking a kind glyph toggles that kind's visibility (a filter). Cheap and answers "show me only hooks".

## 8. Gephi Lite

Sources: https://github.com/gephi/gephi-lite/issues/113 , https://gephi.org/desktop (UI strings seen via search; no official docs page was found, so this is the weakest entry)

- Does well: Appearance panel has Partition (categorical colour) and Ranking (continuous size) modes with explicit fallback size for missing values. Filters stack. A legend generator exists.
- Steal: an explicit "no value" treatment. We already style unknown cost; make the fallback visible in the legend ("hollow = cost unknown") so it reads as deliberate, not broken.

## 9. Linkurious Ogma

Sources: https://doc.linkurious.com/ogma/latest/ , https://doc.linkurious.com/ogma/4.0

- Does well: WebGL first with canvas/SVG fallbacks; style rules behave like CSS and react to data and topology changes; "transformations" filter and group nodes and edges, turning attributes into entities. Neighbour expansion not confirmed by sources found.
- Steal: node grouping as collapse. At fit zoom, render each of 36 clusters as one nebula "super star" with a count, expanding on zoom. Heavier than the others, and partly overlaps the current halo plus name treatment.

## 10. Observable and d3 community notebooks

Sources: https://observablehq.com/@twotau/research-networks , https://observablehq.com/@mkane2/debtors-network-with-zoom-connected-nodes-on-click-and-tool (community notebooks, not the official d3 gallery)

- Do well: the baseline pattern we already use: hover adds a class to the node, its edges and its neighbours; the rest fades. Zoom applied to a container transform.
- Steal: nothing new; confirms our hover model is standard. Treat as a floor, not a source of ideas.

## 11. Awwwards / One Page Love

Source: search at https://www.awwwards.com found no Site of the Day that was a true network graph (collective[i], https://awwwards.com/sites/collective-i , was the closest and is only a loose match). No claim made. Library names that surfaced for follow-up: sigma.js, reagraph, cosmos.gl. The design-taste skill's landing-page run (#15) is the better place to look for award-style motion.

## Ranked ideas (value for effort)

| # | Idea | From | Effort | Value | Conflicts with star atlas? |
|---|---|---|---|---|---|
| 1 | Interactive legend: click a kind glyph to filter that kind | Bloom | S | High | No. Reuses existing `.glyph` marks |
| 2 | Separate dim levels: edges dimmer than stars when unfocused | Cosmograph | S | High | No. Strengthens "sky stays visible" |
| 3 | Visible "cost unknown" key (hollow star) in legend | Gephi Lite | S | Med-High | No |
| 4 | Size-by switch (on-use cost, always-on cost, degree) on the legend | Litmaps | M | High | No, but keep default as cost |
| 5 | Ranked side lists: "Top cost", "Most overlap", click to fly to star | Connected Papers | M | High | Mild: adds list chrome; keep it a quiet glass panel |
| 6 | Hop depth `[` / `]` to widen the lit neighbourhood from 1 to 2 hops | Kumu, Obsidian local graph | S-M | Med | No |
| 7 | Label density slider (fade threshold) in a popover | Obsidian | S | Med | Mild: a slider adds a utilitarian control to a sky |
| 8 | Bridge Items glow plus named "gap" between two constellations | InfraNodus | M-L | Med-High, novel | No, it fits the atlas; needs betweenness computed locally (free under the cost rule) |

Not ranked, deliberately skipped:

- Cluster collapse into super-stars (Ogma): large change, and the halo plus lettering already do this job at 36 clusters.
- Time-lapse animate (Obsidian): our data has no meaningful time axis; also conflicts with the single-orchestrated-moment motion rule.
- Per-cluster colour (InfraNodus, Obsidian groups): conflicts with the chosen direction. Our note already ruled out per-cluster colour (27+ clusters exceed what colour can encode; kind uses colour).
- Real axes (Litmaps): conflicts with a free-form constellation layout; positions are packed clusters, not coordinates.
- Saved named views (Kumu): over-built for a few hundred Items.

## Cross-cutting observations

- Almost every product separates three jobs: encode (size/colour), filter (hide), focus (dim). We do encode and focus; filter is the gap (ideas 1 and 6).
- Legends in the better products are controls, not decoration (Bloom, Litmaps, Gephi Lite). Ours is read-only.
- Label policy in these products is degree-first with a user knob (Cosmograph default, Obsidian threshold). Ours is priority-greedy with collision skip, which is at least as good; only the knob is missing.
- Empty and loading states were not documented by any source found; no evidence-backed idea there. Judge ours by eye in #23.
