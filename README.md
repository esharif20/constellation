# Constellation

An interactive map of a Claude Code setup. See `GLOSSARY.md` for the vocabulary and `docs/adr/` for the decisions.

## Development

```
uv sync
uv run pytest                      # tests
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run mutmut run && uv run mutmut results   # mutation tests for the redaction guard; no output means no survivors
```

Tests never read a real Claude config: they use `tests/fixtures/` or a temporary directory.

### Graph app (frontend)

Vite, React, TypeScript, Tailwind and shadcn/ui in `frontend/`; the graph is `react-force-graph-2d`. Node 22 or newer.

```
npm --prefix frontend install
npm --prefix frontend run build    # typechecks, then writes the app to src/constellation/static/ (gitignored)
npm --prefix frontend run lint
```

`constellation open` serves that build and exits with a hint if it is missing. For live editing, run the API and the
Vite dev server side by side; the dev server proxies `/api` to port 8765 (or `CONSTELLATION_PORT`):

```
uv run constellation open docs/design/demo.json --no-browser   # invented demo data, safe to screenshot
npm --prefix frontend run dev
```

Design language and the refinement checklist: `docs/design/graph-app.md`.

## Using it

```
uv sync --extra llm --extra local              # the model and the local embedder are optional extras
constellation scan ~/.claude --dry-run > prompts.txt   # read-only; prints exactly what would be sent, sends nothing
constellation scan ~/.claude                   # writes constellation.json (mode 0600, descriptions redacted)
constellation scan ~/.claude --offline         # no paid or network calls: no labels or verifier, cached token costs only
constellation scan ~/.claude --no-verify       # skip the stronger model that labels candidate Overlaps
uv run --extra local pytest -m eval -s         # slow clustering quality check with the real embedder
uv run pytest -m eval -s tests/eval/test_overlap_quality.py   # scores the Overlap verifier on 20 invented pairs (real model, a few cents)
```

Overlaps: identical instructions and thin wrappers are found locally, embeddings propose similar pairs, and Claude Sonnet 5.5 labels each pair
from names, descriptions and a few local signals only. File bodies never leave your machine. A real run prints a pair-count and cost estimate
first; verdicts are cached in `~/.cache/constellation/overlap-verdicts.json`.

Caches (each a private 0600 JSON file keyed by the hash of the redacted text, with the model id mixed in for labels and verdicts, so a new
prompt, a changed Item or a new model is asked again and nothing else is): `labels.json` (labels), `overlap-verdicts.json` and
`token-counts.json`, all under `~/.cache/constellation/`. Delete a file to start it over. A re-scan of an unchanged setup makes zero paid calls;
adding two skills costs two label calls plus any new candidate pairs. An unwritable cache is a warning, not a crash.

Offline: `--offline`, or simply no `ANTHROPIC_API_KEY`, makes no paid or network calls. You still get Items, Relations, exact-duplicate and
wrapper Overlaps, token costs already in the cache (others show as unknown), and clusters named after their nearest Item when the local
embedder is installed (otherwise clustering is skipped with a note). Labels are empty and the file's warnings say the run was offline.
`--offline` cannot be combined with `--count-bodies`, which sends text to Anthropic.

The API key goes in a `.env` file in the folder you run the command from (it is gitignored), as one line with no quotes:
`ANTHROPIC_API_KEY=sk-ant-...`. Run `chmod 600 .env` so only you can read it. A variable already set in your shell wins over the file.
