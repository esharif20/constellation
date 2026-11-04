# What "Ask locally" is for

Status: product note, 2026-11-04. No app code changed. Builds on `docs/plans/chat.md` (#11), `docs/design/chat-answers.md` (#51) and #48 (compare/explain). Examples use demo names only (`release-notes`, `changelog-draft`, `tune-spacing`, plus invented `pdf-tools`, `git-helper`, `repo-map`).

## 1. Purpose

Ask is the question box for the clean-up decision: "what in my setup is costing me, doing the same job twice, or never used, and what should I do about it?" Claude Code cannot answer that well from inside a session. It sees only what is loaded into its own context, cannot measure the tokens its setup adds, keeps no usage history across sessions, and cannot compare hundreds of Items against each other. Constellation has already worked all of that out locally (Context cost, Overlaps, usage counts and last-used dates, clusters, Suggestions). So Ask should answer from those saved numbers, for free and on this machine, and finish with a clear verdict plus a hand-off: a ready-to-paste instruction for Claude Code or a line added to the checklist. It is not a general chat assistant, and it never edits the setup.

## 2. Where Ask earns its place

| Question | Who answers it well | Why |
|---|---|---|
| What costs the most tokens every session? | **Constellation** | Exact counts cached per Item (`costs.py`); Claude Code cannot count its own preloaded context |
| Which hooks add text before my first prompt, and how much? | **Constellation** | `hooks.py` static bytes (tokens opt-in); Claude Code only sees what a hook output, not where it came from |
| What have I never used in the last N days? | **Constellation** | `usage.py` reads every saved transcript; a session has no history of earlier sessions |
| When did I last use `git-helper`? | **Constellation** | `Usage.last_used` from transcripts |
| Do `release-notes` and `changelog-draft` do the same job? | **Constellation** | Layered Overlaps (exact body hash, wrapper check, embeddings, verifier) across all pairs |
| Which Items does `repo-map` only wrap? | **Constellation** | Wrapper detection reads bodies locally; Claude Code would need to open every file |
| What could I remove, and how many tokens would that save? | **Constellation** | `suggest()` / `brief()` rank by known savings; unknown stays unknown |
| Which plugin brings the most Items or cost? | **Constellation** | `contains` relations plus costs; easy locally, slow by hand |
| What do I have for PDFs? | Both; Constellation better at 200+ Items | Local FTS + typo + meaning search over everything, not just what is loaded |
| How do I write a new skill? | Claude Code | General knowledge; nothing in the scan helps. **Do not build.** |
| Edit / delete / move `pdf-tools` | Claude Code | It has file tools and permission prompts; the app is read-only by design. **Do not build.** |
| Why did my hook fail? / Debug an MCP server | Claude Code | Needs running processes and logs; the scan holds shapes only. **Do not build.** |
| Summarise what `tune-spacing` says in full | Claude Code | Needs the body; the privacy invariant keeps bodies local and unsent. **Do not build.** |
| Free-form "make my setup better" advice | Neither yet | Needs a model plus the question sent out; not approved. **Do not build now.** |

## 3. The highest-value things Ask should do

All are local and free unless marked. "Missing" is what does not exist today.

1. **"Should I keep X?"** One verdict card (keep / review / could go / not enough data) from Overlap verdict, usage count, last used and always-on cost. Data: `overlaps`, `usage`, `costs`. Free. Missing: the verdict rules and card (#51 designs them; not built).
2. **"What could I remove, and what would it save?"** Ranked Suggestions with a deduplicated total ("frees about 2,140 tokens every session, plus 3 unknown"). Data: `suggest()`, `brief()`, `frees()`. Free. Missing: a chat route to Suggestions (today chat only has top costs and pairs separately) and the total line.
3. **"What does the same job as X?" / "X vs Y"** Overlap verdict and reason, side-by-side cost and usage, and which one to keep (cheaper or more used). Data: `overlaps`, `costs`, `usage`, clusters. Free. Exists in plain text (#48); missing the structured reply (#51) and the "keep which" rule when both are used.
4. **"What do I pay before I type anything?"** Session-start total: always-on costs plus hook bytes, with unknowns counted separately, and the top five contributors. Data: `costs`, `hook_weights`. Free. Missing: chat does not read `hook_weights` at all; no total exists (chat says totals are unsupported).
5. **"What have I not used lately?"** Not just never used: unused for 30+ days, sorted by cost, with the coverage caveat (transcripts get deleted). Data: `usage`, `usage_window`. Free. Missing: a "not since" filter on `last_used`; today only never-seen.
6. **"Which plugin is heaviest?"** Group cost, Item count and unused count by plugin, so one decision (disable the plugin) replaces many. Data: `contains` relations, `costs`, `usage`, `disabled`. Free. Missing: no grouping by plugin anywhere in chat; disabled plugins still count in totals (tracker #32 note).
7. **"Do it" hand-off.** Every verdict offers (a) "Add to checklist" using the existing checklist writer, and (b) "Copy instruction for Claude Code", e.g. `Disable the plugin "pdf-tools" in my user settings.json enabledPlugins; do not delete files.` Data: Item kind, name, scope id, plugin. Free. Missing: the instruction templates per kind and a copy button.
8. **"What does X expand to?"** For an MCP server, its tool list and their schema cost. Data: Expansion (#9). Free locally, but listing tools means starting the server. Missing: #9 is not built.

## 4. What Ask refuses or hands off

- **Editing, deleting, disabling, moving anything.** Ask never writes the setup. It answers with the verdict and a copyable instruction for Claude Code (item 7). Claude Code then does it under its own permission prompts.
- **Reading or summarising file bodies.** "What does X say in full" points to the Inspector's path and says "open it in Claude Code". Bodies are never shown in chat or sent anywhere.
- **Debugging runtime problems** (failed hooks, MCP errors, slow sessions): "Constellation only sees how your setup is shaped, not how it ran. Ask Claude Code: ...".
- **General coding or "write me a skill" questions:** one line saying this is outside the scan, with no fake matches.
- **Anything needing a model** (rephrasing, open advice): refused until the owner approves sending the question (see §6). No silent fallback to a provider.
- **Per-session cost history:** refused honestly. Usage records counts and last-used dates per Item, not cost per session.
- **Move to project scope:** refused for now. The scan only records scope for MCP servers (`user/`, `local/`), so it cannot advise this for other kinds.

## 5. Tickets, ranked

| # | Ticket | Size | Model? |
|---|---|---|---|
| 1 | Land #51 reply blocks and verdict card (keep / review / could go / not enough data) | M | No |
| 2 | Hand-off: "Add to checklist" and "Copy instruction for Claude Code" per kind, from existing checklist writer | S | No |
| 3 | "What could I remove" route to `suggest()` with a deduplicated savings total | S | No |
| 4 | Session-start total: chat reads `hook_weights` and always-on costs, unknowns separate | S | No |
| 5 | "Not used since N days" filter on `last_used`, ranked by cost | S | No |
| 6 | Plugin roll-up: cost, Item count, unused count per plugin; exclude disabled from totals | M | No |
| 7 | Refusal routes: edit/debug/body/general questions get one honest line and a Claude Code hand-off | S | No |
| 8 | Expansion questions after #9 (MCP tool list and schema cost) | M | No (starts the server locally; needs its own approval) |
| 9 | Optional model phrasing of headline and next step (#51 §5) | M | **Yes**: sends the redacted question, needs owner approval first |

Tickets 1 to 7 send nothing to any provider and use only data already in the saved scan. Ticket 9 is the only one that would change the privacy invariant.

## 6. Open decisions for the owner

1. **Is Ask a clean-up assistant only?** This note says yes: narrow and accurate beats broad and vague. If you want general Q&A, that needs a model (ticket 9) and a privacy decision.
2. **Hand-off format.** Copyable text instruction only, or also a `/constellation` plugin command (#12) that Claude Code can run to apply a checklist? The plugin route is smoother but means Claude Code acts on checklist text, so it must stay "propose, user approves".
3. **"Could go" threshold.** How many days unused, and how much always-on cost, before the verdict says "could go" rather than "review"? Suggest 30 days and any known cost above 0, with the transcript-deletion caveat always shown.
4. **Disabled plugins.** Should their cost drop out of totals now (they cost nothing in a session), even though the scan still counts them?
5. **Sending the question to a model.** Keep "never" for now, or approve an opt-in, off-by-default, cached, cost-shown-first mode as in #51 §5?
6. **Expansion in chat.** Starting an MCP server to list its tools is a local side effect. Allow it from a chat question, or only from an explicit Inspector click?
