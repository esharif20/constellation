# Optional chat models for #11

Research checked 2026-11-04. Proposal only: no model installed, no paid calls,
no real setup or transcript data read, and no hardware benchmark performed.

## Recommendation

Keep model chat **off by default**. Answer counts, top Context costs, Item lookup,
known Overlaps and focus/filter actions with deterministic Python tools first,
for zero model calls. For an explicitly enabled local model on the user's
M1 Mac with 16 GB unified memory, start with `qwen3:4b` in Ollama. For explicitly
enabled hosted synthesis, reuse the existing Anthropic SDK with
`claude-haiku-5-5`; current pricing does not justify adding another provider.
These are engineering recommendations, not measured model-quality results.

| Option | Verified model facts | Fit for this app |
|---|---|---|
| Local starting point: `qwen3:4b` | 4.02B parameters, Q4_K_M, 2.5 GB model artifact; tools and thinking supported. [Ollama model card](https://ollama.com/library/qwen3:4b) | Conservative first trial for short metadata synthesis; no per-token API charge. |
| Optional local upgrade: `qwen3:8b` | 8.19B parameters, Q4_K_M, 5.2 GB artifact. [Ollama model card](https://ollama.com/library/qwen3:8b) | Plausible with short context and other apps closed, but less memory headroom; test before adopting. |
| Hosted: `claude-haiku-5-5` | Active model released October 7, 2026; normal interactive input/output rates for prompts up to 100,000 tokens are $0.10/$0.50 per million tokens. [Official model card](https://platform.claude.com/docs/en/models/haiku-5-5/overview) | Existing provider dependency, tiny bounded request cost, no local model memory; sends allowed redacted inputs off-machine. |

`qwen3:4b` is an older family, selected for its small artifact, not a claim of
being the newest or best model. The newer `qwen3.5:4b` is also available; its
card currently shows backend artifacts around 3.3–4.0 GB and vision support,
which this metadata task does not need. Avoid changing models merely for
recency. [Qwen 3.5 card](https://ollama.com/library/qwen3.5:4b)

## What 16 GB means

Ollama supports Apple M-series CPU/GPU execution on macOS Sonoma 14 or newer.
Install the macOS app from its DMG into Applications, start it, then download
only the chosen model with `ollama pull qwen3:4b`. This is an installation
recipe, not an action performed during this research. [macOS requirements and
installation](https://docs.ollama.com/macos), [model command](https://ollama.com/library/qwen3:4b)

The artifact size is disk storage, **not total runtime RAM**. Runtime needs
weights, context/KV state and working buffers; macOS, the browser, editor and
app share the same 16 GB. Larger context increases memory use. Begin with
`num_ctx: 4096`, one request at a time, a bounded result set and short answers;
do not allocate a model's advertised maximum context. Treat 4B as the starting
point and 7B/8B-class quantized models as optional experiments, not guaranteed
fits under every workload. Check memory pressure/Activity Monitor and
`ollama ps`; reduce context or model size if swapping occurs. This is
conservative planning guidance, not a precise RAM estimate or speed promise.
[Context memory guidance](https://docs.ollama.com/context-length),
[request context and runtime inspection](https://docs.ollama.com/faq)

Use the loopback server at `http://127.0.0.1:11434`, an explicitly chosen local
model tag, and disable Ollama cloud features (`disable_ollama_cloud: true` in
its server configuration, followed by restart). Ollama documents local prompt
processing and a loopback bind by default. App errors must return a warning,
never automatically switch to a hosted provider. The application should not
install models or edit Ollama configuration without a separate user action.
[Local mode and networking](https://docs.ollama.com/faq)

For a small metadata answer, request `think: false` where supported; discover
supported controls through `/api/show`. Limit generated output, for example
256 tokens, and set a timeout. `keep_alive: 0` unloads after a response if
reclaiming memory matters more than the next cold start. Thinking output still
requires generation even if the UI hides it. [Thinking controls](https://docs.ollama.com/capabilities/thinking),
[chat API and unloading](https://docs.ollama.com/api/chat)

## Hosted price and data tradeoff

The table above uses standard interactive rates, excluding batch discounts,
cache discounts and free tiers. The official table separately lists the older
Haiku 4.5 at $1/$5 per million: do not confuse that generation with Haiku 5.5.
[Anthropic price table](https://platform.claude.com/docs/en/about-claude/pricing)

Assume **1,500 input tokens total** (question, instructions and retrieved
metadata) and **250 billed output tokens**, no thinking, retry or tool loop:

- Haiku 5.5: `(1500 × $0.10 + 250 × $0.50) / 1,000,000 = $0.000275`
  per answer, or **$0.275 per 1,000 answers**.
- A cheap comparator, Gemini 2.5 Flash-Lite, lists $0.10 input/$0.40 output per
  million for standard text requests: **$0.000250 per answer**, or **$0.25 per
  1,000** under the same assumption. The $0.025 difference per 1,000 answers
  does not justify another SDK, key and data processor here. Its free tier
  permits product improvement use; paid tier does not. [Google pricing and
  data-use table](https://aistudio.google.com/docs/pricing#gemini-2.5-flash-lite)

These are arithmetic examples, not actual bills or identical text-token counts
across models. Read API usage to account for real inputs, output, thinking and
retries. Anthropic bills thinking as output even when hidden. Haiku 5.5 defaults
to adaptive thinking; for this bounded synthesis use `thinking: {"type":
"disabled"}` at low effort, as supported by its current API. Disabling thinking
can affect tool behavior, another reason to retrieve deterministically before
the synthesis request. [Thinking behavior and billing](https://platform.claude.com/docs/en/build-with-claude/thinking)

Anthropic's commercial API does not train on inputs/outputs by default, but
standard API retention is up to 30 days with documented exceptions. That is
still an external disclosure and differs from local execution. Do not equate
no training with zero retention. [Training policy](https://privacy.claude.com/en/articles/7996868-is-my-data-used-for-model-training),
[retention policy](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data)

## Retrieval, not a vector database

For the current small, structured Constellation, retrieve saved Item metadata
by name/description/kind, follow existing Relations, and compute costs/counts
locally. Pass only a small selected evidence set to an optional model to phrase
an answer. This is retrieval-augmented generation in the broad sense; it does
not require embeddings, a vector database, document chunking or another paid
retrieval service. This conclusion follows from the local domain model and
the #11 tools in [the chat plan](../plans/chat.md), not a benchmark claim.

Always validate returned Item ids against retrieved Items before focus/filter
actions. Never have a model recompute totals or infer that unknown cost means
zero. Treat descriptions as untrusted data. Bound the question, evidence,
output and request count; one synthesis request is the simplest cost ceiling.
Cache validated answers to identical redacted requests by model, prompt version, question and
selected evidence hash in private 0600 files; do not persist raw questions or prompts.

The user explicitly approved redacted questions and per-interaction model calls on 2026-11-04, with chat disabled by default and very low cost as a requirement. The [chat plan](../plans/chat.md) records this limited exception. No provider is enabled by this research. File bodies, transcript text, usage counts/dates, credentials and filesystem provenance remain excluded. A fixed one-call pipeline is proposed in place of D12's prebuilt multi-step agent; that architecture change remains a proposal before source implementation.

## Verification still needed

Fixture-only answer quality and id-grounding tests; actual M1 cold/warm latency,
peak memory and memory pressure at 4K context; behavior with other everyday
apps open; supported thinking controls in the installed Ollama version; and
the installed Anthropic SDK's new-model argument compatibility. No such
evaluation, model download or paid call was performed here.
