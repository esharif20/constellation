# Plan: grounded, inexpensive chat (#11)

Status: user opt-in approved 2026-11-04; implementation not started. Chat stays disabled by default. Read issue #11, ADR 0001/0003, AGENTS.md and the [model research](../research/chat-models.md).

## Approved privacy and cost exception

The user explicitly opts into model chat and accepts redacted questions plus relevant Item metadata being processed per interaction, with very low cost a requirement. This is a limited exception to changed-Items-only scan calls. It does not enable a provider, make a paid development call, or authorize background calls.

- Model chat remains off unless the user enables it. Merely possessing an API key, opening the graph, selecting/dragging a node, typing or loading a plugin makes no model request.
- Graph context means a bounded selection of relevant Item kinds, names, descriptions, existing Relations and Context cost signals. No whole-graph dump or conversation-history growth. Selection can improve relevance; it does not broaden the allowed field set.
- Never include transcript text, file bodies, usage counts/dates/window, filesystem source provenance, warnings or credential/settings files in a model request. Usage questions terminate locally to preserve #20's provider-isolation promise. Do not call read_secrets() or load_env() to enrich a chat prompt.
- Redact each complete question/field before shortening it, then guard the final prompt. This uses existing pattern rules on saved metadata/user input; do not promise detection of every possible free-form secret. Redact model answers/errors too.
- No automatic fallback from local inference to a hosted model, no retry/repair/escalation calls, and no auto-download or model installation. Failed/malformed model replies return a useful local result or an error.

## Local work before model work

Compute counts, top Context costs, known Overlaps, usage, search and graph focus/filter actions locally. Reuse brief(), report's ranking/usage helpers and known Item ids. Unknown cost stays unknown; a model never calculates totals or infers usage.

The saved Constellation already is the knowledge base: current invented demos have 90 and 239 Items. Search names/descriptions/kinds and follow relevant Relations. Initially no new embeddings, vector database, chunking pipeline, paid reranker or external retrieval service. Retrieving this structured evidence before synthesis is lightweight RAG; that does not require a RAG platform.

## Proposed initial budgets and model choices

These are implementation recommendations, not measurements of real usage or M1 performance:

- At most eight retrieved Items and twelve relevant links whose endpoints are retained. Prefer explicitly selected Items, exact names and deterministic tie breaking; avoid sending unrelated graph positions/layout data.
- Keep the complete redacted prompt within an explicit byte budget suitable for a 4K local context, including fixed instructions. Bound the submitted question separately; if it cannot fit with evidence, return a local validation error rather than silently spending on a larger context. Do not truncate a secret before redaction.
- One model transport attempt at most for a cache miss; short output capped at 256 generated tokens, thinking disabled where supported, finite timeout, SDK retries explicitly disabled. No model call when there is no usable evidence. Prove this at the transport seam, not by counting an outer function invocation.
- Cache only validated/redacted responses in private 0600 files keyed by the hash of the redacted question, selected evidence, provider/model and prompt/response contract version. Do not store raw questions/prompts. Usage-only changes must not invalidate model answers. Retain successful answers in memory when disk is unwritable; serialize concurrent identical misses to avoid duplicate spend.
- Local option: an explicitly configured Ollama loopback server with a small quantized model, initially qwen3:4b and a 4096-token context. On the user's 16GB M1 this is a conservative starting trial, not a verified fit/quality/speed guarantee. One request at a time; never choose a cloud model through Ollama implicitly.
- Hosted option: reuse the existing Anthropic dependency and claude-haiku-5-5 with a chat-specific low-output/no-retry adapter. Current small-prompt rates are $0.10/M input and $0.50/M output; 1500 input plus 250 total output tokens is about $0.000275, or $0.275 per 1000 uncached answers. This arithmetic is not a dollar ceiling or a substitute for actual returned usage accounting. Do not enable a second hosted provider for a negligible price difference.

## D12 architecture proposal before implementation

The existing tracker specifies prebuilt create_react_agent, possibly replaced by StateGraph later. An ordinary tool-calling loop can require several model completions. To make the per-question ceiling provable, recommend a fixed LangGraph route: deterministic local tools/retrieval, then an optional single synthesis node, then local answer/action validation. This changes D12's initial implementation choice. It is proposed here, not silently implemented; resolve this plan change before writing the provider-backed chat graph. The user has already approved the input/billing exception above, so do not ask for that opt-in again.

## API, tests and completion

- Public seam: POST /api/chat with a question and bounded selected Item ids, returning answer text plus graph actions referencing known Items only. Reuse #25's localhost/origin/JSON guards. Reject invalid/unknown ids and over-budget input before any provider attempt.
- Test through the HTTP API with recording fakes: the email query, explanations, top five costs, unknown costs, empty setup, provider errors, hostile metadata and hallucinated action ids. Do not execute real MCP commands; Expansion delegates to #9 when it exists.
- Assert zero provider calls with chat disabled, for deterministic questions, on an identical cache hit, and after usage-only changes. Assert one transport attempt on a model answer and on simulated rate-limit/server errors, no hidden retry, no automatic hosted fallback, and one shared result for concurrent identical requests. Verify relevant metadata/model changes invalidate the cache.
- Plant sentinels in every forbidden field and assert their absence from recorded provider requests and model cache. Check prompt/output limits, redaction-before-truncation, private cache permissions and unwritable-cache behavior. Do not read actual credentials or setup files in tests.
- Keep chat.py/tests independently owned; one integration owner changes server.py/cli.py/Atlas.tsx after #25. UI follows DESIGN.md with demo-only browser verification. Static #13 chat bypasses providers entirely.
- Run all Python, mutation and frontend gates before calling #11 complete. This design/research commit is not an implemented chat feature. Local model latency, memory pressure and answer quality remain unmeasured; no download or paid call was made.
