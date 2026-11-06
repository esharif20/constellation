# Terminal frames

Text snapshots of bare `constellation` in a terminal, as drawn with `NO_COLOR` (with colour the banner is olive, the selected row teal,
bars red/blue/green by size, footers dim). Data is the invented demo scan `docs/design/demo-assess.json`. Generated from the pure
functions in `menu.py`, `analyze.py` and `cleanup.py`; exact frames are pinned in `tests/test_menu.py`, `tests/test_analyze.py`,
`tests/test_cleanup.py`, and `test_pty_*` drive the real program in a pseudo-terminal. Modelled on Mole (`mo`).

## Main menu, 80 columns (the URL moves beside the art at 87 columns or more)

Entries mirror the command map: 1 Scan, 2 Open, 3 Analyze, 4 Find, 5 Clean, 6 Status, M More. Logic in `frontdoor.py` (entries,
More list, first-run wording) and `menu.py` (frames); `tests/test_menu.py` pins the frames.

```

 _   _       _  ___  _           _  ___ ___  _     
|   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
|_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
github.com/esharif20/constellation
Map your Claude setup · 0.2.0

  ➤ 1. Scan     Read ~/.claude, build or refresh the scan
    2. Open     The graph of your setup, in the browser
    3. Analyze  Rank what loads at the start of every session
    4. Find     Say what a forgotten skill does
    5. Clean    A cleanup checklist with verdicts
    6. Status   Health, this week, what went quiet

  ↑↓ | Enter | M More | V Version | U Update | Q Quit
```

## First run (no saved scan): the header says so, Scan is highlighted and explains itself

Open, Analyze, Clean and Status then ask `Scan first? (y/N) ` instead of failing (Open still falls back to the demo on N).

```

 _   _       _  ___  _           _  ___ ___  _     
|   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
|_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
github.com/esharif20/constellation
Map your Claude setup · 0.2.0

  No scan yet. Start with 1 Scan.

  ➤ 1. Scan     Start here: read ~/.claude and build your map
    2. Open     The graph of your setup, in the browser
    3. Analyze  Rank what loads at the start of every session
    4. Find     Say what a forgotten skill does
    5. Clean    A cleanup checklist with verdicts
    6. Status   Health, this week, what went quiet

  ↑↓ | Enter | M More | V Version | U Update | Q Quit
```

## 1 Scan

```
  ▸ Scan

  Reads ~/.claude (local files only) and writes constellation.json.
  Offline: nothing is sent anywhere.

  Scan now? (y/N, Esc to cancel)
  Scanning your setup (offline, nothing is sent)...
  Done: 97 Items, 12 clusters
  Next: constellation status
```

Prompts take typed text; Esc (alone, then Enter) cancels and goes back. In a terminal each command also ends with one dim
`Next: constellation ...` line from `next_step.py` (after unused: why <first item>; cost: clean; find: why <top hit>; scan: status;
status: unused; doctor: cost; clean: open). Nothing is printed when stdout is piped or `--json` is used.

## M More: every other command, grouped as in `constellation --help` (Look, Act, Map, Manage)

Commands that need an answer ask a short question first (Why: Which Item? Ask: What do you want to know? Profile: Which project?).

```

 _   _       _  ___  _           _  ___ ___  _     
|   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
|_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
github.com/esharif20/constellation
Map your Claude setup · 0.2.0

    1. Doctor          Look · One-screen health check
    2. Cost            Look · What loads at session start
    3. Unused          Look · Items not used lately
    4. Twins           Look · Overlapping skills and which you use
    5. Why             Look · Why one Item has its verdict
  ➤ 6. Remove preview  Look · What breaks if you remove an Item
    7. Hooks           Look · Every hook, ranked
    8. Clashes         Look · Hook, MCP and trigger collisions
    9. Triggers        Look · Skills that never or over-fire
    10. Explain         Look · Plain-English summary of the setup
    11. Ask             Look · Ask a question (local rules, no model)
    12. Report          Look · Plain-text report of the scan
    13. Assess          Look · Every verdict, as JSON
    14. Weekly          Look · What changed since the last scan
    15. Diff            Look · Items changed between two scans
    16. Delta           Look · Tokens and Overlaps between two scans
    17. Preview         Look · What a downloaded plugin would add
    18. Profile         Look · What one project really uses
    19. Expand          Look · Tools of one local MCP server
    20. Review          Act · Go through Suggestions one by one
    21. Share           Act · Write a public-safe snapshot
    22. Export          Act · Show the public snapshot (dry run)
    23. Scan preview    Map · Show what a scan would send and write
    24. Purge           Manage · Items only used by idle projects
    25. Update          Manage · The upgrade command for this install
    26. Uninstall       Manage · How to remove it (dry run)
    27. Completion      Manage · A shell completion script
    28. Doctor --env    Manage · Check Python, install and key

  ↑↓ | Enter | Esc Back | Q Quit
```

## 3 Analyze (ranked by always-on cost; Enter why, O open in the graph, P removal preview, F file path, R rescan)

```
Analyze Setup  (5,503 tokens at session start)
What loads at the start of every session, biggest first:  10 Items

   1. ████████████████████████   7% | quarterly-ledger-reconcil… 410 tok
▶  2. █████████                  3% | lighthouse-lamp-maintenan… 150 tok
   3. ████████                   2% | flashcard-deck             136 tok
   4. ████████                   2% | focus-rings                134 tok
   5. ███████                    2% | motion-pass                123 tok
   6. ███████                    2% | flake-hunter               122 tok
   7. ███████                    2% | dependency-tour            117 tok
   8. ███████                    2% | yaml-lint                  116 tok
   9. ███████                    2% | critic                     115 tok
  10. ███████                    2% | port-finder                112 tok

↑↓→ | Enter | R Refresh | O Open | P Preview | F File | Esc/Q Back
```

While scanning the same page shows `Scanning…` in the header with an empty list.

## 5 Clean: a dry run first (Space toggles an Item in or out of the checklist, P pins it as keep, A writes a new checklist)

```
Clean  (dry run: nothing is deleted)
Could free ~2,442 tokens per session (0 to 2,442; 1 unmeasured)

  skill  13 Items, ~1,168 tokens
    [x] quarterly-ledger-reconciliation-helper  Likely redundant · medium · 410…
    [x] yaml-lint  Review · low · 116 · Its description is 4 words, so Claude m…
    [x] port-finder  Review · low · 112 · Its description is 4 words, so Claude…
  ▶ [x] todo-sweep  Review · low · 100 · Its description is 4 words, so Claude …
    [x] json-shape  Review · low · 81 · Its description is 4 words, so Claude m…
    [x] explain-error  Review · low · 78 · Its description is 4 words, so Claud…
    [x] branch-tidy  Review · low · 68 · Its description is 4 words, so Claude …
    [x] regex-helper  Review · low · 54 · Its description is 4 words, so Claude…
    [x] screenshot-diff  Review · low · 39 · Its description is 4 words, so Cla…
    [x] timezone-math  Review · low · 39 · Its description is 4 words, so Claud…
    [x] quick-commit  Review · low · 26 · Its description is 4 words, so Claude…
    [x] rename-symbol  Review · low · 25 · Its description is 4 words, so Claud…
    [x] unit-convert  Review · low · 20 · Its description is 4 words, so Claude…

↑↓ | Enter Why | Space Toggle | P Pin | A Write checklist | Esc/Q Back
```

After Space on the first Item the headline total drops:

```
Clean  (dry run: nothing is deleted)
Could free ~2,032 tokens per session (0 to 2,442; 1 unmeasured)

  skill  13 Items, ~1,168 tokens
  ▶ [ ] quarterly-ledger-reconciliation-helper  Likely redundant · medium · 410…
```

`A` asks first, showing the path, and never overwrites:

```
  Write a checklist of 80 Items to /home/you/cleanup.md (new file, deletes nothing)? [y/N]
```

## After any command

```
  Press Enter or Esc to return (q to quit)
```

While a command runs the title carries a dim hint (real terminal only), and Esc or Ctrl-C stops just that command:

```
  ▸ Status
  Esc to cancel

  Cancelled
```

## Prompts (Find, Remove preview, the scan question, the checklist question)

Every prompt reads keys itself, so Esc cancels it and does nothing. y/N questions say so, and anything but `y` means no:

```
  What does the skill do? (Esc to cancel)
  No fresh scan. Run `constellation scan ~/.claude --offline` (reads ~/.claude locally, sends nothing)? [y/N, Esc to cancel]
```

## 1 Open (one key from the menu)

```
  ▸ Open

  Press Esc or q to stop the server and go back.
  Serving at http://127.0.0.1:8765/
  http://127.0.0.1:8765/
```

The first URL is an OSC-8 clickable link in terminals that support them (iTerm2, WezTerm, kitty, VS Code, ghostty, VTE 0.50+), plain
text otherwise; the second line is always plain. The server runs in a thread; the browser is opened only once the port accepts
connections (polled for up to 5 s) with `open` (macOS), `xdg-open` (Linux), `os.startfile` (Windows), falling back to
`webbrowser`. If every launcher fails it says `Could not open a browser; open <url> yourself.` Esc or q stops the server and returns
straight to the menu. `constellation open` uses the same opener and says `Press Ctrl-C to stop the server.`

## constellation clean --dry-run --why

```
Clean: dry run (nothing is deleted)

  Could free ~2,442 tokens per session (0 to 2,442; 1 unmeasured)

skill  (13 Items, ~1,168 tokens)
  quarterly-ledger-reconciliation-helper: Likely redundant, medium confidence, saves 410
      - Does the same job as review-diff; neither has been used
  yaml-lint: Review, low confidence, saves 116
      - Its description is 4 words, so Claude may never pick it
  port-finder: Review, low confidence, saves 112
      - Its description is 4 words, so Claude may never pick it
  todo-sweep: Review, low confidence, saves 100
      - Its description is 4 words, so Claude may never pick it
  json-shape: Review, low confidence, saves 81
      - Its description is 4 words, so Claude may never pick it
  explain-error: Review, low confidence, saves 78
      - Its description is 4 words, so Claude may never pick it
  branch-tidy: Review, low confidence, saves 68
      - Its description is 4 words, so Claude may never pick it
  regex-helper: Review, low confidence, saves 54
      - Its description is 4 words, so Claude may never pick it
  screenshot-diff: Review, low confidence, saves 39
  ...
```

Keys: Up/Down move, 1-5 jump, Enter runs, M More, V Version, U Update, Q quit. Ctrl-C at the main menu quits (cursor and terminal mode
restored, exit 130). Everywhere else there is a way back: Esc, Left or B return from More, Analyze and Clean (Q also leaves Analyze and
Clean; Ctrl-C there goes back too); Esc cancels any prompt; Enter or Esc leaves a command's output. Ctrl-C (or Esc, where the
terminal can watch for it) during a running command cancels only that command, prints `Cancelled` and returns to the menu. A scan
writes its file whole into place, so a cancelled one leaves no partial file.
