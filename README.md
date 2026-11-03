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

## Using it

```
uv sync --extra llm --extra local              # the model and the local embedder are optional extras
constellation scan ~/.claude --dry-run > prompts.txt   # read-only; prints exactly what would be sent, sends nothing
constellation scan ~/.claude                   # writes constellation.json (mode 0600, descriptions redacted)
constellation scan ~/.claude --no-verify       # skip the stronger model that labels candidate Overlaps
uv run --extra local pytest -m eval -s         # slow clustering quality check with the real embedder
uv run pytest -m eval -s tests/eval/test_overlap_quality.py   # scores the Overlap verifier on 20 invented pairs (real model, a few cents)
```

Overlaps: identical instructions and thin wrappers are found locally, embeddings propose similar pairs, and Claude Sonnet 5.5 labels each pair
from names, descriptions and a few local signals only. File bodies never leave your machine. A real run prints a pair-count and cost estimate
first; verdicts are cached in `~/.cache/constellation/overlap-verdicts.json`.

The API key goes in a `.env` file in the folder you run the command from (it is gitignored), as one line with no quotes:
`ANTHROPIC_API_KEY=sk-ant-...`. Run `chmod 600 .env` so only you can read it. A variable already set in your shell wins over the file.
