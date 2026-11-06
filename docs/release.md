# Releasing constellation-cli

Releases are cut by hand from a clean checkout of `main`. No CI is involved and nothing here runs automatically.

## Checklist

1. Bump `version` in `pyproject.toml`.
2. Move the `[Unreleased]` notes in `CHANGELOG.md` under a new `## [X.Y.Z] - YYYY-MM-DD` heading (Keep a Changelog).
3. Commit both, then run all gates locally (`ruff check`, `ruff format --check`, `mypy`, `pytest`, `mutmut` on changed modules).
4. Run `scripts/release-check.sh`. It refuses a dirty tree, builds the frontend bundle and the wheel, asserts the wheel
   holds the bundle and the demo and no tests, `.env`, `*.sqlite` or `constellation.json`, installs it with `uv tool`
   into a temporary HOME, runs `--help`, `--version` and `open demo --no-browser` (one request to the server), writes
   `dist/SHA256SUMS`, and cleans up `node_modules`, `src/constellation/static` and the temp dir. It needs about 1 GB of
   transient disk; check `df -h /System/Volumes/Data` first (stop under 10 GB free).
5. `git tag vX.Y.Z && git push origin vX.Y.Z`.
6. Publish (see below), then, if the repo is public, `gh release create vX.Y.Z dist/* --notes-file <notes>`.

## Publishing to PyPI

Publishing is a manual step and is not done by the script. Two routes:

- **API token (default).** Create a PyPI token scoped to the `constellation-cli` project, keep it in the macOS keychain
  (never in `.env` or the repo), and run `uv publish` with it passed through `UV_PUBLISH_TOKEN` for that one command.
- **Trusted publishing (optional, later).** On pypi.org, project settings, Publishing, add a trusted publisher: owner
  `esharif20`, repository `constellation`, workflow file name, and an environment name. Then a workflow with
  `permissions: id-token: write` could run `uv publish` with no stored secret. That workflow does not exist and must be
  trigger-by-hand only (`workflow_dispatch`, never on push) because Actions minutes on this repo are unbudgeted.
  Describing it here does not enable it.

A published version cannot be replaced: fix forward with a new version.
