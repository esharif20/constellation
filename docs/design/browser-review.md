# Browser review (demo data, packaged demo on :8799)

Method: built frontend, `constellation open demo`, agent-browser at 1440x900 and 390x844 (2x). Screenshots in `docs/design/screenshots-review/` (01-15 desktop, 20-25 phone). Invented demo data only. Nothing fixed.

## Bugs, by severity

1. **Ask answer rows collapse the Item name into a vertical column of letters (desktop and phone).** Ask "What could I remove?". Desktop: `10-ask-answer.png` shows `q u a r t e r l y - l e d g e ...` one letter per line. Phone: `24-m-ask-answer.png` breaks it into "quart / erly- / ledge" and the right-hand mono reason text ("Same job as review-diff; saves 410 tokens") overlaps the name. Cause: the `shrink-0` value span in each row can be as wide as the panel, so the `min-w-0` name column gets ~0 width. File: `frontend/src/components/Chat.tsx` ~line 187-190 (rows list; also check `Value`). Fix idea: let the value wrap or stack under the name below `sm`.
2. **"Find by what it does" is suppressed by fuzzy name near-misses.** `wantsFind` (`frontend/src/graph/find.ts`) treats any "close to ..." match as a name hit, so a long phrase gets a single weak fuzzy match and never reaches the group. "pull request review" showed cluster/description hits plus `deploy-preview` "close to" (`02-...`); "summarise my weekly sales numbers" showed only `summarise-paper` "close to" (`03-...`). Only a phrase with no near-miss ("refund customer invoices politely", `04-...`) reaches the group. In the demo the group then only shows the "needs your local ~/.claude" note, plus "Meaning-based search is off (local embedder unavailable)" which is cut off at the popover bottom without any scroll cue. Likely: `find.ts` `nameWhy`, popover height in `TopBar.tsx` ~line 213.
3. **Phone: the "Cleanup brief" pill overlaps the legend** (`20-m-rest.png`, `25-m-sky.png`): it covers the "Hook 10" entry and the legend wraps behind it. File: `frontend/src/components/Legend.tsx` / floating button in `Atlas.tsx`.
4. **Phone: "1 highlighted · from chat/search" chip sits on top of the lens switch** ("This repo" unreadable, `24-m-ask-answer.png`). On desktop the same chip overlaps the typed search text (`03`, `04`: "...ales numbers" is cut by the chip). File: `frontend/src/components/HighlightChip.tsx` / `TopBar.tsx`.
5. **Phone: cluster labels collide and clip** when the brief sheet opens (`21-m-brief.png`: "Notes and study cards" over "Reviewing pull requests", "Test-first development" over "Diagrams and visuals"/ "+72" ring tick) and "Diagrams and visuals" is cut at the right edge in `20-m-rest.png`. File: label placement in `frontend/src/graph/` (StarMap layout).
6. **Desktop: Inspector scroll content slides under the close X with no fade** (`06-inspector-scroll-600.png`: text clipped at the card top edge, X floats over it). Also the legend footer text ("overlaps (on hover)") runs under the Inspector (`05-inspector-top.png`). Files: `frontend/src/components/Inspector.tsx`, `Legend.tsx`.
7. **Nodes render under the transparent top bar text** after zoom/fly (`09`, `12`: a node sits behind "Explain my setup"), hurting legibility. File: `TopBar.tsx` background.
8. **Brief copy for an empty usage history is awkward**: "You could free 0 to 410 tokens", "About 0 to 0 a day at your pace", "Based on 0 sessions over 0 days" (`01-graph-rest.png`). Should hide the pace line when there is no history. File: `Brief.tsx`.
9. **Lens does not scope the Brief**: "This repo" dims the graph (`14`) but Brief numbers stay global. Possibly intended; worth a label.
10. **Console / network**: only one failing call at load, `GET /api/preview` 404 (`Preview.tsx` line 31) plus `favicon.ico` 404. No JS errors. (`/api/weekly` 404s in my log are my own probe; the endpoint does not exist, weekly arrives inside the brief payload.)
11. **Phone inspector sheet**: pinned action footer (Pin / Ask / Find similar / Copy) takes about a third of the 58dvh sheet, leaving about 2 rows of scrollable content (`22-m-inspector.png`). Icon-only top bar buttons (book, telescope) have no visible labels at 390px (`20-m-rest.png`).
12. Inspector "If you remove this" repeats "Still covered by" and "Does the same job" with the same row (`07`).

## Not verified
- **"This week" (Weekly) section**: the demo has one scan so `weekly` is null and the section does not render (`Brief.tsx` line 141). Not screenshotted; needs a demo with a prior scan.
- Semantic Find results (local embedder is unavailable in the demo); Ask in smarter mode (disabled).
- Phone Find group popover and phone Explain dialog.

## What looks great
- Graph at rest (`01`): distinct clusters, serif italic cluster names, readable legend, calm Milky Way backdrop; node sizing reads at a glance.
- Inspector top (`05`): clear verdict card, token meters, duplicate link drawn in the graph with a label; "If you remove this" is honest ("Nothing is changed here. Remove it by hand.").
- Explain-my-setup dialog (`11`) and Sky settings (`12`) are tidy; lens dimming (`13`, `14`) and the cluster picker (`15`) work smoothly.
- No horizontal page overflow at 390px (scrollWidth 390); phone bottom-sheet pattern for Brief/Inspector/Ask is sound.
