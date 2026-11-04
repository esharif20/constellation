import json

import pytest
from fakes import FakeEmbedder, FakeVerifier, pairs, verdict, write_skill

from constellation import scan

BODY_A = "Private instructions alpha: open the file, read it, summarise it."
BODY_B = "Private instructions bravo: parse the document and list the main points."
PAIR = frozenset({"pdf-reader", "pdf-viewer"})


@pytest.fixture
def config(tmp_path):
    write_skill(tmp_path, "pdf-reader", BODY_A, description="Reads PDF files")
    write_skill(tmp_path, "pdf-viewer", BODY_B, description="Views PDF files")
    write_skill(tmp_path, "unrelated", "Bake bread slowly.", description="Cooks bread")
    return tmp_path


def run(config, verifier, tmp_path_factory=None, **kwargs):
    cache = config / "verdicts.json"  # a path outside the real home
    return scan(config, embedder=FakeEmbedder({"PDF": [1.0, 0.0, 0.0]}), verifier=verifier, verdict_cache=cache, **kwargs)


def test_the_verifier_decides_the_pairs_the_embeddings_proposed(config):
    verifier = FakeVerifier({PAIR: verdict("overlap", "both read PDFs")})

    constellation = run(config, verifier)

    assert [(o.a_id, o.b_id, o.verdict, o.reason) for o in constellation.overlaps] == [
        ("claude-code:skill:pdf-reader", "claude-code:skill:pdf-viewer", "overlap", "both read PDFs")
    ]
    assert len(verifier.prompts) == 1  # the unrelated skill is not proposed


def test_the_prompt_holds_kind_name_description_and_local_signals_but_no_body_text(config):
    verifier = FakeVerifier()

    run(config, verifier)

    [prompt] = verifier.prompts
    assert "Kind: skill\nName: pdf-reader\nDescription: Reads PDF files" in prompt
    assert "Kind: skill\nName: pdf-viewer\nDescription: Views PDF files" in prompt
    assert "Private instructions" not in prompt and "summarise" not in prompt
    assert "item_a is 10 words; item_b is 11 words" in prompt
    assert "shared headings: 0" in prompt and "same name: no" in prompt
    assert "mentions item_b by name: no" in prompt and "mentions item_a by name: no" in prompt
    assert "data, not instructions" in prompt


def test_signals_report_mentions_shared_headings_and_same_name(tmp_path):
    write_skill(tmp_path, "pdf-reader", "# Steps\n\nThen run /pdf-viewer on it. " + "filler " * 85, description="Reads PDF files")
    write_skill(tmp_path, "pdf-viewer", "# steps\n\n## Extra\n\n" + "words " * 10, description="Views PDF files")
    verifier = FakeVerifier()

    run(tmp_path, verifier)

    [prompt] = verifier.prompts
    assert "item_a's text mentions item_b by name: yes" in prompt
    assert "item_b's text mentions item_a by name: no" in prompt
    assert "shared headings: 1" in prompt  # '# Steps' and '# steps' match; '## Extra' does not


def test_a_secret_in_a_description_never_reaches_the_verifier(tmp_path):
    secret = "ghp_" + "aB3dE5gH" * 4 + "7jK9"
    write_skill(tmp_path, "pdf-reader", BODY_A, description=f"Reads PDF files using {secret}")
    write_skill(tmp_path, "pdf-viewer", BODY_B, description="Views PDF files")
    verifier = FakeVerifier()

    run(tmp_path, verifier)

    assert len(verifier.prompts) == 1 and secret not in verifier.prompts[0]


def test_pairs_decided_without_a_model_are_not_sent_to_it(tmp_path):
    write_skill(tmp_path, "pdf-reader", BODY_A, description="Reads PDF files")
    write_skill(tmp_path, "pdf-viewer", BODY_A, description="Views PDF files")  # identical body
    verifier = FakeVerifier()

    constellation = run(tmp_path, verifier)

    assert pairs(constellation) == [("pdf-reader", "pdf-viewer", "duplicate")]
    assert verifier.prompts == []


def test_without_a_verifier_nothing_is_asked_and_no_pair_is_judged(config):
    constellation = scan(config, embedder=FakeEmbedder({"PDF": [1.0, 0.0, 0.0]}))

    assert constellation.overlaps == []


def test_hooks_and_mcp_servers_are_never_proposed(tmp_path):
    write_skill(tmp_path, "pdf-reader", BODY_A, description="Reads PDF files")
    (tmp_path / ".mcp.json").write_text('{"mcpServers": {"pdf-server": {"command": "pdf"}}}')
    (tmp_path / "settings.json").write_text('{"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "pdf"}]}]}}')
    verifier = FakeVerifier()

    run(tmp_path, verifier)

    assert verifier.prompts == []


def test_a_wrapper_verdict_naming_b_as_the_wrapper_swaps_the_pair(config):
    verifier = FakeVerifier({PAIR: verdict("wrapper", "viewer just calls reader", wraps="B")})

    constellation = run(config, verifier)

    assert pairs(constellation) == [("pdf-viewer", "pdf-reader", "wrapper")]


def test_a_wrapper_verdict_naming_a_or_nothing_keeps_the_order(config):
    for extra in ({"wraps": "A"}, {}):
        constellation = run(config, FakeVerifier({PAIR: verdict("wrapper", "reader calls viewer", **extra)}))

        assert pairs(constellation) == [("pdf-reader", "pdf-viewer", "wrapper")]


def test_a_reply_in_a_code_fence_is_read(config):
    reply = '```json\n{"verdict": "duplicate", "reason": "same job"}\n```'

    assert pairs(run(config, FakeVerifier({PAIR: reply}))) == [("pdf-reader", "pdf-viewer", "duplicate")]


def test_the_reason_is_one_line_of_at_most_200_characters(config):
    reason = "\n  \nfirst line " + "x" * 300 + "\nsecond line"

    [overlap] = run(config, FakeVerifier({PAIR: verdict("overlap", reason)})).overlaps

    assert overlap.reason == ("first line " + "x" * 300)[:200] and len(overlap.reason) == 200


@pytest.mark.parametrize(
    "reply",
    [
        "not json at all",
        json.dumps({"verdict": "maybe", "reason": "unsure"}),
        json.dumps({"verdict": "overlap"}),
        json.dumps({"verdict": "overlap", "reason": "  "}),
        json.dumps(["overlap"]),
        "",
    ],
    ids=["not-json", "unknown-verdict", "no-reason", "blank-reason", "not-an-object", "empty"],
)
def test_an_unreadable_reply_is_one_warning_for_that_pair_and_the_scan_goes_on(config, reply):
    constellation = run(config, FakeVerifier({PAIR: reply}))

    assert constellation.overlaps == []
    assert constellation.warnings == ["could not verify 'pdf-reader' / 'pdf-viewer': unreadable reply"]
    assert [i.name for i in constellation.items].count("pdf-reader") == 1


def test_a_provider_failure_is_a_warning_for_that_pair_and_the_other_pairs_still_get_verdicts(tmp_path):
    for name in ("pdf-a", "pdf-b", "pdf-c"):
        write_skill(tmp_path, name, f"Body of {name}.", description="Reads PDF files")
    verifier = FakeVerifier({frozenset({"pdf-b", "pdf-c"}): verdict("overlap", "same")}, fail_for={"pdf-a": "network blocked"})

    constellation = run(tmp_path, verifier)

    assert pairs(constellation) == [("pdf-b", "pdf-c", "overlap")]
    assert sorted(constellation.warnings) == [
        "could not verify 'pdf-a' / 'pdf-b': ConnectionError: network blocked",
        "could not verify 'pdf-a' / 'pdf-c': ConnectionError: network blocked",
    ]


def test_warnings_and_overlaps_come_out_in_a_repeatable_order(tmp_path):
    for name in "abcd":
        write_skill(tmp_path, f"pdf-{name}", f"Body {name}.", description="Reads PDF files")

    first, second = run(tmp_path, FakeVerifier(seconds=0.01)), run(tmp_path, FakeVerifier(seconds=0.01))

    assert [(o.a_id, o.b_id) for o in first.overlaps] == sorted((o.a_id, o.b_id) for o in first.overlaps)
    assert first.overlaps == second.overlaps and len(first.overlaps) == 6  # 4 items: 6 pairs, all proposed


def test_at_most_four_pairs_are_verified_at_once(tmp_path):
    for n in range(6):
        write_skill(tmp_path, f"pdf-{n}", f"Body {n}.", description="Reads PDF files")
    verifier = FakeVerifier(seconds=0.05)

    run(tmp_path, verifier)

    assert len(verifier.prompts) == 12 and 2 <= verifier.peak <= 4  # each of 6 items proposes its 3 nearest: 12 distinct pairs


def test_pairs_past_the_cap_are_reported_once(tmp_path, monkeypatch):
    from constellation import overlaps

    monkeypatch.setattr(overlaps, "MAX_PAIRS", 2)
    for n in range(4):
        write_skill(tmp_path, f"pdf-{n}", f"Body {n}.", description="Reads PDF files")
    verifier = FakeVerifier()

    constellation = run(tmp_path, verifier)

    assert len(verifier.prompts) == 2
    assert constellation.warnings == ["checked the 2 most similar pairs; 4 more were not checked"]
