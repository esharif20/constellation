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
- `design-taste-frontend` (taste-skill, user-installed 2026-11-04): anti-slop art direction and a real-browser inspector with a look-and-fix loop; use it for the app screens review (#23-ish) and the landing page. It fetches public stock images only through its own `assets.mjs`; do not add fetched assets to the app.
- `nateherk-design:scroll-craft`: ONLY the public landing page (ticket #15). Never inside the app (it may be consulted for easing and inertia guidance only).
- `vercel-plugin:agent-browser-verify` / `agent-browser`: screenshot the running app to check look and feel.
- `/tdd`, `/implement`, `/code-review` (Matt Pocock): drive and review each ticket; UI feel is checked by eye and screenshots, not unit tests.

## Model routing

Main session stays on Sonnet. Switching the session model with `/model` re-sends the whole context uncached (prompt caches are per model), so do not switch mid-session.

Send high-priority thinking to an Opus 5.5 subagent (`Agent` with `model: "opus"`) instead: planning, architecture decisions, debugging a hard failure, and diagnosing a fix that is not obvious. Give it a short self-contained brief (goal, relevant file paths, what was already tried, the seams from this file), not the conversation. It returns a written plan or diagnosis; save a plan to `docs/plans/` when it will be executed later.

Sonnet then executes a defined plan: writing the code, tests and routine fixes. Haiku is fine for mechanical lookups. Opus reviews (`/code-review`) at ticket end when the change touches redaction or other security-sensitive code.

### UI work: skills and model split

Every UI task loads the full set above before writing code, not just one: `/prototype` for feel, `frontend-design:frontend-design`, `ui-ux-pro-max`, `dataviz`, plus `shadcn` and `vercel-plugin:react-best-practices` if React is used, and `vercel-plugin:agent-browser` to screenshot and look at the result. For graph and motion, prefer well-known libraries (d3-force / d3-zoom / d3-drag, or sigma.js / react-force-graph for large graphs; Motion or CSS transitions for UI motion) over hand-rolled physics. `scroll-craft` stays landing-page only (#15).

Split by model: an Opus 5.5 subagent makes the first design (layout, palette, typography, motion language, a written design note under `docs/design/`), then a Sonnet agent refines it: spacing, states, polish, responsiveness, bug fixes, checked with screenshots. Brief each with the design note and the screenshots, not the conversation.

## Plan alignment (every ticket)

The approved plan is `~/.claude/plans/pasted-content-id-d61b-i-think-modular-fog.md`; its status is mirrored in `docs/plan-tracker.md`.

- Before starting a ticket, read the decisions that touch it (`docs/plan-tracker.md`, then the plan) and put the relevant ones into every agent brief. Briefs must name the required technology, not only the goal.
- If the right choice differs from the plan, stop and say so: record it as a **deviation** in the tracker with the reason, and get the user's approval before building on it.
- At the end of every ticket, update `docs/plan-tracker.md` (status, deviations, new decisions) in the same commit, and reflect it in the ticket's closing comment.
- A reviewer checks the diff against the tracker: wrong stack or silent drift is a finding.

## Cost rule

Free by default, paid only for new or changed Items. A scan of an unchanged setup should make zero paid calls.

- Every paid provider call (labels, verifier, token counts) is cached by the content hash of the redacted text it would send, in a private (0600) file; an unwritable cache is a warning, never a crash.
- Local work (hashing, wrapper checks, embeddings, clustering) always runs first and is always free; a model is called only for what local work cannot decide.
- Every real run prints a call-count and cost estimate first; dry runs show exactly what would be sent.
- Offline mode (no key, or `--offline`) must still produce a useful Constellation.
- Plan for at most a few hundred Items per user, not thousands; do not add complexity for scale beyond that.

## Privacy invariant

Only Item kinds, names and descriptions (plus short local signals and, later, tool schemas) are ever sent to a provider, always after redaction. File bodies are read locally and never sent, with one opt-in exception: `constellation scan --count-bodies` sends each skill's redacted body to Anthropic's token-counting endpoint to measure on-use cost. Without the flag, on-use cost is reported as unknown. Any new feature that would send more than this needs the user's explicit approval first.

### Staged skills (not loaded, to keep context cost at zero)

`~/.claude/skill-library/` holds vetted third-party material that is NOT in the skills folder, so it costs nothing until enabled: `threejs-skills` (13 markdown skills), `img2threejs` (heavy image-to-Three.js pipeline), `awesome-design-md` (84 reference DESIGN.md files; see the design-reference ticket). Enable by copying the needed folders into the project `.claude/skills/` only when a ticket needs them (landing page #15). Vet any new third-party skill first: read its scripts, check network and exec calls, scan for instruction-injection, and never run its installer blind.
## Money and disk rules (owner has no budget to add)
- GitHub Actions minutes cost money on this private repo and the owner will not add budget. CI runs only on pushes to `main` (docs-only pushes skip it) or by hand; the slow mutation gate (about an hour) runs only by manual dispatch. Pushing a branch triggers nothing, so push branches freely, but push `main` rarely: batch merges, run every gate locally first, then one push. Never push `main` per slice, never push a failing tree to "see what CI says", and never re-run CI to retry a flake. A newer push cancels the older run.
- The mutation gate is enforced locally: run `mutmut` only on the modules you changed, one run at a time (delete `mutants/` before and after), zero survivors, and say so in the report. Before a manual full run, ask the owner.
- Only one mutmut run may exist on this machine at a time (several agents work in parallel and the machine overloads). Take the lock first: `until mkdir /tmp/constellation-mutmut.lock 2>/dev/null; do sleep 20; done` (use Monitor to wait if sleep is blocked), run, then `rmdir /tmp/constellation-mutmut.lock` even when the run fails or you stop.
- Disk is small (the data volume was at 95% full). Do not create extra worktrees casually: each one with its own `.venv` and `node_modules` costs hundreds of MB. Reuse one worktree per task, remove it (`git worktree remove`) as soon as its branch is merged, and delete `mutants/`, `.pytest_cache`, build output and screenshots you do not commit. Never download large models, datasets or images into the repo or caches without asking. Check `df -h /System/Volumes/Data` before big installs and stop if less than 10 GB is free.
- Never run anything that spends money (paid model calls, cloud services, new paid plans) without asking first.

