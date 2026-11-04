# Chat answers: readable, beginner-friendly, short (#51)

Status: design only, 2026-11-04. Builds on `docs/plans/chat.md` (#11), `docs/design/DESIGN.md` (tokens, type) and `docs/design/cluster-focus.md` §8 (left slot: card, Brief or Chat, one at a time). Compare/explain intents are #48 (`claude/chat-compare`, in flight); this ticket owns the reply format and its rendering only. Examples use demo data (`docs/design/demo.json`).

Unchanged: chat is local, free and deterministic. No provider call, no model, no download, nothing written to disk, no conversation history. Privacy invariant and cost rule apply as written. The app never edits the user's setup, so every verdict is a suggestion.

## The problem

A typo-filled "what is X and how does it compare to Y" currently returns `Matching Items:` and five raw descriptions cut at 160 characters, mid-word, with the trigger phrasing ("Use when the user says …") left in. There is no answer sentence, no comparison and no next step. A beginner cannot tell what any of it means or what to do.

## 1. What the chat is for (ranked)

The map already answers "where is X". The chat should answer the questions a person cleaning up a setup actually has, using only signals we hold locally: kind, description, always-on and on-use cost, usage, Overlap verdicts, cluster.

| Rank | Use case | Intent (owner) | Answer shape |
|---|---|---|---|
| 1 | Should I keep or remove X? | explain + verdict (#48 node, #51 routing words) | 1 card with verdict |
| 2 | What costs the most every session? | top_costs (exists) | up to 5 rows |
| 3 | What have I never used? | usage/unused (exists) | up to 5 rows + coverage note |
| 4 | What is X? | explain (#48) | 1 card |
| 5 | X vs Y | compare (#48) | comparison table + verdict |
| 6 | What does the same job as X? | pairs, scoped (exists) | up to 5 rows with verdict |
| 7 | What do I have for Y (a task)? | search (exists) | up to 5 rows |

"Move" (for example to a project scope) is not offered: the scan does not record scope well enough to advise it. Add it only when it does.

### Empty state: "What you can ask"

Replace the intro paragraph with one line, `body` text-2: "Ask about this setup. Answers are worked out here, for free." Below it, the heading `section` text-3 "What you can ask", then at most five starter buttons. Starters are built from the loaded model so each one works on this scan; a starter whose inputs are missing is not shown.

1. `Should I keep {selected}?` if an Item is selected, else `What could I remove?` (routes to unused).
2. `What costs the most every session?`
3. `What have I never used?`
4. `What is {name}?` using the selected Item, else the top always-on cost Item.
5. `Compare {a} and {b}` using the first `duplicate` Overlap, else the first `wrapper`, else the first `overlap` (demo: `Compare release-notes and changelog-draft`).
6. `What do I have for {cluster label}?` using the largest cluster's label, lowercased, only when fewer than five of the above showed.

Clicking a starter fills the input and submits it (today it only fills; beginners do not notice the second step).

## 2. Reply contract

Additive: the existing `{answer, actions, mode, cached}` stays; a new `blocks` object is added. Old clients keep rendering `answer`; the new client renders `blocks` and falls back to `answer` when `blocks` is missing or invalid. `answer` becomes the plain-text rendering of `blocks` (copy button, screen readers, tests), produced by one function so they cannot drift.

```
blocks: {
  headline: string,                 // one sentence, the answer itself
  cards:    Card[],                 // 0-2 full Item cards (what is X, keep X, X vs Y)
  compare:  Compare | null,         // only for X vs Y; cards then holds both Items
  rows:     Row[],                  // 0-5 compact rows for ranked lists and searches
  more:     number,                 // results not shown; 0 when none
  note:     string | null,          // one caveat, e.g. usage coverage; never a second answer
  next:     string | null,          // one suggested action, imperative
  follow_ups: string[],             // 0-3 chips; each is a full question the server can answer
  did_you_mean: {id, name}[]        // 0-3; non-empty only when the name was ambiguous
}
Card    = {id, name, kind, kind_label, what, always_on, on_use, usage, overlap, verdict}
Compare = {rows: [{label, a, b}], same_cluster: boolean}
Row     = {id, name, kind, what, value}      // value: the ranked figure, e.g. "1,468 tokens every session"
overlap = {with_id, with_name, verdict: "duplicate"|"wrapper"|"overlap", reason} | null
verdict = {label, tone: "keep"|"review"|"remove"|"unknown", why}
```

All display strings are formatted on the server (one place for wording, tested in Python). The client only lays them out. Every `id`, `with_id` and `did_you_mean.id` must exist in the scan; the client validates them exactly as `readReply` validates action ids today, and drops `blocks` (falling back to `answer`) if any check fails. `actions` still carries highlight/focus ids; a compare highlights both Items.

**Verdicts, from local signals only** (first match wins): `duplicate` Overlap → "Keep one" (remove tone) with "Does the same job as {other}"; `wrapper` → "Keep the wrapped one" (review); never seen in the usage window and known always-on cost > 0 → "Could go" (remove) with "Not seen in {N} days of past sessions and costs {T} tokens every session"; seen at least once → "Keep" (keep) with "Used {N} times in {D} days"; no usage read → "Not enough data" (unknown) with "Usage was not read in this scan". Verdict text says "could", never "should delete".

**First-sentence cleaning** (`what`, max 120 characters), applied to the full redacted description before any `_short` cut (today `_display` truncates to 160 first; cleaning must read the untruncated text):
1. Collapse whitespace; strip Markdown markers (`#`, `*`, backticks, link syntax keeps the link text).
2. Split into sentences at `.`, `!` or `?` followed by a space or the end, not after `e.g`, `i.e`, `etc`, `vs` or a single capital letter, and not inside a URL or path.
3. Skip sentences that are trigger phrasing: start with "Use when", "Use this", "Use for", "Trigger", "Invoke", or contain a slash command or quoted example phrases. Take the first sentence left; if none is left, take the first sentence.
4. If it is longer than 120, cut at the last space at or before 119 and append "…"; never cut inside a word. A single word longer than 120 is cut at 119 + "…".
5. Empty or missing description → "No description." Never invent one.

## 3. Wording rules

- **Lead with the answer.** The headline is one sentence, at most 140 characters, that answers the question: "release-notes and changelog-draft do the same job; you could keep one." Never a label such as "Matching Items:" or "Item details:".
- **Plain words, glossed terms.** Use the plain label in the UI and keep the project term in a gloss shown on hover and focus (`title` plus a visually hidden `aria-describedby` text):

  | Say | Gloss (tooltip) | Instead of |
  |---|---|---|
  | Every session | "Loaded into every conversation before you type." | always-on |
  | When used | "Extra cost only when Claude uses it." | on-use |
  | tokens | "A token is about three quarters of a word." | (bare number) |
  | Does the same job as | "Found by comparing descriptions." | Overlap / duplicate |
  | Wraps | "Mostly calls the other one." | wrapper |
  | past sessions | "Your saved Claude Code transcripts." | transcripts |

- **Numbers always carry units** and thousands separators, tabular figures: "1,468 tokens every session", "5,210 tokens when used", "Used 12 times in 30 days", "Last used 2 Nov". Day counts come from the usage window.
- **Unknown is never 0.** Missing cost is "unknown" (Inter italic, text-3), missing usage is "Usage unknown". Totals never add unknowns; say "plus {n} unknown".
- **Lengths.** Headline 140, `what` 120, verdict `why` 90, `next` 100, `note` 160, chip 40 characters; 2 cards, 5 rows, 3 chips, 3 did-you-mean. The plain `answer` stays under 1,200 characters.
- **Tone.** Second person, sentence case, British spelling (as the rest of the app), no exclamation marks, no "Great question". Kind labels are plain: skill, hook, agent, plugin, MCP server, connector.
- **Did you mean.** One close match (typo tier in `retrieve.py`): answer it and say so in the headline, "I took "relese notes" to mean release-notes." Several equally close: headline "Which one did you mean?", no cards, `did_you_mean` chips (each submits the corrected question).
- **Not found.** "I could not find "teapot" in this scan." plus `next` "Check the spelling, or describe what it does." and one chip `What do I have for teapot?` (search by description). Never fall back to unrelated matches as if they were the answer.
- **Empty lists** say what was checked: "Nothing here has been unused in 30 days of past sessions."

## 4. Rendering in `Chat.tsx`

Panel size, position, slot rule and Escape behaviour stay as built (340px desktop panel, 58dvh phone sheet).

- **Question echo:** `ui` 13 text-3, as now, `overflow-wrap:anywhere`.
- **Headline:** `body-lg` 15/1.45 in `--text`, weight 500. 12px below the echo.
- **Cards** (16px below the headline, 12px apart): `bg-surface-2`, 1px `--line-1`, `--radius-lg`, `px-4 py-3`, `<article aria-labelledby>`.
  - Kind line: `section` 12/500 text-3 with the kind glyph, gap 8.
  - Name: a ghost button in `body` 14/500 `--text`, min-h 40 (44 on phones); clicking it calls `onItem(id)` and the map flies to the Item, as the inspector does.
  - What: `body` 14/1.55 text-2, max 3 lines.
  - Stats: a two-column `dl` (Every session / When used, then Used): keys `caption` text-3 with the gloss, values `mono` 12 `--text` with the unit in `caption` text-3; unknown in Inter italic text-3.
  - Overlap: `ui` 13 text-2, "Does the same job as {name}" with the name as a link button.
  - Verdict: a DESIGN.md badge (`h-5 px-2 rounded-full`): keep text-2, review and remove the warn tone, unknown text-3; the `why` follows on the same line in `caption` text-3.
- **Compare:** a real `<table>` inside one card: header row with both names (`th scope="col"`, link buttons), rows Kind / What it does / Every session / When used / Used (`th scope="row"`, `caption` text-3), cells `ui` 13 with mono numbers; a final "Same cluster: yes/no" row. At 292px of content each column is about 120px, which fits the formatted values; `what` cells wrap.
- **Rows:** a list like today's "Highlighted on the map", but each row shows glyph, name (`body` 500), `what` (`caption` text-3, one line, truncated with the full text in `title`) and `value` right-aligned in `mono` 12. `more` > 0 adds "{n} more. Ask a narrower question." in `caption` text-3.
- **Note:** `caption` text-3, 12px below. **Next:** `ui` 13 text-2 with a leading arrow icon, 16px below.
- **Follow-up chips:** outline buttons, `--radius-md` (not pills; pills are badges), `ui` 13, h-9 desktop, h-11 phone, wrap with gap 8. Clicking submits that question.
- **Copy:** a ghost icon button (copy icon, `aria-label="Copy answer"`) right of the headline, copying `answer`; its label reads "Copied" for 2s.
- **Scroll:** the answer area scrolls, the form stays fixed. On a new reply, scroll the question echo to the top of the scroll area (`scrollIntoView({block: "start"})`, instant under reduced motion) so the headline is read first, not the end of the list.
- **Loading:** show "Looking in this Constellation…" only after 150ms (local answers are usually faster, so avoid a flash); the submit button keeps `aria-busy`. **Errors:** unchanged copy and `role="alert"`; a reply that fails validation shows the plain `answer` instead of an error.
- **Phone (< 640px):** same order; cards full width with `px-3`; compare table keeps two columns; chips wrap; every target at least 44px; the sheet and trigger stacking rule in `cluster-focus.md` §8 is unchanged.
- **Accessibility:** the `role="status" aria-live="polite"` region contains only the headline text (cards are outside it, so a five-row answer is not read aloud in full). Focus returns to the input after a reply, as now. Card names and chips are buttons in reading order; glyphs are `aria-hidden`; glosses are reachable by keyboard via the focusable term.

## 5. Future, separate opt-in: model-backed phrasing

Not part of this ticket. A later ticket could let a model rephrase the `headline` and `next` from the finished `blocks`. It would need the user's explicit approval because it would send the question, which the privacy invariant does not cover today. It must be off by default, cached by hash of the redacted input, show its cost first, and fall back to these deterministic strings. Numbers and ids in its output must equal the blocks' or the output is dropped. The deterministic blocks stay the source of truth.

## 6. Implementation checklist (Sonnet)

**Ownership.** #48 owns the intent nodes in `chat.py` (compare, explain, name resolution and did-you-mean via `retrieve.py`). #51 owns a new `src/constellation/answer.py` (first-sentence cleaning, card/row/verdict builders, wording, `to_text(blocks)`), the `blocks` field, the routing words for "keep/remove/get rid of" → explain, and `frontend/src/components/Chat.tsx`. `server.py` is touched only if the response model needs the new field.

**Merge order.** #48 merges first (it is already in flight). #51 then rebases onto it and converts every node's output (#48's and the existing ones) to `blocks`. If #48 ships its own description cleaner, #51 moves it into `answer.py` and keeps one implementation. If #51's `answer.py` is ready before #48 merges, it may land first as a helper-only commit that #48 can import; nothing in `chat.py` changes in that commit.

1. `answer.py`: `first_sentence(text, limit=120)` with the rules in §2, test-first.
2. `answer.py`: `card()`, `row()`, `verdict()`, formatting (units, separators, unknown) and `to_text(blocks)`.
3. `chat.py`: `_response` gains `blocks`; each node builds headline/cards/rows/next/follow-ups via `answer.py`; `answer = to_text(blocks)`. Clean descriptions from the untruncated redacted text before `_display`.
4. `chat.py`: keep/remove words route to explain; not-found and did-you-mean headlines use #48's resolver output.
5. Cache key unchanged in shape (blocks are derived from the same inputs).
6. `Chat.tsx`: validate `blocks` in `readReply`, render per §4, starters from the model, submit-on-click, copy, scroll, delayed loading.
7. Update `docs/plans/chat.md` (contract) and `docs/plan-tracker.md` (#51 status, any deviation) in the same commit.

**Tests** (through `POST /api/chat`, invented Items): `first_sentence` boundaries (no full stop, `e.g.`, URL, trigger-only description, 119/120/121 characters, one long word, empty) and never mid-word; every id in `blocks` exists; unknown cost renders "unknown", never 0; headline at most 140 and one sentence; at most 2 cards, 5 rows, 3 chips; `answer == to_text(blocks)`; did-you-mean with one and with several candidates; not-found never lists unrelated Items; verdict per signal; hostile descriptions are redacted in `what`. Full gates per AGENTS.md, including zero mutmut survivors. Frontend: lint, build, layout check, and the chat accessibility check extended so the live region text equals the headline.

**Screenshots** (demo data only, 1440 and 390px, never a real scan): empty state with starters; "What is tune-spacing?"; "Compare release-notes and changelog-draft"; top costs; never used (demo has no usage, so the unknown state); a did-you-mean; a not-found; loading; an error; keyboard focus on a card name, a chip and the copy button; phone sheet over a cluster.
