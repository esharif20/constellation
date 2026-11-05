# Plan: on-demand Expansion (#9)

Status: Python/CLI/API implemented and under review; frontend acceptance pending. Implements D2 and ADR 0002. Codex owns Python/CLI/API; Claude owns frontend integration. Coordinate `server.py` ownership with #25 and implement these tickets sequentially.

## Scope

[#9](https://github.com/esharif20/constellation/issues/9) already authorizes opening an MCP server Item or running `expand` to query its tool list live. Ordinary scanning stays passive. Unreachable is a normal result; hosted connectors stay single nodes. Expansion never invokes tools or calls a model.

Current adapter ids include root/plugin scope. Saved JSON has sanitised Items, without executable settings or source-root provenance. The server receives an optional explicitly selected config root in memory and uses #25's localhost guard. Never reconstruct a command from an Item description.

## Proposed minimal contract

- CLI: `constellation expand <item-id> --config-dir PATH [--file constellation.json]`. Use the exact known Item id, not a guessed name. Handle this branch before `load_env()`, as for `report` and `open`.
- App: `constellation open [FILE] --config-dir PATH` optionally enables live Expansion. Pass the root to `create_app` in memory; omitting it keeps read-only viewing. Never write connection settings or config-root provenance into saved JSON.
- API: `POST /api/expand`, body exactly `{"id": "<known Item id>"}`. The client supplies no command, args, environment, URL or config path. GET and initial page load never launch anything. Opening an MCP server in the app makes this POST, per the ticket.
- Response: `{"item_id": "...", "status": "expanded|unreachable|not_expandable|unavailable", "items": [...], "relations": [...], "message": "..."}`. Reachable with no tools is `expanded` with empty lists. No configured root is `unavailable`; connectors and other kinds are `not_expandable`, with no launch.
- Known server failures: HTTP 200 with `unreachable`, CLI exit 0 and a clear message. Unknown id: HTTP 404 / CLI exit 2. Bad request: 422; non-JSON: 415. Invalid/missing scan/config input is a local input failure, not a successful empty tool list.
- Tools become `mcp_tool` Items with stable ids derived from the parent id and the tool name, plus parent-to-child `contains` Relations. Redact names/descriptions; derive the id using a digest of the original tool name so redacted names cannot collide. Missing description is empty. Sort deterministically; conflicting duplicate tool identities fail safely.
- Return results only: no saved-scan updates, cache, labels, counting, embeddings, Overlap processing or provider calls. Re-expanding queries again. The app can replace the previous in-memory list for that parent.

These interface details are proposed implementation defaults, not changes to the privacy invariant.

## Implementation order

1. Write failing tests through `cli.main`, `scan()` and the HTTP API using temp configs and fake MCP sessions. Add one synthetic stdio fixture for lifecycle tests; no real commands, network, models or package downloads.
2. Resolve root/user/local/plugin MCP registrations in `expansion.py`, matching the reader's id naming/redaction rules and reusing its config-location/plugin-discovery helpers. Never construct parent descriptions: those remain owned by the unchanged reader. **User-directed ownership amendment:** `claude_code.py` is protected while another agent edits it; this ticket must not change that reader. Match the exact scan id, source and kind, including active plugin version and inline/file declarations from plugin.json. Preserve shape-only scan descriptions and user/<name>, local/<n>/<name> scopes. Resolve from the explicitly selected root; do not call `scan()` or read skill bodies. Removed or changed-to-URL registrations cannot launch. Keep connection settings private and ephemeral. Collapse identical id/settings/root registrations when a plugin manifest declares the same file that implicit discovery reads; differing settings or roots remain an ambiguous input failure.
3. Add a small `expansion.py` with a typed result, one async operation and an injectable query seam for CLI/API tests. Use the official Python MCP SDK; verify its current stable API, dependency version and teardown semantics before adding it with `uv add`. Do not write a second MCP protocol implementation or generic transport framework.
4. Query configured local stdio servers: initialize a minimal client, follow `tools/list` pagination, then close. Never call tools, read resources/prompts, expose filesystem roots, or provide sampling/elicitation callbacks to a model. Discard tool schemas and server instructions from public output.
5. Use a fixed internal ten-second deadline for initialization, all pages and metadata redaction; reject repeated cursors. Bound discovery to 100 pages, 1,000 tools, and 4,096 UTF-8 bytes per tool name/description. Reject an excessive page before accumulation or any following request. Run metadata checks and redaction in cancellable worker waits so the API event loop stays responsive. Bound cleanup too and reap owned subprocesses after success, failure, timeout and cancellation. Verify the SDK actually closes streams and terminates a non-cooperating child before relying on it. Return no partial list when a later page fails. No retry or user-facing timeout option is needed.
6. Map any Exception from server interaction or metadata processing, including grouped errors, to a generic unreachable message. Cancellation still propagates. Suppress raw stderr and exception text in terminal output, HTTP responses and logs, including child SDK loggers created after module import.
7. Add CLI dispatch and the optional root on `open`; add the async POST before the static mount. MCP waits must not block unrelated API requests. No persistent MCP sessions are needed. Permit only one in-flight query for each selected config root and server id; a duplicate request returns unreachable without launching, and completion/failure/cancellation releases the slot.
8. Reuse #25's `local_only` guard after that ticket lands. If #9 lands first, coordinate the guard extraction with #25: localhost bind; validated localhost/127.0.0.1 Host; present Origin equal to `http://{Host}`; present fetch-site only `same-origin` or `none`; JSON-only POST; no CORS middleware. Reject unsafe requests before config reads or launches. Serialize edits to `server.py`.
9. Update README and `docs/plan-tracker.md` in the implementation commit; mark Python/CLI complete separately from frontend acceptance. Add `expansion.py` to mutation coverage.

The [official SDK](https://github.com/modelcontextprotocol/python-sdk) is the implementation reference. MCP defines paginated [tool discovery](https://modelcontextprotocol.io/specification/2025-06-18/server/tools) separately from invocation; [stdio transport](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports) launches a subprocess. Check the installed SDK rather than copying older API signatures.

## Privacy and execution boundaries

The ticket authorizes starting the selected configured local server to list tools. Execute its configured command and args directly, without an added shell wrapper. A configured program may itself download packages or contact external services; Constellation must not claim that this process is sandboxed or inherently offline. Do not add URL transport, OAuth, credential discovery or remote fallback. Hosted connectors remain single nodes, even when a registration also contains a command.

Use explicit configured env values only as local process settings, keep them ephemeral, and never serialize or print them. Use a documented minimal nonsecret launch environment; do not inspect or copy the full process environment. Unsupported variable/plugin-placeholder substitutions must fail safely rather than trigger extra secret lookup. Fix the precise executable-search/cwd behavior during fixture-based SDK implementation, not by probing real credentials.

No scan content, file body or transcript is sent over MCP. No Provider participates. Redact tool names/descriptions with pattern rules, `read_secrets(config_dir)` and the selected registration's explicit nonempty env and argument values, including short values, header components and URL credentials. Argument components are conservatively treated as private, so matching ordinary words may also be redacted. **Review amendment requested by the user:** reuse the existing selected-config secret reader (including its local credential/settings/dotenv sources) solely for redaction; never inspect the process environment or pass these discovered values into launch settings. Fixture-only tests exercise this path; the agent never reads real credentials or `.env`. Never expose commands, args, env, raw logs or protocol payloads. Expanded metadata entering model prompts later is a separate privacy change requiring approval and guarded wrappers.

No new user design decision is required for this minimal Python scope. Stop only if implementation needs broader credential access, provider inputs or another genuine conflict with the written privacy rules. Do not turn routine API naming or child-process setup choices into approval gates.

## Public-seam tests and completion gates

- Reachable CLI/API server: sorted tool Items/Relations, stable ids, empty tool list, missing description and pagination. Include root/plugin servers with equal names and verify the correct registration is selected. No tools are invoked.
- Missing executable, failed initialization, malformed protocol and timeout: unreachable, no partial children, no raw diagnostics; a subsequent healthy request works.
- Synthetic transport fixture: actual initialization/list lifecycle and owned-process cleanup after success, failure, timeout and cancellation, including a child ignoring graceful close. Shorten the injected deadline in tests; verify unrelated GET remains responsive.
- Connector, unsupported kind, unknown id, missing root, removed registration, source/kind mismatch and malformed scan/config never launch a guessed command. URL registrations stay single nodes. Invalid body/media type and hostile Host/Origin/fetch-site fail before the query seam; GET cannot launch.
- Plant invented short/long secrets in explicit env, tool text, stderr and exceptions; assert absence from CLI/API/logs. Settings never appear in saved JSON. Make `load_env`, transcript traversal and provider callbacks fail if touched; known-secret reads are confined to the explicitly selected synthetic config. Use fixture-only environment sentinels.
- Copied config bytes/mtimes and saved JSON remain unchanged. Normal `scan`, read-only `open` and GET never connect; existing paid caches stay unchanged. No real setup or transcript reads.

Run all repository gates with `uv run --all-extras`: Ruff check and format check, mypy, pytest, then mutmut run and results (empty, zero survivors). Run frontend lint/build/layout checks for integration. Real MCP smoke testing requires an explicit user request for that live execution; fixture results do not establish reachability of the user's setup.

## Claude frontend handoff

Opening a local MCP server starts Expansion and shows pending, tool-list, reachable-empty, unreachable and unavailable states. A connector keeps one node. Static Snapshots and older servers remain usable when live Expansion is absent.

The ticket requires tools listed in the app, not a specified canvas-child layout. Inspector-first listing is the minimal recommendation; the Item/Relation response also permits later graph integration. Any canvas merge must replace that parent's previous result and retain unknown Context costs. Claude owns this presentation choice and visual verification with demo data and fake servers.

Next step: review the Python slice and complete Claude's frontend integration. Do not mark D2 or #9 complete until Claude's app integration and all gates pass. Python verification evidence is recorded in `docs/plan-tracker.md`; frontend acceptance remains separate.
