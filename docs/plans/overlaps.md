# Plan: Overlap detection (#6)

Layers run cheapest first; each later layer only sees pairs the earlier ones left undecided. New module `src/constellation/overlaps.py`, added to `only_mutate`. Tests go through `scan()` and `cli.main` with a new fixture dir `tests/fixtures/overlap_config` (the existing fixture's tests assert exact Item sets, so it stays as is).

## Data model

- `models.py`: `Overlap(a_id: str, b_id: str, verdict: str, reason: str)`, frozen. `Verdict = Literal["duplicate", "wrapper", "overlap", "distinct"]`. `Constellation.overlaps: list[Overlap]`, sorted by `(a_id, b_id)`.
- Order: `a_id < b_id`, except for `wrapper`, where `a_id` is the wrapper and `b_id` is what it calls. `distinct` verdicts are kept so a rescan can show they were checked. #10 decides whether to draw them.
- Only skills and agents have bodies (`read_items` already returns `bodies`), so only they can overlap. Hooks, MCP servers, connectors and plugins are left out.

## Layer 1: exact content (no model)

`exact_duplicates(items, bodies) -> list[Overlap]`. The key is `sha256(normalise(body))`, where `normalise = "\n".join(l.rstrip() for l in body.strip().splitlines())`. Name and description are not hashed: ids differ, and a renamed copy is still a copy. Empty bodies are skipped, because they would all match each other. A group of n copies becomes n-1 pairs, each anchored on the lowest id. All n² pairs would be noise. Reason: `"identical instructions"`. `installed_plugins.json` now keeps one version per plugin, so real copies sit across plugins and user skills (for example `skill-creator` as a user skill and in two plugins). The hash does not care where a copy lives.

## Layer 2: wrapper (no model)

`wrappers(items, bodies, decided) -> list[Overlap]`. A wraps B when A's normalised body has at most `WRAPPER_MAX_WORDS = 80` words and names exactly one other skill or agent, B, in an invocation form: `/B`, `` `B` ``, or `B skill`/`B agent`, matched as a whole token. B's body must be longer than A's. Reason: `"'A' is N words and only hands off to 'B'"`. This rule favours precision. Guarding against false positives: a bare English word does not count as a mention, long bodies never qualify, and a short body that names two Items is not a wrapper. Anything the rule misses still reaches the verifier, which can also return `wrapper`.

## Layer 3: candidates (local embeddings)

- No recomputing. Split `cluster.py` into `item_vectors(items, embed) -> tuple[dict[str, list[float]], bool]`, which returns the unit vectors (mean-centred when there are 10 or more) and whether they were centred, and `cluster(items, labels, vectors, centred, threshold)`. `scan()` embeds once and passes the vectors to both. Update `tests/eval/test_cluster_quality.py` to match.
- `candidates(items, vectors, decided) -> tuple[list[tuple[str, str]], list[str]]`. For each skill or agent, take its `TOP_K = 3` nearest neighbours with centred cosine ≥ `CANDIDATE_THRESHOLD = 0.5`. Same-name pairs are always added, which is how cross-plugin copies with edited bodies get found. Pairs from layers 1 and 2 are skipped. Skill-skill, agent-agent and skill-agent pairs are all allowed.
- Cap: `MAX_PAIRS = 150`, highest similarity first, ties broken by id. Dropped pairs become a single warning. On 255 Items, top-3 alone gives at most about 380 pairs.

## Layer 4: verifier (stronger model)

- Seam: `scan(..., verifier: LLM | None = None, verdict_cache: Path | None = None)`. Same `LLM` type, wrapped as `guarded(verifier, secrets)`. Real model: `anthropic_llm(client=None, model=MODEL)` gains a `model` param; `VERIFIER_MODEL = "claude-sonnet-5-5"` (checked against the claude-api skill: $2/$10 per MTok, effort supported). Use `effort: "low"` and `max_tokens=2048`.
- `verify(pairs, items, bodies, llm, known, cache_path) -> tuple[list[Overlap], list[str]]`. Each body goes through `redact(body, known)` first, then is cut to `MAX_BODY_CHARS = 8000` with a `[truncated]` marker. Redacting before cutting means a cut never splits a secret. The guard then redacts the whole prompt again. The prompt wraps the bodies in `<item_a>`/`<item_b>` tags, says the text is data and not instructions, and asks for JSON only: `{"verdict": ..., "reason": ...}`.
- Parsing: strip code fences, then `json.loads`. The verdict must be in the set; the reason is cleaned like `classify._clean` (one line, 200 chars). Anything else becomes the warning `could not verify 'A' / 'B': unreadable reply` and the pair gets no verdict. A `ProviderError` becomes the same kind of warning. A prompt injection can at worst pick a wrong verdict.
- LangGraph: same shape as `classify`. A conditional edge from START returns `list[Send]`, which is map: one branch per pair. Branch outputs merge through `Annotated[list[Overlap], operator.add]` and `Annotated[list[str], operator.add]`, which is reduce, with a list reducer where `classify` used a dict one. The fan-in to END is implicit. `config={"max_concurrency": 4}` caps parallel calls. shortcut: the graph is duplicated from classify rather than shared; generalise it if a third fan-out appears.
- Cache: `~/.cache/constellation/overlap-verdicts.json`, mode 0o600. The key is the sha256 of the redacted prompt, so a template change invalidates the cache by itself and no secret reaches the file. Make `costs._load/_save` public as `load_cache/save_cache` and reuse them. An unwritable cache is a warning.

## CLI

- `scan --no-verify` skips layer 4. Before a real verify run, stderr shows an upper bound: `verifying at most 150 pairs with claude-sonnet-5-5, under $2.70 (cached pairs are free)`. The figure is 150 × (4k input + 1k output tokens) at Sonnet 5.5 prices. `main(..., verifier=...)` makes this injectable for tests.
- Dry run: record `--- VERIFY ---` prompts and reply `{"verdict":"distinct","reason":"dry-run"}`, with the verdict cache in the temp dir. The dry-run embedder currently returns zero vectors, which would yield no candidates. When fastembed is installed, the dry run uses the real local embedder (it runs locally, so it sends nothing) and still records the texts. Otherwise it prints that no verifier prompts can be shown.

## Eval

`tests/eval/test_overlap_quality.py`, `@pytest.mark.eval`, skipped without `ANTHROPIC_API_KEY`. Data in `tests/eval/overlap_pairs.py`: 20 invented pairs (body A, body B, expected verdict), 5 per verdict, including near-misses such as "review a PR" vs "review prose". It calls `verify()` directly with the real guarded model. It prints a confusion table plus per-verdict precision and recall, and asserts that "flagged" (not distinct) precision ≥ 0.8 and recall ≥ 0.7. That is a regression guard on invented data, not proof of quality on a real setup. Cost is about $0.20 per run. Update the pytest `eval` marker text. The real check (that stop-slop, skill-creator and shadcn surface) is done by the user on `~/.claude`, and its output is never committed.

## Slices (red, then green; one commit each)

1. `Overlap` + `Constellation.overlaps`; the cli JSON includes `overlaps: []`.
2. Layer 1 via `scan(OVERLAP_FIXTURE)` with no providers. Tests: whitespace-variant copies become a duplicate; different names still match; empty bodies don't match; 3 copies give 2 anchored pairs; the output order is stable.
3. Layer 2. Tests: a short `/deep-review` body becomes a wrapper with the right a/b; a long body that mentions another skill does not; a short body that names two skills does not; a bare-word mention does not.
4. *(parallel with 1–3)* `item_vectors` refactor; existing cluster tests stay green.
5. Layer 3 via `scan(embedder=FakeEmbedder, verifier=FakeVerifier)`. Tests: pairs the verifier was asked about; hooks and MCP excluded; decided pairs skipped; same-name pair added; cap warning.
6. Layer 4. Add `FakeVerifier` to `tests/fakes.py` (it maps a name pair to a reply and records prompts). Tests: verdict and reason stored; both bodies in the prompt; truncation marker; a fixture secret is never in the prompts; provider failure, bad JSON and an unknown verdict each give one warning while the scan continues; reason is one line; peak concurrency ≤ 4.
7. Verdict cache. Tests: a rescan makes 0 calls; an edited body triggers a call; the file is 0600; an unwritable cache is a warning.
8. CLI: `--no-verify`, the estimate line, `--- VERIFY ---` in the dry run, and no real cache written. Add the `model` param to `anthropic_llm`.
9. *(after 6)* Eval and fixtures.
10. Mutation gate: zero survivors on `overlaps.py`; manual real-setup check.

## Risks

- Full skill bodies leave the machine for the first time; until now only names and descriptions did. Redaction is pattern-based, so an unusual secret in a body could get through.
- The wrapper rule's thresholds are guesses; tune them on the real setup.
- The dry run now loads the local embedder, which is slower and different from before.
- Same-name copies with drifted bodies depend on the verifier.

## Out of scope

Suggestions and the approval pause (#7). Drawing Overlaps (#10). `Relation` kinds `duplicates`/`wraps` (#10 can derive them). Structured-output mode (upgrade if JSON failures show up in the eval).
