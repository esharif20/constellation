# Rules for any coding agent (Codex, Claude, others)

Project: Constellation, a local FastAPI + LangGraph app that scans a Claude Code setup into an explorable graph. Spec is GitHub issue #1; each ticket is a sub-issue. Read `GLOSSARY.md`, `docs/plan-tracker.md` and the ticket's plan in `docs/plans/` BEFORE writing code. Python 3.13 with **uv** only (`uv run`, `uv add`; never pip). Minimal code: no abstraction, option or feature the ticket did not ask for.

## Who works where (Codex and Claude share this repo)
- Each agent works in its own git worktree on its own branch, one ticket per agent. Never edit files in another agent's worktree or branch.
- Use the fresh clone at `~/dev/constellation` and worktrees under `~/dev/constellation-wt`; stop using the iCloud-damaged `~/Documents/projects/new` checkout.
- Keep Codex and Claude on separate tickets by default. When distinct subtasks share a ticket, use separate branches and worktrees with explicit file ownership, then integrate reviewed commits. Share a branch only for coordinated work on the same task with one writer at a time.
- Before starting a ticket, fetch origin and check ticket branches and their commits so you do not duplicate finished work. Create the next ticket's worktree from `origin/main`.

## Hard rules (privacy and cost)
- Never read, print or send the `.env` file or any secret. Never read the real `~/.claude` (tests use fixtures and temp dirs; `tests/conftest.py` redirects caches). Never read the process environment for secrets.
- Privacy invariant: only Item kinds, names and descriptions (plus short local signals) are ever sent to a provider, always after redaction (`guarded*` wrappers in `src/constellation/__init__.py`). File bodies and transcript text never leave the machine, except the opt-in `--count-bodies`. Anything that would send more needs the user's approval first.
- Cost rule: free by default. Local work first; paid calls only for new or changed Items, cached by hash of the redacted text in 0600 files; an unwritable cache is a warning, not a crash.
- Never commit real scan data, real setup names, or screenshots of a real scan. Demo data only (`docs/design/demo*.json`).
- The app never edits the user's Claude setup.

## Workflow
- Work on a branch named `codex/ticket-<n>`. After all gates pass and the tracker is updated, commit and push only that branch, then stop and report. Never push to `main`, merge, or close issues; Claude owns review and merging.
- Gates before you say done (all must pass, same as CI): `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run pytest -q` (use `--all-extras` locally), and the mutation gate `uv run mutmut run` then `uv run mutmut results` must print nothing (zero survivors). Frontend: `cd frontend && npm run lint && npm run build && npm run layout:check`.
- Tests go through the public seams (`scan()`, `render_report`, `cli.main`, the HTTP API), test-first, with fixtures; kill mutants with boundary tests.
- macOS quirk: if imports break after uv rebuilds, run `chflags nohidden .venv/lib/python3.13/site-packages/*.pth`.
- Update `docs/plan-tracker.md` (status, any deviation from the plan with the reason) in the same commit. If the right choice differs from the plan, stop and say so instead of building on it.
- Final report: branch, what changed, gate results, what you did not verify, and any provider data sent or user processes started. Claude runs an Opus review for work that sends data or starts a user's server.

## Skills note
The skill names below are Claude Code plugin names. See `docs/agents/codex-skills.md` for installed Codex equivalents and remaining gaps. Use the available skills alongside the written design docs (`docs/design/DESIGN.md` for UI tokens and type, `docs/design/graph-app.md`, `docs/plans/*`). UI work is done by Claude; Codex takes Python tickets.

## Subagent cost

When delegating, choose each subagent’s model and reasoning effort to fit task complexity, priority, and importance to the overall goal. Use cheaper models and lower effort for routine work; reserve stronger models and higher effort for difficult or critical work. Reserve Astra for critical issues or unusually complex debugging that needs deeper analysis. Use cheaper models for routine implementation, research and checks. Apply this rule to any agents those subagents deploy.

For parallel repo work, give each subagent an isolated worktree and branch with explicit file ownership. Review and validate its commit before merging it into the ticket branch; subagents must preserve other agents' changes.


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
