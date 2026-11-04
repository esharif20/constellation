# Plan: free local chat (#11)

Status: free local phase implemented 2026-11-04; 16GB unified memory is the supported baseline. Read issue #11, ADR 0001/0003 and AGENTS.md. Chat runs entirely locally and for free, with no generation adapter or provider calls. The original privacy invariant and cost rule apply without a chat exception. Optional local generation remains future work; historical [model research](../research/chat-models.md) does not authorize it or any hosted execution.

## Local retrieval and graph operations

The user's free-first direction authorizes a fixed local `StateGraph` instead of the initial prebuilt multi-call model agent (D12). Route the question, retrieve evidence, shorten display text after redaction, then use `add_conditional_edges` to select distinct search, explanation, focus, top-cost, count, Overlap or usage nodes. Each operation returns a short grounded answer and known-id actions. No model node is enabled.

The saved Constellation is the knowledge base. Search redacted Item names/descriptions/kinds in an in-memory SQLite FTS5 index with BM25 ranking, exact-name priority and stable id tie breaks. Tokenize/quote FTS input and bind it as SQL parameters; never execute user-supplied FTS syntax or SQL. Close SQLite connections after use. No embeddings, persistent index or external retrieval service is required.

Reuse `brief()` and report ranking/usage helpers. Compute counts, top always-on Context costs, known duplicate/wrapper pairs and usage locally; unknown cost stays unknown. Named or selected Items support explanations and their always-on/on-use costs. Unsupported totals and semantic matches receive honest local answers.

## First free version contract

- `POST /api/chat` body: `{question: string (1–1000 characters, nonblank), selected_ids?: string[] (max 8)}`; extra fields forbidden. Unknown selected ids are rejected. Reuse localhost Host/Origin/fetch-site/JSON guards. Reject declared Content-Length above 16,384 bytes before FastAPI parses JSON; reject Transfer-Encoding requests with 411 so chunked bodies cannot bypass that bound.
- Return `{answer: string, actions: [{kind: "highlight"|"focus", item_ids: string[]}], mode: "local", cached: boolean}`. Every action id exists in the current scan. `filter` is removed from the action contract: the current canvas highlights matches by dimming other Items, so filter-worded questions return `highlight`; no answer claims Items were hidden.
- Retrieve up to eight lexical matches, give selected/exact Items priority, and show at most five results with an omitted-results note. No fabricated model explanations or unsupported semantic matches.
- Redact full questions and metadata before indexing or shortening. Do not read credentials, the live setup or transcripts. Usage answers use the saved usage summary locally. Disable LangSmith tracing around graph execution even when ambient tracing is configured.
- Cache bounded local responses in a 128-entry memory cache keyed by redacted question, selection and current relevant data. Usage changes invalidate usage answers; provenance does not enter the cache. Write no raw questions, query logs, conversations or retrieval index to disk.
- UI: collapsed-by-default chat labelled free/local with models off. Submit only explicitly from supported loopback hosts; remote/static pages show unavailable before serializing/sending a question. Validate replies and known action ids before applying actions.
- Opening chat replaces Brief or the cluster card on the left and exits cluster focus using the existing history replacement; entering cluster focus closes chat. Closing chat restores the map flow. The phone Chat trigger stays above the cluster sheet, and keyboard cluster entry retains heading focus. Preserve the under-960 panel coexistence rule and DESIGN.md keyboard/focus/loading/error behavior. `aria-controls` names the section only while that section is mounted; the collapsed trigger has no dangling reference.
- No provider picker, inference adapter, download, paid fallback or setup edits. Root coordinates shared server/Atlas integration; backend owns chat.py and public HTTP tests; UI owns Chat.tsx and its map hooks. The user explicitly authorized the small review UI fixes in #11.

## API, tests and completion

Test at `POST /api/chat` using invented fixtures. Cover lexical retrieval, scoped explanations, focus/highlight actions, top-five costs, unknown costs, usage, empty setups, hostile metadata/FTS input, known ids, bounds, redaction and cache behavior. Request-size boundary tests include malformed JSON with an oversized declared length to prove rejection precedes parsing.

Render the public Chat component in open/collapsed states to verify every `aria-controls` reference resolves and the panel section has its own id. The demo-only `chat:cluster:check` browser regression covers the shared slot, keyboard focus, history and narrow Inspector coexistence at 1440, 700 and 390px; real scans and configured user servers are excluded.

Run Ruff check/format, mypy, all non-eval tests, the full mutation gate with empty results, and frontend lint/build/layout plus the chat accessibility check. Optional model latency/memory/quality, real scans, screen readers and physical touch remain unverified. A future generation implementation requires a separately reviewed contract under the unchanged privacy/cost rules.
