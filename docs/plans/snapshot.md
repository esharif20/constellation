# Plan: public Snapshot (#13)

Status: started; privacy foundation first, full export depends on #9 Expansion and #11 chat contracts. Never publish automatically.

## Public shape and privacy

- A Snapshot is a separate, read-only JSON/bundle built from the saved Constellation and precomputed Expansion/canned-chat results. It uses the existing redaction rules and contains no credentials, file bodies, transcripts or executable connection settings.
- Drop usage and usage_window entirely, including nested copies. Activity dates are personal. Drop warnings and filesystem source provenance; allowlist public fields rather than copy arbitrary input fields.
- Remap Item ids to deterministic opaque ids and update Relations, clusters, costs, Overlaps, tool-parent links and graph actions consistently. Unknown cost stays unknown; retain no original id in metadata.
- The privacy foundation is a pure snapshot(data) transformation with fixture tests. Accept already-expanded mcp_tool Items as ordinary Items; do not pretend absent tools have been expanded. No MCP launches, model calls or environment/credential reads occur in this transformation.
- **User-approved privacy amendment (2026-11-04):** executable Item descriptions (`hook`, `mcp_server`, `connector`) become kind-specific generic text. Snapshot-only text scrubbing additionally removes home paths (macOS, Linux, tilde and Windows), email addresses, URLs including credentials and endpoint paths, dotted hostnames/IPs and `localhost` from every retained free-text field, including names, labels, cluster names, Relation kinds and Overlap verdicts/reasons. Provider redaction is unchanged. Only known Item kinds survive: `skill`, `agent`, `plugin`, `hook`, `mcp_server`, `connector`, `mcp_tool`, `command`; unknown or missing kinds and their orphan references are dropped. The model currently permits arbitrary strings, so this is an explicit public allowlist of Source adapter kinds plus pre-expanded tools.
- **Ticket #32 compatibility (2026-11-04):** the known `command` Item kind is retained. `disabled: true` is retained as a safe boolean so public Snapshots do not imply a disabled plugin or child is enabled; false and malformed values are omitted. Provenance, config and credentials remain outside the public field allowlist.
- Foundation public fields are `items`, `relations`, `labels`, `clusters`, `costs` and `overlaps`; every record is allowlisted too. Item `source` is an empty string for existing frontend compatibility. Opaque ids are ordinals assigned by sorted original id, with existing list order retained. Drop orphan/invalid references and empty clusters; malformed numeric costs become unknown, never private strings or nested data. Missing or null optional collections are empty, matching existing saved-scan readers.

## Export and integration after the dependencies land

- The future CLI requires an explicit output directory, refuses to overwrite existing output and never publishes automatically. No export command is added in this privacy fix.
- CLI export --public writes a local static bundle from the sanitised data, built frontend assets, pre-run #9 Expansion results and canned #11 responses. Do not publish or start real configured servers during development; use synthetic fixtures.
- Precomputed Expansion and canned chat must pass the same field allowlist, opaque-id remapping and public text scrub; neither may bypass it or copy arbitrary nested fields, raw tool responses or connection settings.
- The app loads Snapshot data with no backend. Expansion returns saved tool lists and chat returns saved canned answers without live requests; missing data has an honest unavailable state.
- Keep the pure privacy module and tests independent while #25 owns server.py/cli.py/Atlas.tsx. One integration owner later adds CLI and static loader integration using the settled contracts.
- Tests plant secrets in every public string/reference and unexpected nested keys, verify input immutability and reference integrity, and assert usage, timestamps, source paths and execution settings are absent. Include orphan/invalid references and unknown costs.
- Final acceptance additionally needs a backend-free browser smoke test, fixtures proving Expansion inclusion/canned chat, and all Python, mutation and frontend gates. Do not mark #13 done while that integration is missing.
