# Install and terminal experience (Mole-style)

Status: research and design, 2026-11-06. Nothing here is built yet. Owner decisions are in section 7.

Goal: a stranger with a Mac and Claude Code types one line, gets a `constellation` command, and the terminal feels
like Mole (`mo`): one menu, a few strong verbs, previews before anything is written, no surprises. No landing page.

## 1. What Mole does (studied 2026-11-06)

Source: `github.com/tw93/Mole` (74k stars, GPL-3.0, release `V1.69.0` on 2026-11-04), read through `gh api`
(README, `install.sh`, `mole`, `lib/manage/update.sh`, `bin/completion.sh`, `.github/workflows/release.yml`).

### Install

| Channel | Command | Notes |
|---|---|---|
| Homebrew (core, not a tap) | `brew install mole` | CI job `update-homebrew-core` bumps the formula on stable tags only |
| Script | `curl -fsSL https://raw.githubusercontent.com/tw93/mole/main/install.sh \| bash` | needs the repo public |
| Pinned script | `... \| bash -s -- 1.51.0` or `-- main` | any tag, with or without `V` |
| User prefix | `... \| bash -s -- --prefix "$HOME/.local/bin"` | default `/usr/local/bin` may ask for sudo |
| Nix flake | `nix profile install github:tw93/mole/main#mole` | `mo update`/`mo remove` leave Nix installs alone |
| AI agent | "Install Mole by reading .../llms.txt", or `npx skills add tw93/Mole`, or `/plugin marketplace add tw93/Mole` | ships a Claude Code plugin and skill |

`install.sh` (1,900 lines of bash): `set -euo pipefail`; refuses to run under sudo ("requests administrator access
when needed"); downloads the source tarball for a tag plus Go binaries from GitHub Releases; checks each asset against
`SHA256SUMS` and verifies the Sigstore build-provenance attestation (`actions/attest-build-provenance`); uses
`mktemp` files and an install lock directory with owner/mode/ACL checks; re-runs `mo --version` and `mo --help` to
verify the install. The README also names the only official sources and lists look-alike scam domains.

### Commands and UX

- `mo` with no args on a TTY: full-screen menu, 5 options (Clean, Uninstall, Optimize, Analyze, Status), arrow keys
  or digits `1`-`5`, Enter to run, a controls line at the bottom (help, version, Touch ID, "update available").
  Drawn with raw ANSI (`\033[H`, `\033[2K`) and a `read_key` helper; the terminal is restored on interrupt.
- Verbs: `clean`, `uninstall`, `optimize`, `analyze`, `status`, `purge`, `installer`, `slim`, `touchid`,
  `completion`, `update` (`--nightly`), `remove`, `history` (`--json`), `--help`, `--version`.
- Every destructive verb has `--dry-run`; `--debug` adds logs; `--whitelist` opens a checklist that persists to
  `~/.config/mole/whitelist`; if the whitelist cannot be read the command stops rather than run without it.
- Output is a sectioned report: a title, one context line, `➤` group headers, `✓` done, `◎` skipped with a reason,
  then a ruled summary ("Removed: 4.5GB · 97 items"). Lists use `➤ ●` cursors.
- Machine output: `--json` on analyze/status/history; status switches to JSON automatically when piped.
- Safety: never run with sudo; Trash by default where possible; an operations log (`mo history`, opt out with
  `MO_NO_OPLOG=1`); timeouts tunable by env vars. No telemetry is mentioned anywhere; the only network calls are
  the update check (GitHub releases API / Homebrew) and downloads.
- `mo update` detects the install channel (brew, script, Nix) and **runs** the upgrade itself (it pipes `install.sh`
  from `main` into bash). `mo remove` deletes Mole. `mo completion` writes bash/zsh/fish completion generated from
  one command table (`lib/core/commands.sh`).

### Repo layout

`mole` (entry + menu), `mo` (alias), `bin/<verb>.sh` (one script per verb), `lib/{core,ui,clean,manage,...}`,
`cmd/` + `internal/` (Go for the heavy TUIs), `tests/` (~100 bats files), `install.sh`, `Makefile`, `SECURITY.md`,
`SECURITY_AUDIT.md`, `.gitleaks.toml`, workflows `test`, `check`, `codeql`, `secrets`, `release` (on tag: build,
`SHA256SUMS`, attest, GitHub Release, bump Homebrew core).

### README shape

Centered title + one-sentence pitch + badges (stars, version, licence) -> one big screenshot (`docs/img/big-mole.png`)
-> Features (6 bullets) -> Quick Start (brew, script, agent; a commented command table) -> "Other install options" in a
`<details>` -> Safety -> Configuration -> Features in Detail (each verb with a real-looking text transcript in a
`text` block) -> Community -> Support -> License. Transcripts in code blocks do most of the selling; there is no GIF.

### Copy / do not copy

Copy: the no-args menu; few verbs with obvious names; `--dry-run` on every writer; a whitelist (our pins); text
transcripts in the README; `--json` everywhere; completions generated from one table; a channel-aware `update`;
"only these places distribute it"; refuse sudo.

Do not copy: a 1,900-line installer (we have no binaries; uv does the hard part); `update` that installs by piping a
script from `main` (we print the command instead); Homebrew core (needs notability and a maintained formula);
the Go TUI split.

## 2. Distribution for a uv app with a built frontend

### Facts that shape it

- **The PyPI name `constellation` is taken** (v1.5.0, "Deploy scripts for constellations of docker containers").
  Free on 2026-11-06 (PyPI JSON API returns 404): `claude-constellation`, `constellation-cli`, `cc-constellation`,
  `constellation-map`. A 404 is not a guarantee (PyPI also blocks names too close to existing ones), so register by
  uploading `0.1.0` early. The distribution name can differ from the command: dist `claude-constellation`,
  command `constellation`, import `constellation`. Then `uvx constellation` would fetch the **wrong** package, so docs
  must say `uvx --from claude-constellation constellation` or `uv tool install claude-constellation`.
- **The build backend is `uv_build`.** Per uv's docs it puts the whole module directory into the sdist and wheel and
  does not consult `.gitignore`; only `__pycache__`/`*.pyc` and configured excludes are dropped. So a wheel built after
  `npm run build` already contains `src/constellation/static/`. The risk is the opposite one: building without the
  bundle ships a wheel that cannot `open`. The release script must fail if `static/index.html` is missing.
- **`open` needs the `app` extra** (fastapi, uvicorn, mcp). The map is the product, so move `app` into the base
  dependencies; keep `local` (fastembed, heavy) and `llm` (anthropic) optional. Install line stays one package.
- `requires-python = ">=3.13"`: uv downloads a managed Python itself; pipx needs a 3.13 already present. Favour uv.
- Demo data lives in `docs/design/demo.json` (92 KB, invented), outside the package. `open demo` needs a copy inside
  the package, e.g. `src/constellation/demo/demo.json`, kept in sync by a test.
- Analysis verbs (doctor, cost, unused, twins, why, hooks, clashes, triggers, explain, ask, clean, share) are on
  `claude/cli-commands` (#78) and not on `main` yet; the menu and help work below assume that branch lands first.
  `cli_reports.Style` there already handles colour, `NO_COLOR` and width; reuse it.

### Options, ordered by value / effort

| # | Channel | What a stranger types | Needs public | Cost | Effort | Verdict |
|---|---|---|---|---|---|---|
| 1 | PyPI wheel with bundle inside | `uv tool install claude-constellation` | PyPI only | free | low | **do first** |
| 2 | Same, no install | `uvx --from claude-constellation constellation open demo` | PyPI only | free | none | document |
| 3 | pipx | `pipx install claude-constellation` | PyPI only | free | none | document |
| 4 | GitHub Release with wheel + `SHA256SUMS` | `uv tool install https://github.com/.../claude_constellation-0.2.0-py3-none-any.whl` | a public repo | free | low | do with #1 |
| 5 | `install.sh` one-liner | `curl -LsSf <url>/install.sh \| sh` | the file's host | free | low | optional |
| 6 | Homebrew tap | `brew install esharif20/tap/constellation` | a public `homebrew-tap` repo | free | **high** | later or never |

Why Homebrew is high effort: a Python formula must list every transitive dependency as a `resource` with its
sha256 (`brew update-python-resources` helps), and langgraph + fastapi + mcp pull in dozens. Each release means
regenerating it and fixing wheels that need compiling. A "formula that runs `uv tool install`" is against Homebrew's
rules. For a solo project, PyPI covers brew users already (`brew install uv` then option 1).

### `install.sh` (if wanted)

It only saves typing "install uv first", so keep it about 40 lines of POSIX `sh`:

```sh
#!/bin/sh
# Installs Constellation with uv. No sudo, writes only under $HOME. Read me before piping me into sh.
set -eu
VERSION="${CONSTELLATION_VERSION:-0.2.0}"   # pinned; bumped by the release script
PKG="claude-constellation"
[ "$(id -u)" -eq 0 ] && { echo "Run without sudo; nothing here needs root." >&2; exit 1; }
if ! command -v uv >/dev/null 2>&1; then
  echo "uv is not installed. Install it with the official installer, then rerun:"
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh     # or: brew install uv"
  exit 1                                       # do not chain a second remote script silently
fi
uv tool install --force "${PKG}==${VERSION}"
constellation --version && constellation doctor --env
```

Safety rules: no sudo; pinned version (PyPI files are immutable and uv checks the sha256 that the index publishes,
so a pinned version is the checksum); do not auto-run the uv installer (print it; a prompt can be added with
`< /dev/tty` but costs complexity); wrap the body in a function called on the last line so a truncated download
runs nothing; `shellcheck` it. Hosting: `raw.githubusercontent.com` needs a public repo; GitHub Pages also needs a
public repo on the free plan; a release asset URL needs a public repo too. With a private repo there is no free host,
so the script only makes sense after going public. PyPI alone works with the repo private.

### What must be public, and how to check before flipping

Free paths, cheapest first:

1. **PyPI only, repo stays private.** Strangers can install; they cannot read source or file issues. A wheel is
   just a zip, so the shipped Python and the built JS are readable by anyone anyway. The PyPI project page shows the
   README, so it must not link to private URLs.
2. **Public mirror repo** (`constellation` public, cut fresh): push a single squashed commit of a reviewed tree, so
   no history is exposed. Keeps the private repo for messy work. Costs: two remotes to keep in sync.
3. **Flip the existing repo public.** Bonus: GitHub Actions minutes are free for public repos, which removes the
   money rule that blocks CI today. Cost: every branch, tag and commit since day one becomes public, including the
   170+ `claude/*` and `codex/*` branches (local count; check what is pushed) and the closed issues.

Licence: MIT (shortest, most common for portfolio tools) or Apache-2.0 (adds a patent grant, longer NOTICE rules).
Recommendation MIT. Mole uses GPL-3.0, which forces derivatives to stay open; unusual for a portfolio piece. Add
`LICENSE` and `license = "MIT"` + `license-files = ["LICENSE"]` in `pyproject.toml`.

Pre-public review (owner runs these in a fresh clone; they read only git history, not `~/.claude` or real scans):

```sh
git clone --mirror <private-url> /tmp/review.git && cd /tmp/review.git
# 1. files that should never have been committed, in any branch, ever
git log --all --diff-filter=A --name-only --format= | sort -u \
  | grep -Ei '(^|/)\.env|constellation(-real)?\.json$|\.sqlite$|history\.json|pins\.json|habits|cleanup\.md|\.pem$|id_rsa'
# 2. secret-shaped strings anywhere in history
git log --all -p | grep -nE 'sk-ant-[A-Za-z0-9_-]{10,}|ghp_[A-Za-z0-9]{20,}|github_pat_|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY' | head
# 3. personal paths and identifiers that would show the real setup
git log --all -p | grep -nE '/Users/[a-z]+/|eshansharif|@gmail\.com' | grep -v 'pyproject.toml' | head -50
# 4. large or binary blobs (screenshots of the real map?)
git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectsize) %(rest)' \
  | awk '$1=="blob" && $2>500000' | sort -k2 -n
# 5. optional, thorough: brew install gitleaks && gitleaks detect --source . --log-opts="--all"
```

Also check by eye: `docs/design/screenshots/` (demo data only?), `tests/fixtures/` (invented?), `docs/plans/` and
`CLAUDE.md`/`AGENTS.md` (fine to publish, but they mention local paths), issue and PR text (public with the repo).
If step 1-3 find anything real, use option 2 (fresh squashed mirror) instead of rewriting history.

## 3. CLI UX to match Mole

### Name and alias

`constellation` stays the command. **No `cs` alias**: `cs` is the Coursier (Scala) launcher, installed by many JVM
users, and a two-letter name collides easily. If a short name is wanted later, `cnst` is free on this machine; users
can also `alias cs=constellation`. Not worth shipping a second entry point now.

### No-args menu

`constellation` with no args and both stdin and stdout on a TTY opens the menu; otherwise it prints `--help` (so
scripts and pipes never hang). Exactly Mole's model:

```text
Constellation 0.2.0 · your Claude Code setup, mapped

  ➤ 1  Analyze      what costs context, what is unused, what clashes
    2  Doctor       one-screen health of your setup and this install
    3  Clean        build a cleanup checklist (nothing is deleted)
    4  Weekly       what changed since last week
    5  Open map     the interactive graph in your browser
    6  Update       check for a newer version

  ↑↓ or 1-6 · Enter run · h help · q quit         last scan: 2 days ago
```

- Analyze runs `scan --offline` if there is no scan or it is older than a day (asks first, shows what it reads), then
  prints `doctor` + `cost` + `unused` summaries with "next: `constellation why <name>`" hints.
- Clean runs `clean` (the checklist) and offers to open it; it never deletes Items. Pins act as the whitelist.
- Each entry calls the same function as its subcommand; the menu has no logic of its own.
- Implementation: stdlib `termios` + `tty` raw mode, read `\x1b[A`/`\x1b[B`, digits, `q`, Enter; always restore the
  terminal in `finally` and on `KeyboardInterrupt` (exit 130). Where `termios` is missing (Windows) fall back to a
  numbered `input()` prompt. About 80 lines in a new `menu.py`.

### Dependencies for "rich-looking" output: stdlib only

| Option | Size / cost | Verdict |
|---|---|---|
| `rich` | ~1 MB + `pygments`, `markdown-it`; slower startup | no: Style already does colour, tables and width |
| `textual` | full TUI framework | no: the browser map is the rich view |
| `questionary`/`prompt_toolkit` | ~1 MB, arrow-key prompts | no: one menu and one checklist do not justify it |
| stdlib ANSI + `termios` | 0 | **yes** |

Reasons: zero new install weight, startup stays fast, output stays deterministic for the golden tests in
`tests/golden/cli/`, and mutation testing does not wander into a vendored renderer. A spinner is a 15-line thread that
writes `⠋⠙⠹…` to stderr only when stderr is a TTY. Respect `NO_COLOR`, `TERM=dumb`, and `--no-color`.

### Command set (existing kept, new marked)

| Command | Writes? | `--dry-run` | Notes |
|---|---|---|---|
| `scan` | constellation.json, history, caches | yes (exists: shows what would be sent) | extend: also list files it would write |
| `open [file\|demo]` | no (starts a local server) | n/a | **new**: `open demo` serves the packaged demo |
| `doctor` | no | n/a | **extend**: Environment section, below |
| `cost` `unused` `twins` `why` `hooks` `clashes` `triggers` `explain` `ask` `assess` `weekly` `diff` `delta` `expand` `find` | no | n/a | read-only; `--json` on all |
| `clean` | checklist file | **add** | prints the checklist to stdout instead of writing |
| `share` / `export` | files under `--out` | **add** | lists every file and byte count it would write |
| `preview --out` | one file | **add** | |
| `pin` / `unpin` (if exposed) | pins.json | **add** | the whitelist; `clean` and suggestions skip pinned Items |
| `update` **new** | no | n/a | see below |
| `uninstall` **new** | no | n/a | prints steps only |
| `completion bash\|zsh\|fish` **new** | no (prints to stdout) | n/a | user redirects into their rc file |
| `--version` **new** | no | n/a | from `importlib.metadata.version` |

Rule (and a test): every subcommand that can write accepts `--dry-run`, and with it touches no file. One parametrised
test over the parser finds writers by a `writes=True` marker set where the parser is built.

### Help

Every subparser gets `description` (one sentence) and an `epilog` with 2-3 real examples, using
`RawDescriptionHelpFormatter`:

```text
$ constellation clean --help
usage: constellation clean [--dry-run] [--out PATH] [--json]

Build a private cleanup checklist from the last scan. Nothing in your setup is changed.

examples:
  constellation clean --dry-run        # print the checklist, write nothing
  constellation clean --out ~/cleanup.md
```

Top-level `--help` groups verbs as Mole does: Look (doctor, cost, unused, ...), Act (clean, share, export),
Map (scan, open), Manage (update, uninstall, completion).

### Completions: hand-written generator, not argcomplete

`argcomplete` is another dependency and needs `register-python-argcomplete` in the user's rc file, and it runs Python
on every Tab. Instead `completion.py` walks the argparse parser (`_subparsers._group_actions[0].choices` and each
subparser's option strings) and prints a static script for bash, zsh or fish, like Mole's `bin/completion.sh` reading
one command table. A test renders all three and checks every subcommand name appears. Install hint printed with it:
`constellation completion zsh > ~/.zfunc/_constellation`.

### `update`

- The only network call outside `scan` and `ask`, made only when the user types `update` (no background checks, no
  banner by default). Sends nothing but a GET to `https://pypi.org/pypi/claude-constellation/json`; timeout 5 s;
  offline is a message, not a crash.
- Compares with the installed version, detects the channel from `sys.prefix` (`uv tool dir` -> uv tool, contains
  `pipx/venvs` -> pipx, `.venv` in a checkout -> dev) and **prints** the matching command:
  `uv tool upgrade claude-constellation` / `pipx upgrade claude-constellation` / `git pull && uv sync`.
  It never installs (deviation from Mole, chosen because a CLI that rewrites itself is a supply-chain step the user
  should see). Exit 0 up to date, 10 update available (so scripts can check), 1 check failed.

### `uninstall`

Prints, does not do:

```text
To remove Constellation:
  uv tool uninstall claude-constellation        # the command itself
Data it may have written (yours to keep or delete):
  ~/.cache/constellation/        caches, history, pins, habits (0700)
  ./constellation.json           and any other --out files you chose
  ~/.claude is never written by Constellation.
```

### `doctor`: add an Environment section

Runs even with no scan; never reads Item bodies; prints presence, never values:

| Check | Pass | Warn |
|---|---|---|
| Python | >= 3.13 | n/a (cannot start otherwise) |
| Install channel | uv tool / pipx / dev | unknown |
| Frontend bundle | `static/index.html` present | missing: `open` cannot work, reinstall |
| Extras | `fastapi` importable | `fastembed` / `anthropic` missing: "local embeddings / labels off" (info, not warn) |
| Cache dir | `~/.cache/constellation` is 0700, files 0600, writable | wrong mode or unwritable (warning, per the cost rule) |
| Last scan | history newer than 7 days | older or none: "run `constellation scan --offline`" |
| API key | `ANTHROPIC_API_KEY` set or not (yes/no only) | n/a, offline mode is fine |
| uv on PATH | yes | no (only matters for `update` advice) |

`doctor --env` shows only this section (used by `install.sh`).

### Exit codes

`0` success; `1` runtime error (unreadable file, server failed); `2` usage error or missing input (argparse and the
existing code already use 2); `10` `update` found a newer version; `130` interrupted (already used). `doctor --strict`
exits 1 on any warning, for scripts.

### Telemetry

None. No analytics, no crash reports, no update ping. Network happens only in `scan` (provider calls, shown and
priced first, none with `--offline`), `ask` with a key, and `update`. State this in the README and in `--help`.

## 4. Packaging work list (independent Sonnet slices)

Order: S1 then S2 are the critical path; S3-S5 can run in parallel after S1; S6 needs S2. Each slice follows AGENTS.md
gates (ruff, mypy, pytest, mutmut on changed pure modules, local only) and updates `docs/plan-tracker.md`.

**S1. Package contents and demo.** Owns `pyproject.toml`, `src/constellation/demo/`, `src/constellation/cli.py`
(`open demo`, `--version`), `tests/test_packaging.py`.
- Rename dist to the chosen name; command stays `constellation`. Move `app` deps to base. Add `license`, `urls`,
  `classifiers`, `keywords`. Copy `docs/design/demo.json` to `src/constellation/demo/demo.json`; a test asserts the two
  are identical. `open demo` resolves to it via `importlib.resources`.
- Tests: `constellation --version` prints the metadata version; `open demo --no-browser` resolves the packaged path
  (server start mocked as the existing open tests do).
- Accept: `uv build` produces a wheel whose `unzip -l` shows `constellation/static/index.html` and `constellation/demo/demo.json`.

**S2. Local release script and clean-install proof.** Owns `scripts/release-check.sh`, `CHANGELOG.md`, `docs/release.md`.
- Script: refuse a dirty tree; `npm --prefix frontend ci && npm --prefix frontend run build`; fail if
  `src/constellation/static/index.html` is missing; `rm -rf dist && uv build`; `unzip -l` asserts bundle + demo present
  and no `constellation.json`, `.env`, `*.sqlite`, `tests/` in the wheel; then in `mktemp -d` with
  `HOME=$tmp UV_TOOL_DIR=$tmp/tools UV_TOOL_BIN_DIR=$tmp/bin XDG_CACHE_HOME=$tmp/cache`:
  `uv tool install dist/*.whl`, run `constellation --help`, `constellation --version`, `constellation doctor --env`,
  `constellation open demo --no-browser` (start, `curl -fs localhost:<port>/` once, kill), then delete the temp dir.
  Writes `dist/SHA256SUMS` with `shasum -a 256`.
- Release checklist in `docs/release.md`: bump `version` in `pyproject.toml`, CHANGELOG entry (Keep a Changelog),
  run the script, `git tag vX.Y.Z`, `uv publish` with a PyPI token from the keychain (never in `.env` or the repo),
  `gh release create vX.Y.Z dist/* --notes-file` (if repo public). No CI involved.
- Accept: the script passes on a clean checkout and fails if the bundle step is skipped (try it once by hand).

**S3. Menu and output style.** Owns `src/constellation/menu.py`, `tests/test_menu.py`; touches `cli.py` dispatch only.
- Pure `step(state, key) -> state | action` for navigation (testable, mutation-friendly); thin raw-mode loop around it.
  Reuse `cli_reports.Style`. No-args + TTY opens it, else help.
- Tests: key sequences (down, down, enter -> "clean"; `q` -> quit; digits; bounds at top and bottom); non-TTY prints help;
  terminal restore called on exception (fake termios).
- Accept: screenshot-free check by eye in a real terminal; `constellation < /dev/null` prints help and exits 0.

**S4. Help, dry-run rule, exit codes, completions.** Owns `cli.py` parser text, `src/constellation/completion.py`,
`tests/test_cli_contract.py`.
- Descriptions + epilogs with examples on every subparser; grouped top-level help; `--dry-run` on every writer;
  `completion bash|zsh|fish`.
- Tests: every subparser has an epilog containing "examples:"; every `writes=True` command run with `--dry-run` in a temp
  dir leaves it unchanged; each completion script names every subcommand; `bash -n` / `zsh -n` on the output if present.
- Accept: `constellation <verb> --help` shows examples for all verbs.

**S5. `update`, `uninstall`, `doctor --env`.** Owns `src/constellation/selfcheck.py` (pure checks taking paths and an
injected fetch), `tests/test_selfcheck.py`; adds the subcommands in `cli.py`.
- Tests: version compare edge cases (equal, newer, pre-release, malformed JSON, timeout); channel detection from fake
  prefixes; cache dir with 0755 warns, 0700 passes; missing bundle warns; no network in tests (fetch injected).
- Accept: `doctor --env` in the S2 temp HOME shows all checks; `update` offline prints a message and exits 1.

**S6. README and optional `install.sh`.** Owns `README.md`, `install.sh`, `docs/img/`.
- README per section 5; transcripts generated by running the commands against `docs/design/demo.json` (never a real
  scan); hero screenshot of `open demo`. `install.sh` per section 2, `shellcheck` clean, tested by S2's temp-HOME
  harness with a local wheel (`CONSTELLATION_WHEEL=dist/...` override).
- Accept: every command in the README runs as written in the temp HOME.

## 5. README structure (modelled on Mole)

```text
# Constellation
One line: See your whole Claude Code setup as a map: what loads every session, what you never use, what overlaps.
Badges: PyPI version · licence · Python 3.13 (no star/commit badges until public)
[hero screenshot: the map from `open demo`, docs/img/hero.png, demo data only]

## Features            6 bullets: Map, Cost, Unused, Twins/Clashes, Cleanup checklist, Weekly
## Quick start         uv tool install claude-constellation
                       constellation              # menu
                       constellation open demo    # try it on invented data first
                       commented command table, like Mole's
  <details> Other ways: uvx --from ..., pipx, a wheel from Releases, from source
## Privacy             what is read (config files, locally), what is sent (only names and descriptions, redacted,
                       priced first, never with --offline), --count-bodies opt-in, no telemetry, where files are written
## Safety              nothing in ~/.claude is ever modified; clean writes a checklist only; --dry-run on every writer;
                       pins protect Items from suggestions
## Commands in detail  one `text` transcript per main verb (doctor, cost, unused, why, clean, weekly), demo data
## Configuration       env vars (ANTHROPIC_API_KEY, CONSTELLATION_PORT, NO_COLOR), cache location
## Update / uninstall  constellation update; constellation uninstall
## FAQ                 Does it send my skills? Does it cost money? Does it change my setup? Windows/Linux?
                       Why is on-use cost "unknown"? How is this different from /context?
## Development         the current README's Development section, moved down
## Licence
```

Keep the current README's deep sections (Report, Public Snapshot, Plugin, Review Suggestions) in `docs/` and link them.

## 6. Risks

- **Wrong package via `uvx constellation`.** The name is someone else's; a user who guesses gets docker deploy scripts.
  Mitigation: every doc line uses the full dist name; consider the name choice that makes `uvx <name>` work, e.g. make
  the console script name match the dist (`claude-constellation`) as a second entry point, so
  `uvx claude-constellation` runs. Cheap: one extra line in `[project.scripts]`.
- **Shipping a wheel without the bundle.** Covered by S2's hard check and the `doctor --env` warning.
- **History leaks on going public.** Covered by section 2's review; fallback is a squashed mirror.
- **Typosquats / look-alikes.** Low for a small project; state the official sources in the README as Mole does.
- **Python 3.13 floor.** Some users have 3.12; uv solves it, pipx does not. Document uv first.
- **fastembed and anthropic extras.** Installing `[local]` downloads an ONNX model on first use; say so before it happens.
- **Menu on odd terminals.** Raw mode fails in some IDE terminals; fall back to the numbered prompt on any termios error.
- **Release done by hand.** No CI means human error; the script and checklist are the guard. Going public makes CI free.

## 7. Decisions for the owner

1. **Visibility.** (a) PyPI only, repo private; (b) public squashed mirror; (c) flip this repo public (frees CI). Suggest
   (a) now, (b) when ready to show the code.
2. **Distribution name.** `claude-constellation` (clear, searchable; check Anthropic's trademark guidance on using
   "Claude" in a name first) or `constellation-cli` (neutral). Command stays `constellation` either way.
3. **Licence.** MIT (suggested) or Apache-2.0.
4. **`app` into base dependencies** so the one-line install can open the map. Suggest yes.
5. **Homebrew tap.** Suggest later or never; PyPI + uv covers Mac users.
6. **`install.sh`.** Only after something is public; optional since `uv tool install` is already one line.
7. **Short alias.** Suggest none (`cs` clashes with Coursier).
8. **`update` never installs** (deviation from Mole). Confirm.

Record 1, 2, 4 and 8 as decisions in `docs/plan-tracker.md` when made; 4 changes the dependency plan.
