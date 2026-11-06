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

## 6. Timeline: what we built and what went wrong

About 460 commits over four days (3 to 6 November 2026), built by parallel agents with a merge-and-gate loop
(ruff, mypy, tests, mutation on core logic, privacy review) before each push.

**Day 1, 3 Nov: the skeleton and Overlaps.**
- Built: scan skills, agents and local MCP servers into Items; the redaction gate; Overlaps in layers (identical text, thin wrappers, embeddings, then a model labels each pair); CLI with a dry run that prints exactly what would be sent; first graph app.
- Problem: privacy had to hold before any feature. Decision: only kinds, names and descriptions leave, after redaction; offline must still work.

**Day 2, 4 Nov: usage, cost and the first UI polish.**
- Built: usage read from transcripts, session-start cost, label cache and offline mode, MCP servers from all scopes, the local Ask panel (free, local search), the Snapshot export, design pass on the graph.
- Problems: the usage reader dropped data on bad lines (fixed: keep reading, count and report skips); Snapshot leaked in places (scrub gaps closed after review); the first search was too exact (made forgiving).

**Day 3, 5 Nov: the Inspector, Brief and Ask grow up.**
- Built: redesigned Inspector, per-project usage, scope filter, what-if removal, Explain card, trigger audit, readable chat answers, resumable scan, diff between scans, lenses.
- Problems: Ask answers were unreadable walls (new structured reply format); per-project usage touched sensitive data (privacy-reviewed, hashes never leave); agents' branches kept colliding (keep-both merges, one merge at a time).

**Day 4, 6 Nov: verdicts, packaging, terminal, then hardening.**
- Built, morning: habit ledger and shared verdict engine, weekly report, Sky background, panel motion, click-outside dismissal, package and installer, grouped help and completions.
- Problems found by using it: false `[REDACTED]` on ordinary words (stopped guessing secrets from skill bodies); the saved scan was not fully redacted and ids could collide (whole-scan redaction, unique ids); clustering put almost everything in "Other" (new grouping engine with a 20% cap, then better names); the terminal was hard to navigate and `find` output unreadable (Mole-style menu with Esc back, cards, progress bar).
- Built, afternoon: safe-removal preview, Expansion (list an MCP server's tools), profile, purge, status, find filters, advise, Obsidian-style elastic drag, Snapshot with pre-run Expansions and canned Ask.
- Problems: CI failed on an unused import I had reported clean (fixed, gates re-run); the repo went public, so every screenshot and fixture was audited for real data (none found); a privacy review found a symlink overwrite and an untrusted `./constellation.json` (fixed); real pty tests found wrapping, resize and 40-column bugs; mutation runs became a bottleneck on one shared lock (rule: core logic only); the elastic drag regressed after a browser fix and is being repaired.

## 7. Not done

PyPI publish, deployed Snapshot and landing page, touch-device checks, paid Overlap verifier score, hook-cluster naming.
