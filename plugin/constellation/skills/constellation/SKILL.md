---
name: constellation
description: Scan your Claude Code setup (offline, free), show its status and open the local graph.
argument-hint: [config-directory]
disable-model-invocation: true
---

Use the installed `constellation` CLI. Arguments: $ARGUMENTS

1. The only optional argument is a config directory (default: the CLI's own default, `~/.claude`).
   Reject any argument starting with `-`, including `--count-bodies`; arguments are paths, never CLI
   options. Reject extra arguments. Treat the path as data and quote it as one literal shell argument;
   never evaluate shell syntax from it.
2. Run `constellation scan --offline --no-usage --project=PROJECT_DIRECTORY -q` (append `-- CONFIG_DIRECTORY`
   only when one was given), where PROJECT_DIRECTORY is the session's working directory, so the report and
   graph split global from this repo's Items. The scan writes to the CLI's default scan file
   (`./constellation.json` if present, else `~/.cache/constellation/scan.json`). Remove `--offline` only if
   the user explicitly requests a paid scan. Pass `--count-bodies` only if explicitly requested, explaining
   that it sends redacted skill bodies to Anthropic's counting endpoint.
3. On success, run `constellation status`. Show its stdout verbatim in a code block; the CLI owns
   formatting and redaction.
4. On success, run `constellation open` (it opens the latest scan) using the shell tool's background
   execution so the server can keep running. Report the local URL `http://127.0.0.1:8765/` after the
   server starts, and keep the process running until the user stops it.

Stop on a failed CLI command and show its error. If the executable or frontend build is missing, relay the
CLI's setup guidance; leave installation to the user. Use CLI output only: do not read the scan JSON,
config contents, transcripts, credentials or environment files into the session. Never edit the user's
Claude Code setup.

Transcript usage is disabled in this session wrapper (`--no-usage`) so activity counts and dates are not sent
into Claude context. Use the standalone CLI for transcript usage.
