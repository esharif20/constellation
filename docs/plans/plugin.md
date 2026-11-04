# #12 Thin Claude Code plugin

## Scope

Package one user-invoked command under `plugin/constellation/`, with a manifest
in `.claude-plugin/plugin.json` and `skills/constellation/SKILL.md`.
It delegates to the existing `constellation scan`, `report` and `open` commands.
The report remains the CLI's `render_report` output; the plugin has no scanner,
renderer, provider, dependency or application changes.

Claude Code namespaces plugin commands, so the invocation is
`/constellation:constellation`, rather than bare `/constellation` in the ticket.
This platform constraint is documented explicitly; approval of that naming
adjustment is pending. The current official docs recommend `skills/` for new
plugins; it provides the same slash-command interface without a legacy format.

## Behaviour

1. Require a user-supplied config directory. Use a user-supplied scan output
   file, or `constellation.json` in the working directory; ask before replacing
   an existing file. Quote paths as literal shell arguments.
2. Run `constellation scan CONFIG --offline --out FILE` by default. Paid scan
   options require an explicit user request; `--count-bodies` is never inferred.
3. After a successful scan, run `constellation report FILE` and show its stdout
   verbatim in a code block. Read only this CLI output into the session.
4. Run `constellation open FILE` as a background process through the session's
   shell tool. Report CLI errors and stop the sequence on a failed command.

The installed CLI owns all processing and redaction. The plugin does not read
file bodies, JSON scans, transcripts, credentials or environment files, and
does not modify the Claude Code setup. Expansion stays with #9; no nonexistent
`expand` command is advertised.

## Validation

Validate the manifest locally with an isolated Claude config directory if the
installed CLI supports it, and check command references against CLI help.
Smoke-test the public CLI on invented fixtures in a temporary working directory
with providers and caches isolated, comparing the report with `render_report`.
Run the repository's Python and frontend gates. No live Claude session, real
setup scan, paid call, plugin installation or browser launch is part of local
validation. Record any missing gate or integration validation in the tracker.

## References (verified 2026-11-04)

- [Claude Code plugin creation and local loading](https://code.claude.com/docs/en/plugins/create)
- [Plugin manifest reference](https://code.claude.com/docs/en/plugins/manifest-reference)
- [Plugin components, including Markdown commands](https://code.claude.com/docs/en/plugins/components)
