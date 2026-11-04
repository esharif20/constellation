---
name: constellation
description: Scan a supplied Claude Code config directory, show its terminal report and open the local graph.
argument-hint: <config-directory> [scan-file]
disable-model-invocation: true
---

Use the installed `constellation` CLI. Arguments: $ARGUMENTS

1. Take the config directory from the user's arguments; ask for it if absent.
   Take the output file from the second argument, defaulting to
   `constellation.json` in the working directory. Ask before replacing an
   existing output file. Treat paths as data and quote each as a literal shell
   argument; never evaluate shell syntax from the arguments.
2. Run `constellation scan CONFIG_DIRECTORY --offline --out SCAN_FILE`.
   Remove `--offline` only if the user explicitly requests a paid scan. Pass
   `--count-bodies` only if explicitly requested, explaining that it sends
   redacted skill bodies to Anthropic's counting endpoint.
3. On success, run `constellation report SCAN_FILE`. Show its stdout verbatim
   in a code block; the CLI owns report formatting and redaction.
4. On success, run `constellation open SCAN_FILE` using the shell tool's
   background execution so the server can keep running. Report the local URL
   `http://127.0.0.1:8765/` URL after the server starts, and keep the process
   running until the user stops it.

Stop on a failed CLI command and show its error. If the executable or frontend
build is missing, relay the CLI's setup guidance; leave installation to the user.
Use CLI output only: do not read the scan JSON, config contents, transcripts,
credentials or environment files into the session. The CLI handles local
processing. Never edit the user's Claude Code setup. Expansion is not part of
this command until the CLI supports it.
