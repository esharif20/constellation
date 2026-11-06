# Constellation: overview

Short on purpose. Detail lives in `README.md`, `docs/plan-tracker.md` and the code.

## 1. Purpose

A Claude Code setup grows: skills, agents, commands, hooks, MCP servers, plugins. Nobody knows what it costs at
session start, what overlaps, or what they never use. Constellation scans the setup and shows it as a map plus
plain answers, without sending your files anywhere.

## 2. What it does

1. **Scan** `~/.claude` locally: Items (skill, agent, command, hook, MCP server, plugin), their sizes and their use
   (counted from transcripts, never read for content).
2. **Group** Items into clusters and find Overlaps (pairs doing the same job).
3. **Judge** each Item: keep, review, redundant, could go, or not enough history.
4. **Show** it: a browser map (Inspector, Brief, Ask, Find) and a terminal menu and commands.
5. **Never change** your setup. It writes checklists you act on yourself.

## 3. The core

| Piece | Job |
|---|---|
| `claude_code.py` | Reads the config into Items |
| `redact.py` | The privacy gate: nothing is saved, shown or sent without passing it |
| `grouping.py` | Clusters Items (words, optional local embeddings, plugin, relations) |
| `verdicts`, `habits`, `costs` | Judge use and cost from local history |
| `server.py` | Local FastAPI serving the scan to the React app |
| `cli.py` and friends | Terminal commands and menu |

Rule that shapes everything: only kinds, names and descriptions leave the machine, after redaction, and only if
you give a key. Offline must still be useful. Paid calls happen only for new or changed Items.

## 4. Features and why

| Feature | What it does | Why |
|---|---|---|
| Cost view | Session-start tokens by plugin | The hidden bill is the main pain |
| Verdicts | Keep / review / redundant, with confidence | Tells you what is safe to drop |
| Overlaps | Exact duplicates, thin wrappers, similar pairs | Twins waste tokens and confuse triggers |
| Find | Search skills by what they do, with last use and cost | You forget what you installed |
| Safe-removal preview | What refers to an Item and what loses coverage | Removing blind breaks things |
| Expansion | Lists tools of a local MCP server | MCP cost is invisible otherwise |
| Clean checklist | Private to-do, never edits settings | Safe by construction |
| Public Snapshot | Redacted read-only export, canned Ask answers | Share a map without sharing yourself |
| Terminal menu | Same engine, no browser | Faster, scriptable |

## 5. Redaction, step by step (including Shannon entropy)

`redact(text, known)` applies layers in order. Each catches what the previous one cannot.

1. **Known formats.** Regexes for GitHub, `sk-`, AWS and Slack keys and `Bearer` tokens. Cheap and exact.
2. **Secret-sounding names.** `--token X`, `API_KEY=X`, `"client_secret": "X"`. The value is hidden whatever it looks like.
3. **Known values.** Secrets read from your own config, matched anywhere they appear, including URL-encoded and
   base64 forms. Only values of 8+ characters (shorter ones match normal words). Overlaps are merged, then replaced once.
4. **Entropy backstop** for secrets with no format, name or known value. Steps:
   - Take runs of 32+ characters from `[A-Za-z0-9+/_=-]`.
   - Skip unless it has both letters and digits (paths and words look the same otherwise).
   - Skip if over 80% is lowercase, `-` or `_` (a kebab or snake name, not a secret).
   - Skip if over 30% of neighbouring characters are consecutive (`abc…`, `321…`).
   - Compute **Shannon entropy**: `H = -Σ p·log2(p)` over character frequencies, in bits per character.
     A random secret spreads over many characters, so H is high; a repetitive or wordlike string is low.
   - Redact if H is at least 3.0 for hex or 4.0 otherwise. These are set a little below common tools (3.0 / 4.5) so it fails closed.

Known limit, accepted: letters-only or digits-only secrets, and secrets under 8 characters, are not caught by the
entropy step. A false hit costs only a slightly worse label; a miss would leak, so the thresholds lean strict.

## 6. Problems we hit and how we solved them

**Privacy and safety**
- *Secrets hid in names and ids.* Fixed by `redact_tree` over the whole saved scan, with unique ids (stable keyed hash) so redaction cannot merge two Items.
- *False `[REDACTED]` on ordinary words.* Cause: secrets guessed from skill bodies, plus re-redacting markers. Fixed with the 8-character floor, a single-pass matcher and no guessing.
- *Overlapping secrets leaked a tail.* The matcher now merges spans before replacing.
- *A cloned repo could trick `scan` into overwriting a file or being trusted as your scan.* Writes now use a fresh private temp file, and `./constellation.json` is trusted only if it is your own mode-600 file.
- *Expansion starts your own MCP servers.* Tested against real crashing, hanging and flooding servers; failures return a fixed message and never raw output.

**Quality of the map**
- *Everything landed in one "Other" cluster.* New grouping engine: combined similarities, a 20% size cap, minimum sizes and categories. Works without the local model ("words only").
- *Weak cluster names* ("Sort Involve"). Filler-word stoplist and shared-bigram names. Still weak for hook events: next fix.
- *Verdicts need history.* Short history honestly shows "not enough history" instead of guessing.

**Experience**
- *Terminal hard to navigate, ugly find output.* Mole-style menu with Esc back, cards for Find, progress bar, and real pseudo-terminal tests that caught wrapping, resize and 40-column bugs.
- *Graph drag felt wrong.* Obsidian-style springs: the star follows, neighbours stretch, everything returns home. Under repair after a regression.
- *UI panels stuck or duplicated.* A `Presence` timer bug fixed with a browser check.

**Process**
- *Mutation testing too costly everywhere.* Decision: core backend logic gets per-function zero-survivor runs; UI and terminal glue get exact-output, browser and pty tests. Reports say which is which.
- *Parallel agents collided* on one lock, one tracker file and some commands. Lock protocol, keep-both merges, and one merge at a time with full gates.
- *Hangs when piping long test runs.* Redirect output to a file.

## 7. Not done

PyPI publish, deployed Snapshot and landing page, touch-device checks, paid Overlap verifier score, hook-cluster naming.
