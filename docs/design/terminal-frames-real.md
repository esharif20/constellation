# Real-terminal frames

Captured by running `constellation` in a real pseudo-terminal (`tests/vt.py` screen emulator, TERM=xterm-256color) over an invented setup of 30 skills (or `tests/fixtures/scan.json`). Each block is the screen after the step named in its header; the pty tests in `tests/test_terminal_real.py` guard the bugs this walk found.

## 120x40 env=[] steps=[m|DOWN]

```text
--- [120x40] start (cursor HIDDEN r16c0 scrolled=0)

⋆   ✦   ⋆    _   _       _  ___  _           _  ___ ___  _
 ╲ ╱ ╲ ╱    |   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|  Map your Claude setup
  ⋆   ⋆     |_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |  0.1.0
            github.com/esharif20/constellation

  No scan yet. Start with 1 Scan.

  ➤ 1. Scan     Start here: read ~/.claude and build your map
    2. Open     The graph of your setup, in the browser
    3. Analyze  Rank what loads at the start of every session
    4. Find     Say what a forgotten skill does
    5. Clean    A cleanup checklist with verdicts
    6. Status   Health, this week, what went quiet

  ↑↓ | Enter | M More | V Version | U Update | Q Quit

--- [120x40] m (cursor HIDDEN r36c0 scrolled=0)

⋆   ✦   ⋆    _   _       _  ___  _           _  ___ ___  _
 ╲ ╱ ╲ ╱    |   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|  Map your Claude setup
  ⋆   ⋆     |_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |  0.1.0
            github.com/esharif20/constellation

  ➤ 1.  Doctor          Look · One-screen health check
    2.  Cost            Look · What loads at session start
    3.  Unused          Look · Items not used lately
    4.  Twins           Look · Overlapping skills and which you use
    5.  Why             Look · Why one Item has its verdict
    6.  Remove preview  Look · What breaks if you remove an Item
    7.  Hooks           Look · Every hook, ranked
    8.  Clashes         Look · Hook, MCP and trigger collisions
    9.  Triggers        Look · Skills that never or over-fire
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

--- [120x40] DOWN (cursor HIDDEN r36c0 scrolled=0)

⋆   ✦   ⋆    _   _       _  ___  _           _  ___ ___  _
 ╲ ╱ ╲ ╱    |   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|  Map your Claude setup
  ⋆   ⋆     |_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |  0.1.0
            github.com/esharif20/constellation

    1.  Doctor          Look · One-screen health check
  ➤ 2.  Cost            Look · What loads at session start
    3.  Unused          Look · Items not used lately
    4.  Twins           Look · Overlapping skills and which you use
    5.  Why             Look · Why one Item has its verdict
    6.  Remove preview  Look · What breaks if you remove an Item
    7.  Hooks           Look · Every hook, ranked
    8.  Clashes         Look · Hook, MCP and trigger collisions
    9.  Triggers        Look · Skills that never or over-fire
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

final exit None
--- [120x40] after ctrl-c (cursor HIDDEN r16c0 scrolled=0)

⋆   ✦   ⋆    _   _       _  ___  _           _  ___ ___  _
 ╲ ╱ ╲ ╱    |   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|  Map your Claude setup
  ⋆   ⋆     |_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |  0.1.0
            github.com/esharif20/constellation

  No scan yet. Start with 1 Scan.

  ➤ 1. Scan     Start here: read ~/.claude and build your map
    2. Open     The graph of your setup, in the browser
    3. Analyze  Rank what loads at the start of every session
    4. Find     Say what a forgotten skill does
    5. Clean    A cleanup checklist with verdicts
    6. Status   Health, this week, what went quiet

  ↑↓ | Enter | M More | V Version | U Update | Q Quit

```

## 80x24 env=[SCAN=fix] steps=[ENTER|ESC]

```text
--- [80x24] start (cursor HIDDEN r15c0 scrolled=0)

⋆   ✦   ⋆    _   _       _  ___  _           _  ___ ___  _
 ╲ ╱ ╲ ╱    |   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
  ⋆   ⋆     |_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
            Map your Claude setup · 0.1.0
            github.com/esharif20/constellation

  ➤ 1. Scan     Read ~/.claude, build or refresh the scan
    2. Open     The graph of your setup, in the browser
    3. Analyze  Rank what loads at the start of every session
    4. Find     Say what a forgotten skill does
    5. Clean    A cleanup checklist with verdicts
    6. Status   Health, this week, what went quiet

  ↑↓ | Enter | M More | V Version | U Update | Q Quit

--- [80x24] ENTER (cursor on r6c33 scrolled=0)
  ▸ Scan

  Reads /tmp/tr/home/.claude (local files only) and writes /tmp/tr/home/.cache/c
onstellation/scan.json.
  Offline: nothing is sent anywhere.

  Scan now? [y/N, Esc to cancel]

--- [80x24] ESC (cursor HIDDEN r15c0 scrolled=0)

⋆   ✦   ⋆    _   _       _  ___  _           _  ___ ___  _
 ╲ ╱ ╲ ╱    |   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
  ⋆   ⋆     |_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
            Map your Claude setup · 0.1.0
            github.com/esharif20/constellation

  ➤ 1. Scan     Read ~/.claude, build or refresh the scan
    2. Open     The graph of your setup, in the browser
    3. Analyze  Rank what loads at the start of every session
    4. Find     Say what a forgotten skill does
    5. Clean    A cleanup checklist with verdicts
    6. Status   Health, this week, what went quiet

  ↑↓ | Enter | M More | V Version | U Update | Q Quit

final exit 130
--- [80x24] after ctrl-c (cursor on r0c0 scrolled=0)


```

## 80x24 env=[SCAN=fix] steps=[m|DOWN|RESIZE60x20]

```text
--- [80x24] start (cursor HIDDEN r15c0 scrolled=0)

⋆   ✦   ⋆    _   _       _  ___  _           _  ___ ___  _
 ╲ ╱ ╲ ╱    |   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
  ⋆   ⋆     |_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
            Map your Claude setup · 0.1.0
            github.com/esharif20/constellation

  ➤ 1. Scan     Read ~/.claude, build or refresh the scan
    2. Open     The graph of your setup, in the browser
    3. Analyze  Rank what loads at the start of every session
    4. Find     Say what a forgotten skill does
    5. Clean    A cleanup checklist with verdicts
    6. Status   Health, this week, what went quiet

  ↑↓ | Enter | M More | V Version | U Update | Q Quit

--- [80x24] m (cursor HIDDEN r23c0 scrolled=0)

⋆   ✦   ⋆    _   _       _  ___  _           _  ___ ___  _
 ╲ ╱ ╲ ╱    |   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
  ⋆   ⋆     |_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
            Map your Claude setup · 0.1.0
            github.com/esharif20/constellation

  ➤ 1.  Doctor          Look · One-screen health check
    2.  Cost            Look · What loads at session start
    3.  Unused          Look · Items not used lately
    4.  Twins           Look · Overlapping skills and which you use
    5.  Why             Look · Why one Item has its verdict
    6.  Remove preview  Look · What breaks if you remove an Item
    7.  Hooks           Look · Every hook, ranked
    8.  Clashes         Look · Hook, MCP and trigger collisions
    9.  Triggers        Look · Skills that never or over-fire
    10. Explain         Look · Plain-English summary of the setup
    11. Ask             Look · Ask a question (local rules, no model)
    12. Report          Look · Plain-text report of the scan
    13. Assess          Look · Every verdict, as JSON
    14. Weekly          Look · What changed since the last scan

  ↑↓ | Enter | Esc Back | Q Quit

--- [80x24] DOWN (cursor HIDDEN r23c0 scrolled=0)

⋆   ✦   ⋆    _   _       _  ___  _           _  ___ ___  _
 ╲ ╱ ╲ ╱    |   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
  ⋆   ⋆     |_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
            Map your Claude setup · 0.1.0
            github.com/esharif20/constellation

    1.  Doctor          Look · One-screen health check
  ➤ 2.  Cost            Look · What loads at session start
    3.  Unused          Look · Items not used lately
    4.  Twins           Look · Overlapping skills and which you use
    5.  Why             Look · Why one Item has its verdict
    6.  Remove preview  Look · What breaks if you remove an Item
    7.  Hooks           Look · Every hook, ranked
    8.  Clashes         Look · Hook, MCP and trigger collisions
    9.  Triggers        Look · Skills that never or over-fire
    10. Explain         Look · Plain-English summary of the setup
    11. Ask             Look · Ask a question (local rules, no model)
    12. Report          Look · Plain-text report of the scan
    13. Assess          Look · Every verdict, as JSON
    14. Weekly          Look · What changed since the last scan

  ↑↓ | Enter | Esc Back | Q Quit

--- [80x24] RESIZE60x20 (cursor HIDDEN r19c0 scrolled=0)

 _   _       _  ___  _           _  ___ ___  _
|   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
|_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
Map your Claude setup · 0.1.0
github.com/esharif20/constellation

    1.  Doctor          Look · One-screen health check
  ➤ 2.  Cost            Look · What loads at session start
    3.  Unused          Look · Items not used lately
    4.  Twins           Look · Overlapping skills and which…
    5.  Why             Look · Why one Item has its verdict
    6.  Remove preview  Look · What breaks if you remove an…
    7.  Hooks           Look · Every hook, ranked
    8.  Clashes         Look · Hook, MCP and trigger collis…
    9.  Triggers        Look · Skills that never or over-fi…
    10. Explain         Look · Plain-English summary of the…

  ↑↓ | Enter | Esc Back | Q Quit

final exit None
--- [80x24] after ctrl-c (cursor HIDDEN r15c0 scrolled=0)

 _   _       _  ___  _           _  ___ ___  _
|   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
|_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
Map your Claude setup · 0.1.0
github.com/esharif20/constellation

  ➤ 1. Scan     Read ~/.claude, build or refresh the scan
    2. Open     The graph of your setup, in the browser
    3. Analyze  Rank what loads at the start of every sessi…
    4. Find     Say what a forgotten skill does
    5. Clean    A cleanup checklist with verdicts
    6. Status   Health, this week, what went quiet

  ↑↓ | Enter | M More | V Version | U Update | Q Quit

```

## 54x24 env=[] steps=[ENTER|y|ENTER]

```text
--- [54x24] start (cursor HIDDEN r17c0 scrolled=0)

 _   _       _  ___  _           _  ___ ___  _
|   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
|_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
Map your Claude setup · 0.1.0
github.com/esharif20/constellation

  No scan yet. Start with 1 Scan.

  ➤ 1. Scan     Start here: read ~/.claude and build …
    2. Open     The graph of your setup, in the brows…
    3. Analyze  Rank what loads at the start of every…
    4. Find     Say what a forgotten skill does
    5. Clean    A cleanup checklist with verdicts
    6. Status   Health, this week, what went quiet

  ↑↓ | Enter | M More | V Version | U Update | Q Quit

--- [54x24] ENTER (cursor on r6c33 scrolled=0)
  ▸ Scan

  Reads /tmp/tr/home/.claude (local files only) and wr
ites /tmp/tr/home/.cache/constellation/scan.json.
  Offline: nothing is sent anywhere.

  Scan now? [y/N, Esc to cancel]

--- [54x24] y (cursor on r6c34 scrolled=0)
  ▸ Scan

  Reads /tmp/tr/home/.claude (local files only) and wr
ites /tmp/tr/home/.cache/constellation/scan.json.
  Offline: nothing is sent anywhere.

  Scan now? [y/N, Esc to cancel] y

--- [54x24] ENTER (cursor on r14c43 scrolled=0)
  ▸ Scan

  Reads /tmp/tr/home/.claude (local files only) and wr
ites /tmp/tr/home/.cache/constellation/scan.json.
  Offline: nothing is sent anywhere.

  Scan now? [y/N, Esc to cancel] y
  Scanning your setup (offline, nothing is sent)...
Groups: built from words and plugin structure. For bet
ter groups add the local model (about 100 MB): uv sync
 --extra local
  Done: 30 Items, 5 clusters
  Next: constellation status

  Press Enter or Esc to return (q to quit)

final exit None
--- [54x24] after ctrl-c (cursor HIDDEN r15c0 scrolled

 _   _       _  ___  _           _  ___ ___  _
|   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
|_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
Map your Claude setup · 0.1.0
github.com/esharif20/constellation

  ➤ 1. Scan     Read ~/.claude, build or refresh the …
    2. Open     The graph of your setup, in the brows…
    3. Analyze  Rank what loads at the start of every…
    4. Find     Say what a forgotten skill does
    5. Clean    A cleanup checklist with verdicts
    6. Status   Health, this week, what went quiet

  ↑↓ | Enter | M More | V Version | U Update | Q Quit

```

## 40x24 env=[SCAN=fix] steps=[ENTER|DOWN]

```text
--- [40x24] start (cursor HIDDEN r12c0 s

⋆✦⋆ Constellation
Map your Claude setup · 0.1.0

  ➤ 1. Scan     Read ~/.claude, build o…
    2. Open     The graph of your setup…
    3. Analyze  Rank what loads at the …
    4. Find     Say what a forgotten sk…
    5. Clean    A cleanup checklist wit…
    6. Status   Health, this week, what…

  ↑↓ | Enter | M More | Q Quit

--- [40x24] ENTER (cursor on r7c33 scrol
  ▸ Scan

  Reads /tmp/tr/home/.claude (local file
s only) and writes /tmp/tr/home/.cache/c
onstellation/scan.json.
  Offline: nothing is sent anywhere.

  Scan now? [y/N, Esc to cancel]

--- [40x24] DOWN (cursor on r7c33 scroll
  ▸ Scan

  Reads /tmp/tr/home/.claude (local file
s only) and writes /tmp/tr/home/.cache/c
onstellation/scan.json.
  Offline: nothing is sent anywhere.

  Scan now? [y/N, Esc to cancel]

final exit None
--- [40x24] after ctrl-c (cursor HIDDEN 

⋆✦⋆ Constellation
Map your Claude setup · 0.1.0

  ➤ 1. Scan     Read ~/.claude, build o…
    2. Open     The graph of your setup…
    3. Analyze  Rank what loads at the …
    4. Find     Say what a forgotten sk…
    5. Clean    A cleanup checklist wit…
    6. Status   Health, this week, what…

  ↑↓ | Enter | M More | Q Quit

```

## 80x24 env=[SCAN=fix,PYTHONIOENCODING=latin-1,PYTHONUTF8=0] steps=[DOWN]

```text
--- [80x24] start (cursor HIDDEN r15c0 scrolled=0)

*   +   *    _   _       _  ___  _           _  ___ ___  _
 \ / \ /    |   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
  *   *     |_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
            Map your Claude setup - 0.1.0
            github.com/esharif20/constellation

  > 1. Scan     Read ~/.claude, build or refresh the scan
    2. Open     The graph of your setup, in the browser
    3. Analyze  Rank what loads at the start of every session
    4. Find     Say what a forgotten skill does
    5. Clean    A cleanup checklist with verdicts
    6. Status   Health, this week, what went quiet

  Up/Dn | Enter | M More | V Version | U Update | Q Quit

--- [80x24] DOWN (cursor HIDDEN r15c0 scrolled=0)

*   +   *    _   _       _  ___  _           _  ___ ___  _
 \ / \ /    |   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
  *   *     |_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
            Map your Claude setup - 0.1.0
            github.com/esharif20/constellation

    1. Scan     Read ~/.claude, build or refresh the scan
  > 2. Open     The graph of your setup, in the browser
    3. Analyze  Rank what loads at the start of every session
    4. Find     Say what a forgotten skill does
    5. Clean    A cleanup checklist with verdicts
    6. Status   Health, this week, what went quiet

  Up/Dn | Enter | M More | V Version | U Update | Q Quit

final exit 130
--- [80x24] after ctrl-c (cursor on r0c0 scrolled=0)


```

## 80x24 env=[SCAN=fix] steps=[DOWN|DOWN|DOWN|DOWN|ENTER|DOWN]

```text
--- [80x24] start (cursor HIDDEN r15c0 scrolled=0)

⋆   ✦   ⋆    _   _       _  ___  _           _  ___ ___  _
 ╲ ╱ ╲ ╱    |   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
  ⋆   ⋆     |_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
            Map your Claude setup · 0.1.0
            github.com/esharif20/constellation

  ➤ 1. Scan     Read ~/.claude, build or refresh the scan
    2. Open     The graph of your setup, in the browser
    3. Analyze  Rank what loads at the start of every session
    4. Find     Say what a forgotten skill does
    5. Clean    A cleanup checklist with verdicts
    6. Status   Health, this week, what went quiet

  ↑↓ | Enter | M More | V Version | U Update | Q Quit

--- [80x24] DOWN (cursor HIDDEN r15c0 scrolled=0)

⋆   ✦   ⋆    _   _       _  ___  _           _  ___ ___  _
 ╲ ╱ ╲ ╱    |   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
  ⋆   ⋆     |_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
            Map your Claude setup · 0.1.0
            github.com/esharif20/constellation

    1. Scan     Read ~/.claude, build or refresh the scan
  ➤ 2. Open     The graph of your setup, in the browser
    3. Analyze  Rank what loads at the start of every session
    4. Find     Say what a forgotten skill does
    5. Clean    A cleanup checklist with verdicts
    6. Status   Health, this week, what went quiet

  ↑↓ | Enter | M More | V Version | U Update | Q Quit

--- [80x24] DOWN (cursor HIDDEN r15c0 scrolled=0)

⋆   ✦   ⋆    _   _       _  ___  _           _  ___ ___  _
 ╲ ╱ ╲ ╱    |   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
  ⋆   ⋆     |_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
            Map your Claude setup · 0.1.0
            github.com/esharif20/constellation

    1. Scan     Read ~/.claude, build or refresh the scan
    2. Open     The graph of your setup, in the browser
  ➤ 3. Analyze  Rank what loads at the start of every session
    4. Find     Say what a forgotten skill does
    5. Clean    A cleanup checklist with verdicts
    6. Status   Health, this week, what went quiet

  ↑↓ | Enter | M More | V Version | U Update | Q Quit

--- [80x24] DOWN (cursor HIDDEN r15c0 scrolled=0)

⋆   ✦   ⋆    _   _       _  ___  _           _  ___ ___  _
 ╲ ╱ ╲ ╱    |   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
  ⋆   ⋆     |_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
            Map your Claude setup · 0.1.0
            github.com/esharif20/constellation

    1. Scan     Read ~/.claude, build or refresh the scan
    2. Open     The graph of your setup, in the browser
    3. Analyze  Rank what loads at the start of every session
  ➤ 4. Find     Say what a forgotten skill does
    5. Clean    A cleanup checklist with verdicts
    6. Status   Health, this week, what went quiet

  ↑↓ | Enter | M More | V Version | U Update | Q Quit

--- [80x24] DOWN (cursor HIDDEN r15c0 scrolled=0)

⋆   ✦   ⋆    _   _       _  ___  _           _  ___ ___  _
 ╲ ╱ ╲ ╱    |   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
  ⋆   ⋆     |_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
            Map your Claude setup · 0.1.0
            github.com/esharif20/constellation

    1. Scan     Read ~/.claude, build or refresh the scan
    2. Open     The graph of your setup, in the browser
    3. Analyze  Rank what loads at the start of every session
    4. Find     Say what a forgotten skill does
  ➤ 5. Clean    A cleanup checklist with verdicts
    6. Status   Health, this week, what went quiet

  ↑↓ | Enter | M More | V Version | U Update | Q Quit

--- [80x24] ENTER (cursor HIDDEN r9c0 scrolled=0)
Clean  (dry run: nothing is deleted)
Could free ~480 tokens per session (0 to 480)

  skill  1 Item, ~420 tokens
  ▶ [x] deploy  Likely redundant · low · 420 · Does the same job as ship; neith…
  agent  1 Item, ~60 tokens
    [x] reviewer  Likely redundant · low · 60 · Only hands off to review

↑↓ | Enter Why | Space Toggle | P Pin | A Write checklist | Esc/Q Back

--- [80x24] DOWN (cursor HIDDEN r9c0 scrolled=0)
Clean  (dry run: nothing is deleted)
Could free ~480 tokens per session (0 to 480)

  skill  1 Item, ~420 tokens
    [x] deploy  Likely redundant · low · 420 · Does the same job as ship; neith…
  agent  1 Item, ~60 tokens
  ▶ [x] reviewer  Likely redundant · low · 60 · Only hands off to review

↑↓ | Enter Why | Space Toggle | P Pin | A Write checklist | Esc/Q Back

final exit None
--- [80x24] after ctrl-c (cursor HIDDEN r15c0 scrolled=0)

⋆   ✦   ⋆    _   _       _  ___  _           _  ___ ___  _
 ╲ ╱ ╲ ╱    |   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
  ⋆   ⋆     |_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
            Map your Claude setup · 0.1.0
            github.com/esharif20/constellation

    1. Scan     Read ~/.claude, build or refresh the scan
    2. Open     The graph of your setup, in the browser
    3. Analyze  Rank what loads at the start of every session
    4. Find     Say what a forgotten skill does
  ➤ 5. Clean    A cleanup checklist with verdicts
    6. Status   Health, this week, what went quiet

  ↑↓ | Enter | M More | V Version | U Update | Q Quit

```

## 80x24 env=[SCAN=fix] steps=[DOWN|DOWN|ENTER|f]

```text
--- [80x24] start (cursor HIDDEN r15c0 scrolled=0)

⋆   ✦   ⋆    _   _       _  ___  _           _  ___ ___  _
 ╲ ╱ ╲ ╱    |   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
  ⋆   ⋆     |_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
            Map your Claude setup · 0.1.0
            github.com/esharif20/constellation

  ➤ 1. Scan     Read ~/.claude, build or refresh the scan
    2. Open     The graph of your setup, in the browser
    3. Analyze  Rank what loads at the start of every session
    4. Find     Say what a forgotten skill does
    5. Clean    A cleanup checklist with verdicts
    6. Status   Health, this week, what went quiet

  ↑↓ | Enter | M More | V Version | U Update | Q Quit

--- [80x24] DOWN (cursor HIDDEN r15c0 scrolled=0)

⋆   ✦   ⋆    _   _       _  ___  _           _  ___ ___  _
 ╲ ╱ ╲ ╱    |   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
  ⋆   ⋆     |_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
            Map your Claude setup · 0.1.0
            github.com/esharif20/constellation

    1. Scan     Read ~/.claude, build or refresh the scan
  ➤ 2. Open     The graph of your setup, in the browser
    3. Analyze  Rank what loads at the start of every session
    4. Find     Say what a forgotten skill does
    5. Clean    A cleanup checklist with verdicts
    6. Status   Health, this week, what went quiet

  ↑↓ | Enter | M More | V Version | U Update | Q Quit

--- [80x24] DOWN (cursor HIDDEN r15c0 scrolled=0)

⋆   ✦   ⋆    _   _       _  ___  _           _  ___ ___  _
 ╲ ╱ ╲ ╱    |   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
  ⋆   ⋆     |_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
            Map your Claude setup · 0.1.0
            github.com/esharif20/constellation

    1. Scan     Read ~/.claude, build or refresh the scan
    2. Open     The graph of your setup, in the browser
  ➤ 3. Analyze  Rank what loads at the start of every session
    4. Find     Say what a forgotten skill does
    5. Clean    A cleanup checklist with verdicts
    6. Status   Health, this week, what went quiet

  ↑↓ | Enter | M More | V Version | U Update | Q Quit

--- [80x24] ENTER (cursor HIDDEN r11c0 scrolled=0)
Analyze Setup  (1,210 tokens at session start)
What loads at the start of every session, biggest first:  6 Items

▶  1. ████████████████████████  35% | deploy        420 tok
   2. ████████████████████████  34% | ship          415 tok
   3. ██████████                15% | release-notes 180 tok
   4. █████                      8% | review         95 tok
   5. ███                        5% | reviewer       60 tok
   6. ██                         3% | changelog      40 tok

↑↓→ | Enter | R Refresh | O Open | P Preview | F File | Esc/Q Back

--- [80x24] f (cursor on r5c43 scrolled=0)
  ▸ deploy
  Esc to cancel

  skills/deploy/SKILL.md

  Press Enter or Esc to return (q to quit)

final exit None
--- [80x24] after ctrl-c (cursor HIDDEN r11c0 scrolled=0)
Analyze Setup  (1,210 tokens at session start)
What loads at the start of every session, biggest first:  6 Items

▶  1. ████████████████████████  35% | deploy        420 tok
   2. ████████████████████████  34% | ship          415 tok
   3. ██████████                15% | release-notes 180 tok
   4. █████                      8% | review         95 tok
   5. ███                        5% | reviewer       60 tok
   6. ██                         3% | changelog      40 tok

↑↓→ | Enter | R Refresh | O Open | P Preview | F File | Esc/Q Back

```

## 54x24 env=[SCAN=fix] steps=[DOWN|DOWN|DOWN|DOWN|DOWN|ENTER]

```text
--- [54x24] start (cursor HIDDEN r15c0 scrolled=0)

 _   _       _  ___  _           _  ___ ___  _
|   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
|_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
Map your Claude setup · 0.1.0
github.com/esharif20/constellation

  ➤ 1. Scan     Read ~/.claude, build or refresh the …
    2. Open     The graph of your setup, in the brows…
    3. Analyze  Rank what loads at the start of every…
    4. Find     Say what a forgotten skill does
    5. Clean    A cleanup checklist with verdicts
    6. Status   Health, this week, what went quiet

  ↑↓ | Enter | M More | V Version | U Update | Q Quit

--- [54x24] DOWN (cursor HIDDEN r15c0 scrolled=0)

 _   _       _  ___  _           _  ___ ___  _
|   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
|_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
Map your Claude setup · 0.1.0
github.com/esharif20/constellation

    1. Scan     Read ~/.claude, build or refresh the …
  ➤ 2. Open     The graph of your setup, in the brows…
    3. Analyze  Rank what loads at the start of every…
    4. Find     Say what a forgotten skill does
    5. Clean    A cleanup checklist with verdicts
    6. Status   Health, this week, what went quiet

  ↑↓ | Enter | M More | V Version | U Update | Q Quit

--- [54x24] DOWN (cursor HIDDEN r15c0 scrolled=0)

 _   _       _  ___  _           _  ___ ___  _
|   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
|_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
Map your Claude setup · 0.1.0
github.com/esharif20/constellation

    1. Scan     Read ~/.claude, build or refresh the …
    2. Open     The graph of your setup, in the brows…
  ➤ 3. Analyze  Rank what loads at the start of every…
    4. Find     Say what a forgotten skill does
    5. Clean    A cleanup checklist with verdicts
    6. Status   Health, this week, what went quiet

  ↑↓ | Enter | M More | V Version | U Update | Q Quit

--- [54x24] DOWN (cursor HIDDEN r15c0 scrolled=0)

 _   _       _  ___  _           _  ___ ___  _
|   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
|_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
Map your Claude setup · 0.1.0
github.com/esharif20/constellation

    1. Scan     Read ~/.claude, build or refresh the …
    2. Open     The graph of your setup, in the brows…
    3. Analyze  Rank what loads at the start of every…
  ➤ 4. Find     Say what a forgotten skill does
    5. Clean    A cleanup checklist with verdicts
    6. Status   Health, this week, what went quiet

  ↑↓ | Enter | M More | V Version | U Update | Q Quit

--- [54x24] DOWN (cursor HIDDEN r15c0 scrolled=0)

 _   _       _  ___  _           _  ___ ___  _
|   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
|_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
Map your Claude setup · 0.1.0
github.com/esharif20/constellation

    1. Scan     Read ~/.claude, build or refresh the …
    2. Open     The graph of your setup, in the brows…
    3. Analyze  Rank what loads at the start of every…
    4. Find     Say what a forgotten skill does
  ➤ 5. Clean    A cleanup checklist with verdicts
    6. Status   Health, this week, what went quiet

  ↑↓ | Enter | M More | V Version | U Update | Q Quit

--- [54x24] DOWN (cursor HIDDEN r15c0 scrolled=0)

 _   _       _  ___  _           _  ___ ___  _
|   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
|_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
Map your Claude setup · 0.1.0
github.com/esharif20/constellation

    1. Scan     Read ~/.claude, build or refresh the …
    2. Open     The graph of your setup, in the brows…
    3. Analyze  Rank what loads at the start of every…
    4. Find     Say what a forgotten skill does
    5. Clean    A cleanup checklist with verdicts
  ➤ 6. Status   Health, this week, what went quiet

  ↑↓ | Enter | M More | V Version | U Update | Q Quit

--- [54x24] ENTER (cursor on r23c43 scrolled=7)

Top findings
  - deploy (skill): Does the same job as ship; neither
 has been used (saves 420)
  - reviewer (agent): Only hands off to review (saves
60)

Hooks and triggers
  ✓ No clashes
  ✓ 1 hook, 0 able to block a prompt
  ✓ 0 skills never fire, 0 fire greedily

MCP and connectors
  0 MCP servers, 0 connectors (tool schemas are not me
asured)

  ! 2 scan warnings in the saved scan
Next: constellation cost
Weekly state of your setup
Not enough history yet: this is the first scan recorde
d for this setup. Scan again later and this page compa
res the two.

  Press Enter or Esc to return (q to quit)

final exit None
--- [54x24] after ctrl-c (cursor HIDDEN r15c0 scrolled

 _   _       _  ___  _           _  ___ ___  _
|   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
|_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
Map your Claude setup · 0.1.0
github.com/esharif20/constellation

    1. Scan     Read ~/.claude, build or refresh the …
    2. Open     The graph of your setup, in the brows…
    3. Analyze  Rank what loads at the start of every…
    4. Find     Say what a forgotten skill does
    5. Clean    A cleanup checklist with verdicts
  ➤ 6. Status   Health, this week, what went quiet

  ↑↓ | Enter | M More | V Version | U Update | Q Quit

```

## 80x24 env=[SCAN=fix,NO_COLOR=1] steps=[DOWN|DOWN|ENTER]

```text
--- [80x24] start (cursor HIDDEN r15c0 scrolled=0)

⋆   ✦   ⋆    _   _       _  ___  _           _  ___ ___  _
 ╲ ╱ ╲ ╱    |   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
  ⋆   ⋆     |_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
            Map your Claude setup · 0.1.0
            github.com/esharif20/constellation

  ➤ 1. Scan     Read ~/.claude, build or refresh the scan
    2. Open     The graph of your setup, in the browser
    3. Analyze  Rank what loads at the start of every session
    4. Find     Say what a forgotten skill does
    5. Clean    A cleanup checklist with verdicts
    6. Status   Health, this week, what went quiet

  ↑↓ | Enter | M More | V Version | U Update | Q Quit

--- [80x24] DOWN (cursor HIDDEN r15c0 scrolled=0)

⋆   ✦   ⋆    _   _       _  ___  _           _  ___ ___  _
 ╲ ╱ ╲ ╱    |   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
  ⋆   ⋆     |_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
            Map your Claude setup · 0.1.0
            github.com/esharif20/constellation

    1. Scan     Read ~/.claude, build or refresh the scan
  ➤ 2. Open     The graph of your setup, in the browser
    3. Analyze  Rank what loads at the start of every session
    4. Find     Say what a forgotten skill does
    5. Clean    A cleanup checklist with verdicts
    6. Status   Health, this week, what went quiet

  ↑↓ | Enter | M More | V Version | U Update | Q Quit

--- [80x24] DOWN (cursor HIDDEN r15c0 scrolled=0)

⋆   ✦   ⋆    _   _       _  ___  _           _  ___ ___  _
 ╲ ╱ ╲ ╱    |   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
  ⋆   ⋆     |_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
            Map your Claude setup · 0.1.0
            github.com/esharif20/constellation

    1. Scan     Read ~/.claude, build or refresh the scan
    2. Open     The graph of your setup, in the browser
  ➤ 3. Analyze  Rank what loads at the start of every session
    4. Find     Say what a forgotten skill does
    5. Clean    A cleanup checklist with verdicts
    6. Status   Health, this week, what went quiet

  ↑↓ | Enter | M More | V Version | U Update | Q Quit

--- [80x24] ENTER (cursor HIDDEN r11c0 scrolled=0)
Analyze Setup  (1,210 tokens at session start)
What loads at the start of every session, biggest first:  6 Items

▶  1. ████████████████████████  35% | deploy        420 tok
   2. ████████████████████████  34% | ship          415 tok
   3. ██████████                15% | release-notes 180 tok
   4. █████                      8% | review         95 tok
   5. ███                        5% | reviewer       60 tok
   6. ██                         3% | changelog      40 tok

↑↓→ | Enter | R Refresh | O Open | P Preview | F File | Esc/Q Back

final exit None
--- [80x24] after ctrl-c (cursor HIDDEN r15c0 scrolled=0)

⋆   ✦   ⋆    _   _       _  ___  _           _  ___ ___  _
 ╲ ╱ ╲ ╱    |   | | |\| |_   |  |_  |   |   |_|  |   |  | | |\|
  ⋆   ⋆     |_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |
            Map your Claude setup · 0.1.0
            github.com/esharif20/constellation

    1. Scan     Read ~/.claude, build or refresh the scan
    2. Open     The graph of your setup, in the browser
  ➤ 3. Analyze  Rank what loads at the start of every session
    4. Find     Say what a forgotten skill does
    5. Clean    A cleanup checklist with verdicts
    6. Status   Health, this week, what went quiet

  ↑↓ | Enter | M More | V Version | U Update | Q Quit

```
