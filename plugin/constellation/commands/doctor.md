---
description: Health check of your Claude Code setup from the last Constellation scan (read-only, local, free).
argument-hint: [scan-file]
allowed-tools: Bash(constellation doctor:*)
disable-model-invocation: true
---

Run `constellation doctor -- SCAN_FILE` with the shell tool, where SCAN_FILE is the argument below, or
`~/.cache/constellation/constellation.json` when none is given (resolve `~` without evaluating shell syntax;
quote the path as one literal argument and reject any argument starting with `-`). Arguments: $ARGUMENTS

Show the stdout verbatim in a code block; the CLI owns the formatting and redaction. If it exits 2, relay its
message and suggest `/constellation` to scan first. Do not edit any settings or files.
