# Codex skills for Constellation

Audited 2026-11-04 against the skill names documented in `AGENTS.md`, the installed Codex/shared skill directories, and the original public repositories. This audit did not inspect the real Claude configuration, transcripts, `.env`, or credential values. It establishes availability of the documented skills, rather than an inventory of every plugin installed in Claude.

Codex uses the upstream `SKILL.md` packages directly; Claude plugin hooks and automatic skill injection are separate features. The repository's privacy rules and written design decisions still govern every ticket. Installing these skills does not change the current assignment of UI work to Claude.

| Documented Claude skill | Codex skill | Result and original source |
|---|---|---|
| `/prototype` | `prototype` | Already installed in the shared skills directory; [Matt Pocock](https://github.com/mattpocock/skills/tree/main/skills/engineering/prototype). |
| `/tdd` | `tdd` | Already installed; [Matt Pocock](https://github.com/mattpocock/skills/tree/main/skills/engineering/tdd). |
| `/implement` | `implement` | Already installed; [Matt Pocock](https://github.com/mattpocock/skills/tree/main/skills/engineering/implement). |
| `/code-review` | `code-review` | Already installed; [Matt Pocock](https://github.com/mattpocock/skills/tree/main/skills/engineering/code-review). |
| `shadcn`, `vercel-plugin:shadcn` | `shadcn` | Already installed from [shadcn/ui](https://github.com/shadcn-ui/ui/tree/main/skills/shadcn); one copy covers component work. |
| `frontend-design:frontend-design` | `frontend-design` | Installed from [Anthropic](https://github.com/anthropics/skills/tree/ca45fc496a3436251f191354091d557da31c15b5/skills/frontend-design). |
| `vercel-plugin:react-best-practices` | `vercel-react-best-practices` | Installed from [Vercel](https://github.com/vercel-labs/agent-skills/tree/1a2c79d4e6c4a2283dc2c614b6538cbe1ed5ca62/skills/react-best-practices). |
| `ui-ux-pro-max` | `ui-ux-pro-max` | Installed from [the original project](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill/tree/dd9a1b4cf9f67ca2e326f646d93e101b2778db30/.claude/skills/ui-ux-pro-max). Local command paths were adapted for Codex and `uv run --all-extras`. |
| `nateherk-design:scroll-craft` | `scroll-craft` | Installed from [Nate Herk](https://github.com/nateherkai/scroll-craft/tree/75d81f74e83692add18cd7a8a8e078b8a887a579/plugins/nateherk-design/skills/scroll-craft). Use only for ticket #15's public landing page. |
| `vercel-plugin:agent-browser-verify`, `agent-browser` | `agent-browser` | Installed [Vercel's current browser skill](https://github.com/vercel-labs/agent-browser/tree/6682da310c75bed8af340b39cc10b7f71bded155/skills/agent-browser). The exact `agent-browser-verify` skill was [removed upstream](https://github.com/vercel/vercel-plugin/commit/7a73b567913d04fc7704d3a5c0b822aa26e072ee); no stale copy was installed. |
| `dataviz` | Unresolved | No authoritative public source was identified for the palette validator described in `docs/design/graph-app.md`. Other similarly named skills are different packages. Continue using the written graph design rules until the original source is supplied. |

The five new packages live in `~/.codex/skills/`; the existing packages remain in `~/.agents/skills/`. They become discoverable on the next Codex turn. Reinstalling an upstream package may overwrite the local adaptations described here.

The installed scroll-craft instructions explicitly preserve Constellation's privacy and cost rules: its `doctor.mjs` and `kie.mjs` helpers inspect credentials or `.env` and must not run in this repository. No helper, plugin hook, paid image call, or Claude configuration edit was executed during installation.

Verified: all five installed packages contain `SKILL.md`; UI/UX Pro Max's local `keyboard focus modal` search returned its focus-state guidance. Browser runtime verification remains open: `agent-browser` was not on the shell path, and no browser binary or global CLI package was installed. Before browser work, provision the CLI/browser through its upstream instructions, then load `agent-browser skills get core`. Scroll-craft rendering and asset generation were not run.

Follow-up verification (2026-11-04, #25 and #11): the installed `agent-browser` CLI and Chromium runtime now work. Demo-only browser checks ran against the real local Python API, including responsive chat selection and graph actions; no real scan was loaded. The original dataviz package, scroll-craft rendering and asset generation remain unverified.
