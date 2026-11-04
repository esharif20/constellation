# Local public export (branch `codex/export-public`)

This is the user-requested writer/static-graph stage on top of `snapshot.py`,
including the #47 scrub. It leaves the protected reader/model, chat/answer,
clustering and Atlas/StarMap files unchanged. AGENTS.md and CLAUDE.md privacy
rules are unchanged.

- `constellation export --public [FILE] --out DIRECTORY` reads the saved scan only.
  Both `--public` and a new output directory are required. Dispatch precedes
  environment loading; no credentials, real setup, models or MCP processes are used.
- Apply `snapshot()` once to all exported scan data. Only opaque ids and the
  existing public field allowlist survive. Keep disabled flags and already saved
  tool Items; discard usage, source paths, bodies, warnings and connection settings.
- Copy the trusted frontend build's index and regular assets only. Refuse incomplete
  builds and linked index/assets. Create output exclusively, outside any `.claude`
  folder, with a private root and 0600 files. Never overwrite or publish automatically.
  A failed disk write returns a CLI error; any incomplete new directory is left for
  the user to inspect/remove, and is not overwritten on retry.
- Serve `api/constellation` as a plain static file. A small exported adapter returns
  local read-only errors for other API calls, so search falls back locally and no
  question, search query or checklist write is sent to a backend. No backend is shipped.
- **This does NOT anonymise free text.** Say so in CLI help, successful CLI output
  and the exported README. Known limits are bare usernames/machine names, unquoted
  paths with spaces, obfuscated emails, public hostnames outside URLs/emails,
  `//server/share`, and `$HOME`/`%USERPROFILE%` forms. Publishing requires human review.
- Test the public CLI seam with invented scans/builds, planted secrets in all free
  text fields, NFKC forms, paths, hosts, IPv6, overwrite refusal and permissions.
  Test the exported browser adapter without network, then verify the real built
  graph against a static file server using demo data only.
- Add `public_export.py` to `only_mutate`; run every Python/mutation/frontend gate.

The full #13 plan also calls for live pre-run Expansion and canned chat UI. Those
remain pending under the user's explicit protected-file ownership restriction;
this branch never launches a configured server or fabricates missing tool lists
or chat responses. Do not mark all of #13 complete from this writer stage.
