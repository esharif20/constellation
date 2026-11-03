## Agent skills

### Issue tracker

GitHub Issues on esharif20/constellation (via `gh`). See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-label vocabulary. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: root `GLOSSARY.md` + `docs/adr/`. See `docs/agents/domain.md`.

## Frontend skills

Use these for any UI work, in this order of intent:

- `/prototype` (Matt Pocock): throwaway experiments to settle UI feel before building it, especially the graph physics (drag spring, hover fade, zoom labels).
- `frontend-design:frontend-design`: aesthetic direction and typography; avoid templated defaults.
- `ui-ux-pro-max`: palettes, font pairings, UX guidelines, spacing and interaction states.
- `shadcn` (and `vercel-plugin:shadcn`): add and compose shadcn/ui components for the chat panel and inspector.
- `vercel-plugin:react-best-practices`: React performance and structure.
- `dataviz`: colour and encoding rules for the node size, clusters and Overlap links.
- `nateherk-design:scroll-craft`: ONLY the public landing page (ticket #15). Never inside the app.
- `vercel-plugin:agent-browser-verify` / `agent-browser`: screenshot the running app to check look and feel.
- `/tdd`, `/implement`, `/code-review` (Matt Pocock): drive and review each ticket; UI feel is checked by eye and screenshots, not unit tests.
