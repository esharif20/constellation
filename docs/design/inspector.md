# Inspector: from a label to a decision

Status: design note for #73, 2026-11-04. No app code changed. Builds on `DESIGN.md` (tokens, badge, stat card, panel), `graph-app.md` (glyphs, non-modal panel, phone sheet), `chat-answers.md` §verdicts and `ask-purpose.md` §3, §6. Data from `plans/whatif.md` (#69), `per-project.md`, `lenses.md`, `history.md` is used only where it already exists or is named as a later slot.

**Problem.** Clicking a star shows the kind, the name and one block of description. The numbers that matter for clean-up (cost, use, overlaps) sit below it in grey tables. The owner wants the panel to answer "what is this, is it worth keeping, what else is like it, what do I do" at a glance, calmly.

**Rules.** Local signals only; no provider call, nothing sent. Unknown is the word "unknown" (italic text-3), never 0 and never an empty bar. A control for an unbuilt feature is hidden, not shown disabled. Only existing tokens from `index.css` (dark theme only; there is no light theme). Every colour also has a word or icon.

## 1. Layout (380px panel, top to bottom)

1. **Header.** Row 1: kind chip (glyph + kind name, `caption` 500 text-3, as now) then, when present, `from {origin}` and a scope badge (`Global` / `Project · {label}`; MCP `user/` = Global, `local/<n>/` = Project). Row 2: name in Newsreader 30/26px. Row 3: the purpose label (`item.label`) in text-2, one line, as now.
2. **Verdict banner.** One row, `--radius-lg`, 10% tint of its tone with a 1px 30% border of the same tone, icon + verdict word (Inter 13/600 in the tone colour) + the `why` (Inter 13 text, max 90 chars). See §2.
3. **Facts.** A two-column grid of stat chips (`bg-surface-2`, 1px line-1, radius-lg, px-3 py-2): label in `caption` text-3, value in `mono` 13 text.
   - **Always-on**: `1,240 tokens` + a 4px mini-bar (track `--line-1`, fill `--indigo-bright`) scaled to `model.costRef` (the p95; clamp at full and add `+` when above) and a caption `top 8%` (rank among Items with known cost). Unknown: word only, no track.
   - **On use**: same, no rank; unknown adds the hint `Run constellation scan --count-bodies to measure.` (as today; hooks say `Known only when it runs.`).
   - **Usage**: `14 uses · last 2 Oct`; `Never seen in 212 transcripts`; `Not tracked for hooks` / `for plugins`; `No transcripts scanned`. Caption under the grid: `Transcripts 3 Sep to 4 Nov`.
   - **Cluster**: italic Newsreader name (as now). It becomes a button only if an `onCluster` prop is passed.
   - **Overlaps** (full width, only when any): one chip per partner, max 3 then `+2 more`: partner glyph + name + verdict badge (`duplicate` / `wraps` / `wrapped by` / `overlaps`) with an `--overlap` 1px border. Click calls `onSelect` (the camera already glides; reduced motion snaps); hover/focus calls `onPreview`. The reason is the button `title` and is shown in full in Related.
4. **About.** Two short blocks with `section` headings text-3: **What it does** and **When it triggers** (§3). Each clamps to 3 lines with a `Show more` text button (`aria-expanded`). Then the source path in mono 12 text-3, as now.
5. **Kind details** (§4), one block, only for kinds that have extra facts.
6. **Related.** Groups, each with heading + count, rows as the existing `ItemButton` (min-h 40): `Does the same job` / `Wraps` / `Wrapped by` / `Overlaps with` (with reason line, as now), `Contains` / `Contained in` / `Triggers` (existing Relation groups), `In the same plugin` (siblings via the parent's `contains`), `Same cluster` (other members, sorted by known always-on cost then name, excluding anyone listed above). Max 5 per group, then `Show all 23`. Empty: `No Relations to other Items.`
7. **Actions** (§5). Desktop: after Related. Phone: sticky footer of the sheet.

## 2. Verdict (local, first match wins)

Same wording as `chat-answers.md` so chat and panel agree; text says "could", never "should delete".

| Signal | Label | Tone token | Why (example) |
|---|---|---|---|
| `disabled` | Switched off | text-3 on surface-2 | `Disabled in enabledPlugins; the scan still counts its cost.` |
| `duplicate` Overlap | Keep one | `--destructive` | `Does the same job as changelog-draft.` |
| `wrapper` Overlap (this is the wrapper) | Keep the wrapped one | `--warn` | `Only calls release-notes.` |
| tracked, count 0, known always-on > 0 | Could go | `--destructive` | `Not seen in 61 days of sessions; costs 840 tokens every session.` |
| tracked, last used 30+ days before `usage_window.last`, known always-on > 0 | Review | `--warn` | `Last used 12 Aug; costs 840 tokens every session.` |
| tracked, count > 0 | Keep | `--indigo-bright` | `Used 14 times in 61 days.` |
| otherwise (hooks, plugins, no usage read) | Not enough data | text-3 on surface-2 | `Usage is not tracked for hooks.` |

The 30-day line is the owner's open decision (`ask-purpose.md` §6.3); keep it one constant. A plugin with no Overlap rolls up its contents: `Could go` if every tracked child is never seen and known cost > 0, else not enough data. Icons (lucide): Check, Eye, CircleMinus, Copy (duplicate), CircleHelp, Power (off). Add a caption under the banner when count-based: `Transcripts can be deleted, so "never seen" is a hint.`

## 3. Splitting the description

Pure function `splitDescription(text)` (new `lib/describe.ts`, with an assert self-check): collapse whitespace, split into sentences (not on `e.g.`, URLs or decimals). A sentence is a **trigger** if it starts with `Use (this )?(when|whenever|for|if)`, `Trigger(s|ed)? (when|on)`, `Invoke when`, `Activates (on|when)`, `TRIGGER` or `Triggers on`, and so are the sentences after it until one that does not mention a trigger word. The rest is **What it does**. If What it does is empty, use the purpose label, else hide that block. If nothing matches, the whole text is What it does and the trigger block is hidden. Hooks and MCP servers skip the split (their description is a command or shape, §4). No description: `No description.`

## 4. Per kind

- **Hook.** `Event` (part of the name before `:`), `Matcher` (after it, or `all tools`), `Runs before you type` for SessionStart/UserPromptSubmit, `Can block` for PreToolUse, PermissionRequest, UserPromptSubmit, Stop, SubagentStop (copy: `This event lets a hook stop the action.`), Session-start weight (`3,200 bytes`, tokens or `tokens not counted`), the command in mono 12, 2-line clamp, and `Calls {server}` from the `triggers` Relation.
- **MCP server / connector.** `Shape` = the description (transport and host or command name only), `Scope` badge, usage, and later the tool list (#9, hidden until built).
- **Plugin.** `Contains` counts by kind with glyphs (`12 skills · 3 hooks · 1 agent`), `Total always-on` of its contents (`4,100 tokens + 3 unknown`), and `5 of 15 never seen`. A stacked bar is not used: one total plus the count reads faster.
- **Command.** On-use cost and origin; no extra block.
- **Per project** (when `usage_by_project` reaches the frontend, `per-project.md`): a row `9 in dev-constellation, 1 in another`.

## 5. Actions

One row of `outline` buttons, h-10 (h-11 on phones), wrapping to two lines; each hidden when its feature or prop is missing.
- **Copy instruction** (always): copies a kind template, e.g. skill `Remove the skill "release-notes" from my setup; show me the file first and do not delete anything else.`, plugin `Disable the plugin "pdf-tools" in my user settings.json enabledPlugins; do not delete files.`, hook `Remove the {Event} hook that runs "{command name}" from my settings; show me the diff first.`, MCP `Remove the MCP server "{name}" from {scope} config; do not touch other servers.` Live region: `Copied`. Templates in new `lib/instruction.ts`.
- **Add to checklist** (#53): only when the Item has a Brief row and the checklist writer is available; after success `Added to checklist` (disabled), failure inline with icon.
- **Remove in what-if / Put back** (#69): only while what-if is on, `aria-pressed`, plugin adds `Removes 4 Items` (exact copy from `whatif.md`).
- **Compare with…**: opens Chat with `Compare {name} with ` prefilled (#48), only if an `onAsk` prop is passed.

## 6. States

- **Loading** (lazy chunk or brief fetch): header renders at once from the node; facts show a 1-line `bg-surface-3` shimmer only after 150ms; no layout jump (fixed chip heights).
- **Unknown:** the word, never 0, never an empty bar. **Offline file:** facts still render; label row hidden when empty.
- **Disabled Item:** header gets a `Switched off` badge, the name in text-2, mini-bar fill `--text-4`, verdict "Switched off", actions keep Copy instruction (`Re-enable…` template is not built: hide).
- **Long names/descriptions:** `overflow-wrap:anywhere`; clamps as above.

## 7. Phone (390px)

Bottom sheet stays 58dvh with the grab bar. In that first view: kind chip, name (26px), verdict banner and the first row of facts must be visible without scrolling. Facts become one column under 360px. Actions are a sticky footer inside the sheet (`bg` = panel glass, top border line-1, `pb-[env(safe-area-inset-bottom)]`), at most two buttons per row. Every target 44px. `Back to {cluster}` stays as now.

## 8. Keyboard, a11y, motion

- Focus goes to the name heading on open (exists); Tab order: close, header, overlap chips, Show more, kind details, Related rows, actions. Escape closes (exists). All buttons get the ring (`--indigo-bright`).
- Verdict banner is plain content (`<p>` with a visually hidden `Verdict:` prefix); the existing selection live region adds the verdict word: `Selected release-notes, Keep one`.
- Mini-bars are `role="img"` with `aria-label="Always-on 1,240 tokens, top 8% of known costs"`; chips are a `<dl>`.
- Motion: sections fade in 140ms `--ease-out`, bars grow 200ms on open. Under `prefers-reduced-motion` both are off (snap). Nothing loops.

**Contrast (on panel `#0f1011` and the 10% tint of each tone, computed):** indigo-bright 6.6 / 5.9, warn 11.7 / 9.7, destructive 7.6 / 6.6, overlap 7.1 / 6.3, text-3 5.9 / 5.2; body text on any tint 14.6+. Bars vs track: indigo-bright 5.4:1 (non-text needs 3:1). All pass AA. `--k-agent` green is not used for Keep, so verdict colour never reads as a kind.

## 9. Tickets (Sonnet; Inspector.tsx and new files only)

| # | Ticket | Owns | Size |
|---|---|---|---|
| A | Header, verdict, facts | `Inspector.tsx` (structure), new `components/inspector/{Header,Verdict,Facts,MiniBar}.tsx`, new `lib/verdict.ts` (pure, assert self-check per row of §2), append `origin?`, `scope?`, `project?` to `Item` in `graph/model.ts` (append only; #69 also edits it) | M |
| B | About, Related, kind details | new `lib/describe.ts` (+ self-check), `components/inspector/{About,Related,KindDetails}.tsx`; moves today's `Overlaps` and Relation groups into `Related` | M |
| C | Actions, phone footer, a11y pass | new `lib/instruction.ts`, `components/inspector/Actions.tsx`, optional props `onAsk`, `onCluster`, `brief`; the Atlas wiring is one small change made after #69 merges (Atlas is #69's file) | S |

A first; B and C after A merges (both touch `Inspector.tsx` only at their slot). Do not touch `StarMap.tsx`, `paint.ts`, `Chat.tsx`, `Brief.tsx`, backend or `demo*.json`. Origin/scope do not exist in `demo-250.json`; test them with an invented fixture in the self-check, not by editing demos. Update `docs/plan-tracker.md` per ticket.

## 10. Screenshot checklist (demo-250, 1440x900 and 390x844, agent-browser)

1. A skill with a duplicate Overlap: red "Keep one", overlap chip, click flies to partner.
2. A skill with uses: indigo "Keep", usage and last used.
3. A skill never seen with known cost: "Could go".
4. A hook (`Event:matcher`): event, can block, weight, "Not enough data".
5. A plugin: contents counts, total, roll-up verdict; and the `disabled: true` plugin and its child.
6. A trigger-only description (`Use when the task involves…`): What it does = label.
7. `demo-offline.json`: unknown costs read "unknown", no bars.
8. Phone: first view shows name, verdict, first facts row; sticky actions; no horizontal scroll.
9. Reduced motion emulated: no fades or bar growth. Keyboard-only walk through one Item.

## 11. Acceptance

- [ ] Verdict follows §2 exactly; self-check covers every row and the 30-day edge (29, 30, 31).
- [ ] No value ever shows 0 or an empty bar for unknown.
- [ ] Description split passes the self-check: no trigger, trigger-only, trigger first, trigger last, `e.g.`, URL, empty.
- [ ] Overlap chips select and preview the partner; Related groups capped at 5 with Show all.
- [ ] Hidden, not disabled, for unbuilt features (#9, #53 without row, #69 off, no `onAsk`).
- [ ] Only existing tokens; AA contrast as in §8; colour always paired with a word or icon.
- [ ] 390px: first view and sticky footer as §7; 44px targets.
- [ ] Gates: lint, build, `layout:check`, `chat:cluster:check` still pass; screenshots §10 checked by eye.
- [ ] Nothing new is sent to any provider; no new dependency.
