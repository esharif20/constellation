# Where "Ask locally" lives

Status: built on `claude/ask-placement`, 2026-11-05. Placement only: the chat panel, its API and its answers are unchanged (`docs/design/ask-purpose.md`, `chat-answers.md`). Demo data only (`docs/design/demo-250.json`).

## The problem

The trigger was a floating pill in the bottom-left corner. That corner already holds the Legend (three rows: kinds, Packs, size key), the Brief, the cluster card and, on phones, the Brief and Inspector sheets. So the pill had to measure the Legend and move above whichever sheet was open, using four `bottom` rules. At 1440 it sat squeezed between the Brief and the Legend, partly under the panel's edge. At 390 it covered the first Legend row. Nothing on the first screen said the app can answer questions. The app-screen rules in `design-taste-frontend` say a floating button is acceptable only when it is the screen's one primary action and covers nothing at any width. This one met neither condition.

Before: `screenshots/ask-placement-before-1440-brief.jpg`, `screenshots/ask-placement-before-390-rest.jpg`.

## Options

### A. In the top bar, next to search (chosen)

```
1440
| Constellation  246 items...  [All|Global|Repo]   [Q Find an Item  /] [o Ask locally A]  History  Explain |
| +- Brief / Chat / Cluster -+                                                   +- Inspector -+         |
| |                          |                 sky                               |             |         |
| +--------------------------+                                                   +-------------+         |
| Legend rows ...                                                                                        |

390
| Constellation  246 items...      |
| History  [book]  [All|Global|Repo]|
| [Q Find an Item      ] [o Ask locally] |
|              sky                 |
| ===== sheet (Brief / Chat / Inspector) ===== |
```

The two ways of questioning the map sit together: "Find an Item" by name, "Ask locally" by question. The top bar is already reserved space: the map fit measures `header`, so the button never covers a star, the focus area or the What-if chip, and it never needs to know about sheets. It is a toggle (`aria-expanded`, `aria-controls` while open) with a pressed fill when the panel is open, so the open panel is visibly tied to its button.

### B. A command bar at the top centre ("Ask about your setup... ⌘K") that expands into the panel

```
| Constellation  [ Ask about your setup...            ⌘K ]   [Q Find /]  History |
```

This is the most discoverable option, but it puts two input-shaped fields side by side, and people would type Item names into the wrong one. It also wants the answer under the bar, in the centre. That is where the camera frames the selected star, so answers would cover the focus area. Merging both into one box (search results plus an "Ask: ..." row) is the stronger version of B. That changes search behaviour, so it is a separate ticket.

### C. A tab on the right edge

```
|                                   sky                        |A|
|                                                             |s|
|                                                             |k|
```

This is out of everyone's way, but the right edge belongs to the Inspector, which would cover or move the tab every time something is selected. Vertical text is hard to read, and on phones the tab would sit on the scroll and back-swipe edge.

## Recommendation and what was built

Option A:

- `AskTrigger` (exported from `Chat.tsx`, `id="ask-trigger"`) is passed to `TopBar` through a new `ask` slot and sits right after search. On phones it shares the search row (both 44 px). From 1380 px up it shows the label and the `A` kbd. Between 641 and 1379 px the one-row bar is full, so the label folds to an icon. It stays in the accessible name and the `title`. The kbd shows from 1024 px.
- Shortcut `A` opens Ask from anywhere except text fields, matching the existing `/` (search) and `B` (Brief). Escape still collapses the panel and returns focus to the trigger.
- Context chip: the Inspector's actions gain "Ask about this". It drafts "Should I keep <name>?" into the box without sending, the same path as "Compare with…".
- The old floating pill, its Legend measuring for the trigger, the four phone `bottom` offsets and the Brief's 52 px footer reserve are removed. The Brief gets that height back.
- The tablet top bar (641-1023 px) was already overflowing at 768 (the right-most control ended at 795 px). The History label and the search `/` kbd now fold away below 1024 px and Explain is icon-only there, so the bar fits at 700 and 768 with the new button.

Not built: a first-run hint (the labelled button and the starter questions in the panel already explain it), an "Ask about this cluster" chip on the cluster card (a server route for cluster questions would need to exist first), and ⌘K.

## Accessibility

- A real `<button>` with a visible label (or an sr-only label at mid widths), `aria-expanded`, `aria-controls="chat-panel"` while open, `aria-keyshortcuts="A"`. The kbd is `aria-hidden`, so the name stays "Ask locally".
- Tab order: search, then Ask, then History and Explain, which matches the visual order.
- Focus moves to the question box on open and back to the trigger on Escape or close.
- The focus ring and the 44 px phone target are the existing button tokens. The indigo border meets the 3:1 non-text contrast on glass.

## Phone (390)

The button sits on the search row at the top, not in the thumb zone. That is the trade: the bottom of a phone screen belongs to the sheets (Brief, Inspector, cluster, Chat) and the Legend, and every bottom placement collided with one of them. When Chat opens, the sheet rises from the bottom, so the input and the Ask button are in the thumb zone where typing happens. The trigger is never covered by a sheet.

## Verified

agent-browser on `demo-250.json` at 1440x900 and 390x844 (rest, Brief open, Chat open, Inspector, "Ask about this"), plus header measurements at 700, 768, 1024, 1280 and 1440. After screenshots: `screenshots/ask-placement-final-1440-askthis.jpg`, `-final-390-rest.jpg`, `-final-390-chat.jpg`.

## Open for the owner

1. Shortcut: `A` (built, matches `/` and `B`) or ⌘K as well?
2. Should search and Ask merge into one box later (option B's strong form)?
3. Is the top of a phone screen acceptable for Ask, or should it also have a bottom placement once the sheets are reworked?
