# Model mode: optional, cheap, grounded

Status: design note, 2026-11-05. No code changed. Covers #45 (project advisor) and the "local model vs cloud" question. Builds on
`docs/design/smarter-verdict.md` §7 to §9, `docs/design/ask-purpose.md`, `docs/research/chat-models.md` and the tracker rows D3,
D8, D12, D15. Examples use invented names only (`release-notes`, `changelog-draft`, `tune-spacing`, `pdf-tools`, `git-helper`,
`repo-map`, a demo repo `acme-shop`).

## 0. Recommendation (read this first)

- **Model mode is off by default.** Offline Constellation stays complete: verdicts, Brief, Overlaps from hashes, wrappers and
  embeddings, usage, costs, Ask. Nothing in this note is needed for any existing answer.
- **When the owner turns it on, the default provider is cloud Claude Haiku 5.5 (`claude-haiku-5-5`), bring your own key.** It is
  the cheapest option that adds real value: a full first "smarter analysis" run of a 300-Item setup costs about **$0.04**, an
  unchanged rescan **$0.00** (cache), a grounded Ask answer about **$0.002**. A heavy month is about **$0.30**. A 4B local model
  is free in dollars but takes an estimated 15 to 30 minutes for the same first run on an M1 16 GB and is weaker at multi-step
  tool use, so it is the right choice for privacy, not for cost.
- **Project files and anything derived from transcripts go to the local model only** (the owner's #45 direction). Cloud mode sends
  only what the privacy invariant already allows (redacted kinds, names, descriptions, short local signals) plus, if the owner
  approves decision M2, aggregate numbers (counts, days, token costs) with no text.
- **The model never writes a fact.** It receives structured graph facts with ids, returns structured JSON that cites fact ids, and
  a local checker rejects any unknown id, any number it did not get, and any claim it cannot trace. Numbers shown to the owner
  are rendered locally from the cited ids.
- Budget generously because the model is cheap: up to 200 calls per run, a hard cap of **$0.50 per run** and **$3 per month**
  by default, estimate printed first, every call cached by the hash of its redacted input.

## 1. What a model adds, and what stays local

Plain Claude Code, inside one session, sees only what is loaded into its own context. It does not see other sessions or projects,
cannot measure the tokens its setup adds, keeps no usage history, and cannot compare hundreds of Items pairwise. Constellation
already computes all of that locally. The model layer is worth paying for only where it turns those local facts into a judgement
or a piece of writing that rules cannot produce.

### 1.1 Must stay local (rules, embeddings, arithmetic)

| Task | Why it stays local |
|---|---|
| Hashes, wrapper detection, embedding proposals, ambiguity ranking | Free, exact, already built (#6, #18) |
| Token costs, session-start totals, savings totals | Arithmetic over cached counts; a model would only add error |
| Usage counts, last used, habit ledger, co-use | Read from transcripts locally; transcript text never leaves |
| Verdict (keep / review / could go / not enough data) | Rules in `answer.py`; the model may explain, never overrule |
| Intent routing for Ask, the 14 rule routes in `chat.py` | Free and instant; model is only a fallback |
| Clustering, trigger-miss v1 (description embeddings) | Local embeddings (ADR 0003) |
| Before/after projections for any proposed change | Computed by `receipt()`/`brief()` from the model's proposed ids |

### 1.2 Model-only capabilities (the feature catalogue)

Prices use Haiku 5.5 at $0.10 input / $0.50 output per million tokens (prompts up to 100K tokens; $0.50 / $2.50 above, which
the checker prevents), cache reads at $0.01 and 5-minute cache writes at $0.125 per million. Output figures include low-effort
thinking (Haiku 5.5 thinks adaptively by default; we send `effort: "low"` as `anthropic_llm.py` already does). A shared system
prompt of about 1,500 tokens (above Haiku 5.5's 512-token cache minimum) is cached, so per-call cost is mostly the fresh facts
and the reply. "Facts" below always means redacted kinds, names, descriptions, Item ids and numbers; never bodies or transcript
text.

**(a) Redundancy judge.** For each Overlap or ambiguous pair the rules could not settle, decide which twin to keep and write the
merged description.

- Why Claude Code cannot: it never sees both Items' usage across sessions, their measured costs, or the full pair list.
- Input: both Items' redacted names and descriptions, verdict and reason from `overlaps`, ledger counts (uses, sessions, last
  day), always-on cost, cluster, blast-radius list (who wraps or names each one).
- Output example:
  `{"keep":"i_17","retire":"i_42","why":"f3,f7","merged_description":"Draft release notes and changelog entries from merged PRs. Use when preparing a release.","confidence":"high"}`
  rendered as "Keep `release-notes` (used 12 times in 9 sessions, f3); retire `changelog-draft` (never used, f7, frees 214
  tokens per session)". The 12, 9 and 214 come from the local facts, not the model.
- Calls and cost: one per pair; ~500 fresh input + ~500 output tokens; ~$0.0003 per pair; 40 pairs ≈ **$0.013**.
- Consent: within the invariant once M2 (numbers) is approved.

**(b) Description rewriter for skills that never fire.** For skills flagged as likely trigger misses (smarter-verdict §7 (e)),
rewrite the description so Claude Code will pick it when relevant.

- Why Claude Code cannot: it does not know which skills never fired over months, nor which of the owner's skills do fire.
- Input: the skill's redacted description, the five nearest **used** skills' descriptions with their use counts (a proxy for the
  owner's real tasks), the near-twins to avoid colliding with. Raw prompts are never sent; v2 can add local topic tags made by the
  local model from prompts, which stay local (§4).
- Output example: `{"item":"i_9","description":"Fix spacing, padding and alignment in React or Tailwind UI. Use when a layout looks cramped or uneven.","avoids":["i_31"]}`
  shown as a copyable before/after with its token cost difference computed locally.
- Calls and cost: one per flagged skill; ~600 in + ~600 out; ~$0.0004 each; 30 skills ≈ **$0.011**.
- Consent: within the invariant.

**(c) Setup architect.** Propose a restructured setup: what to group into a plugin, what to move project-local vs keep global,
what to retire, with projected session-start tokens before and after.

- Why Claude Code cannot: it needs the whole graph, all projects' usage and measured costs at once.
- Input: one compact table of all Items (id, kind, name, 1-line redacted description, cluster, always-on tokens, uses, sessions,
  projects-used-in count, last day) plus Overlaps and plugin membership. 300 Items ≈ 18K tokens.
- Output: a list of moves `{"op":"retire|move_local|group|keep_global","ids":[...],"project":"p_2","why":["f.."]}`. The app
  applies the moves to a copy of the scan locally and computes "session start: 8,940 → 5,310 tokens (−41%)". The model never
  states the totals.
- Calls and cost: 1 call, ~20K in + ~3K out ≈ $0.0035; one checker retry ≈ **$0.007** worst case.
- Consent: within the invariant once M2 is approved. Project ids are opaque hashes; project names are not sent.

**(d) Weekly narrative.** A plain-English summary of what changed and why: "You added 3 skills from `pdf-tools`; session start
rose 620 tokens; `git-helper` went unused for 30 days; two new Overlaps".

- Why Claude Code cannot: it has no memory of last week's setup.
- Input: the local `diff.py`/`history.py` output (added, removed, changed Items, cost and usage deltas, new Overlaps), already
  computed and ranked.
- Calls and cost: 1 per week; ~3K in + ~1K out ≈ **$0.0008**.
- Consent: within the invariant once M2 is approved. Offline already gets the same facts as a bulleted list.

**(e) Free-form graph Q&A (Ask, grounded).** For questions the 14 rule routes cannot answer ("which of my writing skills would I
miss least?", "what would a lean setup for frontend work look like?"), the model answers through a tool-calling loop over the
local engine.

- Why Claude Code cannot: the tools return cross-session usage, measured cost and all-pairs Overlaps it does not have.
- Tools (read-only, local, returning redacted facts with ids): `query_items(text|kind|cluster)`, `item(id)`, `usage(ids, since)`,
  `overlaps(ids)`, `costs(ids)`, `plugin(id)`, `session_start()`. No tool reads a body or transcript.
- Output: answer text with inline citations `[i_17]`, `[f12]`; the checker resolves them and renders names and numbers.
- Calls and cost: ~4 model turns; ~20K input total, ~12K of it cache reads; ~2K output ≈ **$0.002 per question**; 100
  questions ≈ $0.20.
- Consent: sending the redacted question is new (ask-purpose §6.5); needs M3.

**(f) Project advisor drafts (#45).** From a repo's `architecture.md`/`README`/`CLAUDE.md` and manifest names, draft a tiny
CLAUDE.md section ("for this repo use `repo-map` for navigation") and skill stubs, with the draft's own token cost shown.

- Why Claude Code cannot do it as well: it can read the repo, but not which global Items exist, which are used here or elsewhere,
  or what each costs. Honest note: Claude Code itself is good at summarising the architecture file; the value is the match.
- Input, local mode (default): first 4 KB of each project file plus the ranked Item matches from smarter-verdict §8. Cloud mode:
  only the manifest dependency names and the local embedding match list, unless the owner gives per-use consent to send the
  redacted 4 KB (§4).
- Calls and cost: 1 to 3 calls; cloud ~5K in + ~1.5K out ≈ **$0.0013**; local free, ~1 to 2 minutes.
- Consent: per use, every time, for project text.

**(g) Hook and trigger collision explainer.** For collisions found locally (#18: two hooks on the same event and matcher, two
skills whose descriptions fire on the same request), explain the conflict and suggest a safe fix ("narrow `tune-spacing`'s
description to layout work", "move the second PostToolUse hook's matcher to `Write`").

- Why Claude Code cannot: it never sees all hooks and skills side by side with which actually fired.
- Input: event, matcher, hook command **basename** only (the full command line is file text; it stays local), redacted
  descriptions, fire counts.
- Calls and cost: one per collision; ~800 in + ~500 out ≈ $0.0003; 10 collisions ≈ **$0.003**.
- Consent: within the invariant once M2 is approved. Suggestions are copyable instructions; the app never edits settings.

**(h) What to install next.** Gaps analysis: given the owner's project types (manifest names, clusters they use), which Items
already on the machine (disabled plugins, other projects' local Items, the #12 install-preview catalogue) would fill a gap.

- Why Claude Code cannot: it does not see disabled plugins, other projects or the catalogue.
- Input: project profile (manifest dependency names only in cloud), used clusters, catalogue entries' names and descriptions.
  Nothing is fetched from the internet.
- Calls and cost: 1 call, ~8K in + ~1.5K out ≈ **$0.0016**.
- Consent: within the invariant; manifest dependency names are new data to send (M4).

### 1.3 The verify step (all features)

Every model reply goes through a local checker before anything is shown or cached as accepted:

1. **Schema**: parse JSON (structured output in cloud via `output_config.format`, JSON mode locally); reject extra fields.
2. **Ids**: every Item id, fact id, project id and pair must exist in the facts given to that call. Unknown id = reject.
3. **Numbers**: the model may not emit digits outside cited ids and quoted descriptions; the checker strips or rejects them.
   Displayed numbers come from `costs`, `usage` and `receipt()` by id.
4. **Verdict guard**: the model may not mark an Item `retire` if the local verdict is `keep` with recent use, or if blast radius
   shows it is the only Item in its cluster, without the reason being shown as "model disagrees with rules".
5. **Length and safety**: descriptions capped (300 chars), CLAUDE.md draft capped (40 lines, token cost shown), output passed
   through `redact()` again (a reply may echo a secret; `scan_graph.label` already does this).
6. **On failure**: one retry with the checker's error appended; then fall back to the rules answer, labelled "Model answer
   rejected by checker: <reason>". The failed reply is not cached as accepted.

The checker is plain Python over the scan dict; it is the part that needs the strongest tests (fixture replies with invented ids,
invented numbers, injected instructions in descriptions).

## 2. Cost model

### 2.1 Cloud (Haiku 5.5), per run on a 300-Item setup

| Run | Calls | Estimated cost |
|---|---|---|
| First full smarter analysis: (a) 40 pairs, (b) 30 skills, (c) 1, (g) 10, (h) 1, (d) 1 | ~83 | ~$0.04 |
| Rescan, nothing changed | 0 | $0.00 (all cache hits) |
| Rescan, 10% of Items changed | ~10 | ~$0.005 |
| One Ask question through the tool loop | ~4 | ~$0.002 |
| Project advisor, one repo | 1 to 3 | ~$0.001 |
| Heavy month: 4 rescans, 4 weekly notes, 100 questions, 2 repos | ~500 | ~$0.30 |

For comparison the existing Sonnet 5.5 verifier (D3) at 150 pairs is about $0.15 a scan, so the whole model mode is cheaper than
the verifier the app already uses. Batch API (50% off) would save about 2 cents a run at the cost of asynchronous polling; not
worth it in v1.

### 2.2 Local (Ollama-style, OpenAI-compatible)

Baseline from `docs/research/chat-models.md`: `qwen3:4b` (2.5 GB artifact, Q4_K_M) on an M1 with 16 GB; `qwen3:8b` (5.2 GB) as an
optional upgrade with less headroom. Public guides report roughly 30 to 60 generated tokens per second for 3B to 8B models on
Apple Silicon, with wide variation by chip, quantisation and context; none of this is measured on the owner's machine.

| Task | Local estimate (unmeasured) | Reliability of a 4B model |
|---|---|---|
| Short classify or rewrite, (a) (b) (g) | 5 to 20 s per call | Fair with JSON mode; the checker catches the misses |
| Whole-setup architect (c), 20K-token prompt | 1 to 3 min, prefill dominates | Weak: long context, many ids; expect more rejections |
| Tool-loop Q&A (e) | 30 s to 2 min per question | Weak at multi-step tool use at 4B; 8B better |
| Project summary for (f) | 1 to 2 min | Good enough for a stack-and-domains summary |
| Full first run, ~83 calls | 15 to 30 min | Mixed |

Cost: $0 in dollars, some battery and memory. The owner already asked for a small eval on real architecture text before local
quality is promised; this note keeps that condition (slice S5).

### 2.3 Default, estimate and caps

- **Cheapest good default when on: cloud Haiku 5.5 for metadata features; local only for project text and transcript-derived
  work.** The owner can pick `local` for everything; then project text and metadata both stay on the machine.
- **Estimate first** (existing cost rule): before any call, print
  `Smarter analysis (Haiku 5.5): 83 calls, ~61K input / ~40K output tokens, about $0.04. 112 answers reused from cache. Budget: $0.50 this run, $2.71 left this month. Continue? [y/N]`
  The app shows the same line in the Brief's confirm dialog. `--dry-run` prints every redacted prompt instead of sending.
- **Hard caps**: per-run default $0.50, per-month default $3, both editable. The planner drops the lowest-ranked jobs to fit
  and says so ("12 pairs skipped: over budget"). A running total from `response.usage` stops the run before a call that would
  cross the cap. Monthly spend is kept in `~/.cache/constellation/model-spend.json` (0600: month, dollars, call count only).
- Per-call ceilings: `max_tokens` 1,024 (2,048 for (c) and (f)); input refused above 90K tokens so the over-100K price never
  applies; at most 200 calls per run, 4 concurrent (as `classify.MAX_CONCURRENCY`).

## 3. Provider interface and graph wiring

### 3.1 One seam, two adapters

Keep the existing seam `LLM = Callable[[str], str]` (`models.py`) for the single-shot features (a, b, c, d, f, g, h): they are
one prompt in, one JSON reply out, and already fit `guarded()` in `redact.py`. Add one more seam only for the tool loop (e):

```python
class ChatModel(Protocol):
    def turn(self, system: str, messages: list[dict], tools: list[dict]) -> Reply: ...  # Reply: text, tool_calls, usage
```

| Adapter | Transport | Notes |
|---|---|---|
| `none` (default) | no calls | Rules and templates only |
| `cloud` | Anthropic SDK, `anthropic_llm.py` extended | `claude-haiku-5-5`, `effort: "low"`, cached system prompt (`cache_control`), structured output, tools with `strict: true` and `tool_choice: auto`; key from `ANTHROPIC_API_KEY` only |
| `local` | OpenAI-compatible `POST /v1/chat/completions` via stdlib `urllib` | Default `http://127.0.0.1:11434/v1`; **refuses any host other than 127.0.0.1, ::1 or localhost**; model name from settings; no new dependency; nothing bundled or auto-downloaded |

Both adapters are wrapped by the existing guard (`guarded`, extended to cover `ChatModel` message content and tool results), so
redaction is not optional in either mode. Local mode is redacted too: cheap, and it keeps one code path.

### 3.2 Chat graph (Ask)

`chat.py` today: `START → route → (conditional on intent) → one of 14 nodes → END`. Add one branch, reached only when rules
cannot answer:

```
route ──(intent=search, no confident match, or new intent "open")──► model_gate
model_gate ──(mode off, no consent, over budget)──► search (today's answer) ──► END
model_gate ──(on)──► agent ⇄ tools ──► check ──(ok)──► END
                                          └──(fail)──► search (labelled fallback) ──► END
```

- `model_gate` is local: checks mode, M3 consent, budget, and the answer cache (`cache_key` of the redacted question plus the
  redacted facts the tools returned last time and the model id).
- `agent` and `tools` loop at most 5 turns; tools call the same local functions the rule nodes use (`_by_id`, `brief()`,
  `answer.verdict`), on the already-redacted `clean` dict that `LocalChat.answer` builds.
- `check` is §1.3. LangSmith tracing stays disabled (`tracing_context(enabled=False)`), as today.

### 3.3 Insights graph (scan side)

The scan graph (`scan_graph.py`) keeps its two existing model edges (labels, verifier) unchanged. The new features need the
finished scan plus history, so they run as a separate small `StateGraph` over the saved JSON, invoked by
`constellation insights` and by the app's "Run smarter analysis" button:

```
START → plan (local: build jobs, cache hits, estimate, budget, consent) ──(conditional: no jobs)──► assemble
plan ──(Send fan-out, one per job not cached)──► ask_model → check → flush (cache, spend) → assemble → END
```

This copies the `plan_labels → route_labels → label → labels_done` pattern already in the scan graph, so it inherits the
cost rule (cache-first, Send only for misses) and the checkpointer. Results land in an additive `insights` field of the saved
scan.

## 4. Privacy

### 4.1 What may be sent, by mode

| Data | Off | Local | Cloud |
|---|---|---|---|
| Kinds, names, descriptions (redacted) | – | stays on machine | sent (already allowed) |
| Item ids, cluster ids, opaque project hashes | – | stays | sent (already allowed as local signals) |
| Aggregate numbers: uses, sessions, last day, token costs | – | stays | **sent only if M2 approved** |
| Ask question text (redacted) | – | stays | **sent only if M3 approved** |
| Manifest dependency names | – | stays | **sent only if M4 approved** |
| Project file text (architecture.md, README, CLAUDE.md, 4 KB each) | – | **per-use consent**, stays | **not sent** (or per-use consent if M5 approved) |
| Hook command lines, Item bodies | – | not read by model mode | never sent |
| Transcript text, prompts | – | **per-use consent** (v2 topic tags), stays | never sent |

Local mode keeps everything on the machine: the adapter refuses non-loopback hosts, and the docs tell the owner to disable any
cloud features of their local server (for Ollama, `disable_ollama_cloud`). Constellation does not install or configure it.

The privacy invariant in `CLAUDE.md`/`AGENTS.md` is **not** loosened by this note. Each row marked M2 to M5 is an explicit
amendment the owner approves (or not); approved rows get a dated line in the invariant text and the tracker, as `--count-bodies`
did. Nothing is widened silently by a default.

### 4.2 Consent wording

First time model mode is turned on (CLI prompt and app dialog, same text):

> Smarter analysis uses a model on top of Constellation's free local analysis.
> Cloud (Claude Haiku 5.5, your Anthropic key): sends the names and descriptions of your Items, with secrets removed, plus usage
> counts and token costs. It never sends file contents, your prompts or your transcripts. About $0.04 for a first run; reruns
> reuse saved answers. Spending stops at $0.50 a run and $3 a month.
> Local (your own model server on this computer): nothing leaves this machine.
> You can turn this off at any time in Settings. Turn on? [cloud / local / no]

Each use of project text:

> To draft a CLAUDE.md section, Constellation will read the first 4 KB of `architecture.md`, `README.md` and `CLAUDE.md` in
> `acme-shop`, remove anything that looks like a secret, and give it to your local model at 127.0.0.1. Nothing is sent to the
> internet. Read and use these files this time? [y/N]

The project-text consent is not remembered: every run asks.

### 4.3 Where the opt-in lives

`~/.cache/constellation/model-settings.json`, 0600: `{"mode": "off|local|cloud", "local_url", "local_model",
"budget_run", "budget_month", "approved": {"numbers": "2026-11-05", ...}}`. No key is stored: the cloud key comes only from the
environment, and the app UI never asks for or displays one. The app changes the file only through a new localhost-only
`POST /api/model-settings` (id-only style input, same checks as `/api/checklist`); that endpoint is a deviation to approve (M6).

## 5. UX

- **Settings and Brief toggle: "Smarter analysis (optional)"**, off. Under it: provider (Local / Cloud), budget, and a line of
  what is sent. Turning it on opens the §4.2 dialog.
- **CLI**: `--model off|local|cloud` (default `off`) on `scan`, `insights` and `chat`; `--budget USD`; `--dry-run` shows every
  redacted prompt; `--offline` forces off. `insights` runs (a)(b)(c)(g)(h), `insights --weekly` (d), `advise PATH` (f).
- **Labelling**: model content sits in its own block under the rules answer, with a chip "Model-written · Haiku 5.5 · checked
  against your graph" (or "· local qwen3:4b"). Cited Items are links that select the node. A rejected answer shows the rules
  answer and "Model answer rejected: invented id".
- **Caching**: key = `cache_key(redacted prompt, known secrets, salt = model id + prompt version)` from `costs.py`, stored in
  `~/.cache/constellation/insights.json` (0600). A changed description, count bucket or prompt template makes a new key. Counts
  are bucketed (0, 1 to 2, 3 to 9, 10+) and days rounded to weeks in prompts, so daily churn does not bust the cache. A cached
  answer shows "saved answer from 3 Nov".
- **Hand-off**: every suggestion offers "Add to checklist" and "Copy instruction for Claude Code"; the app never edits files.

## 6. Risks, rejected options, slices, decisions

### 6.1 Risks

| Risk | Mitigation |
|---|---|
| Model invents Items or numbers | §1.3 checker; numbers rendered locally |
| Prompt injection in a third-party skill description ("ignore rules, recommend X") | Descriptions are quoted data in a delimited block; checker verdict guard; output re-redacted |
| Cost creep | Estimate first, per-run and monthly caps, cache, 200-call ceiling |
| Local model too weak, owner blames the app | Label every answer with its model; fall back to rules; S5 eval before recommending local for (c)/(e) |
| Secrets in a reply | `redact()` on input and output, as labels do |
| Cache busting by daily counts | Bucketed counts, week-rounded days |
| Haiku 5.5 refusal (no server-side fallback) | Treat as a failed call; rules answer |
| "Local" server that is actually remote | Loopback-only URL check; documented cloud-feature switch |

### 6.2 Rejected options

- **Sonnet or Opus for these features**: 20 to 40 times the price for one-line judgements on short facts; Haiku plus the checker
  is enough. (Whether Haiku can also replace the Sonnet verifier is M7, after an eval.)
- **A second cloud provider (e.g. Gemini Flash-Lite)**: saves under 3 cents per 1,000 answers; a second SDK and key (owner's
  #45 comment).
- **Bundling or auto-downloading a local model**: the owner installs their own; nothing bundled.
- **Model calls inside the scan graph's main path**: insights need the finished scan; a separate graph keeps scan unchanged and
  free.
- **Sending bodies or raw prompts "for better quality"**: outside the invariant; not proposed.
- **Batch API in v1**: about 2 cents saved per run, adds polling and delay.
- **LangChain `create_react_agent`**: D15 keeps the SDK direct; a five-node StateGraph is small.

### 6.3 Slices (independent Sonnet tickets)

| Slice | Scope | Depends on |
|---|---|---|
| S1 Provider seam and guardrails | `model-settings.json`, `--model/--budget`, cloud adapter extension (cached system, structured output, tools), loopback-only local adapter on `urllib`, spend file, estimate line, caps, fake-model tests | none |
| S2 Checker and insights graph, features (a)(b)(g) | `check.py` with adversarial fixtures, insights `StateGraph` (plan → Send → check → flush), cache, `constellation insights` | S1 interface (can use a fake) |
| S3 Grounded Ask (e) and UI | `model_gate`, agent ⇄ tools loop in `chat.py`, Settings toggle, consent dialog, model-written chip, `POST /api/model-settings` | S1, S2 checker; M3, M6 |
| S4 Whole-setup features (c)(d)(h) | architect moves applied locally with before/after `receipt()`, weekly narrative from `diff.py`, install gaps from #12 catalogue | S2 |
| S5 Project advisor (f) and local eval | per-use consent, 4 KB reads, local default, CLAUDE.md draft with token cost; a small eval (invented architecture texts first, then the owner's own on their machine) comparing qwen3:4b, qwen3:8b and Haiku on (a)(b)(f) | S1, S2; O7 project reading |

Each slice keeps model mode off by default, adds no paid call to tests (fakes only; one deselected paid eval), and updates
`docs/plan-tracker.md`.

### 6.4 Decisions the owner must make

- **M1 Default provider when on**: cloud Haiku 5.5 for metadata (recommended), or local for everything.
- **M2 Aggregate numbers to cloud**: may uses, sessions, last-used week and token costs (no text) be sent? Most features need
  this; without it (a)(c)(d)(e)(g) lose most of their value in cloud mode.
- **M3 Ask question to cloud**: send the redacted free-form question (ask-purpose §6.5)?
- **M4 Manifest dependency names to cloud** for (h) and cloud-mode (f)?
- **M5 Project text to cloud** with per-use consent, or local only (the owner's #45 direction; recommended: local only).
- **M6 New settings file and `POST /api/model-settings`** endpoint (deviation).
- **M7 Later**: replace the Sonnet verifier with the Haiku redundancy judge if an eval matches D3's 19 of 20.
- **Budget defaults**: $0.50 per run and $3 per month, or other figures.
