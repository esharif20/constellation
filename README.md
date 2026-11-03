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
