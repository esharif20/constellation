# Browser review 2

Demo data only (`demo-250.json`, built server, agent-browser). Screenshots: `docs/design/screenshots-review/browser-*.png`.

## Checked and fine
- Inspector at 1718x1338: "If you remove this", Your use, Tools this server offers (mocked `/api/expand` reply, long description clamps to two lines), Same cluster list, footer actions.
- Find at 1440x900: Cmd+K focuses the box, a phrase that matches no name returns description matches ("Matched: in description"), ArrowDown moves the selected option.
- Explain card: cluster share bars match their percentages; use-vs-pay bar is 67% as written.
- Elastic drag at 1440x900 after the fix: canvas pixel-identical before and after (0% diff).

## Bugs found and fixed
1. Inspector showed the previous Item's "Your use" and "If you remove this" after switching Items. Cause: four siblings in `Inspector.tsx` shared `key={item.id}` (duplicate keys break React's unmount). Fix: `yours-`, `tools-`, `removal-`, `related-` prefixes. Regression: `inspector:check` fails on duplicate sibling keys (verified red on the old code).
2. Dragged star did not return to its resting position (a 27 px jump on the first pointer move stayed as the new "home"). Cause: `elastic.grab` ran after force-graph had moved the star; now `StarMap.tsx` resets it to `__initialDragPos` first. Regression: `npm run dragrest:browser` (canvas hash before and after a drag; red without the fix).
3. Cluster name in a slightly different spot after settling. Cause: `paint.ts` re-ran `chooseSpot` every frame while stars were displaced, and its sticky `pick` bias kept the name on the alternative spot. Fix: names are held while `focus.stretch` is set (a drag or settling). Covered by the same `dragrest:browser` run (names are in the canvas).
4. 390x844 with the Brief open: "Chess openings" touched "Tide table lookups", "Moth identification" touched "Pressing flowers". Cause: name boxes had no vertical padding. Fix in `names.ts` (3 px). Three small names now wait for zoom instead of crowding. `layout:check` still passes.

## Not covered (time)
Weekly section with the history file, lens panels, Sky settings, dismiss-on-click-outside, Ask answer rows, light/dark logo and favicon. Earlier dismiss and history checks cover some of these by script.
