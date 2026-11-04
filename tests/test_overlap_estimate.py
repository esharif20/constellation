import pytest
from fakes import FakeEmbedder, FakeVerifier, write_skill

from constellation import scan
from constellation.overlaps import estimate_cost


def test_the_estimate_is_input_and_output_tokens_at_sonnet_prices():
    # $2 per million input tokens, $10 per million output tokens, 300 output tokens assumed per call
    assert estimate_cost(10, 1_000_000) == pytest.approx(2.0 + 10 * 300 * 10 / 1_000_000)


def test_no_calls_cost_nothing():
    assert estimate_cost(0, 0) == 0


def test_the_scan_announces_how_many_pairs_will_be_asked_and_their_size_before_asking(tmp_path):
    root = tmp_path / "claude"
    write_skill(root, "pdf-reader", "Read it.", description="Reads PDF files")
    write_skill(root, "pdf-viewer", "View it please.", description="Views PDF files")
    seen = []
    verifier = FakeVerifier()

    scan(
        root,
        embedder=FakeEmbedder({"PDF": [1.0, 0.0]}),
        verifier=lambda p: seen.append(("asked", len(verifier.prompts))) or verifier(p),
        verdict_cache=tmp_path / "v.json",
        on_verify=lambda calls, tokens: seen.append((calls, tokens)),
    )

    [(calls, tokens), asked] = seen
    assert calls == 1 and tokens == len(verifier.prompts[0]) // 4 and asked == ("asked", 0)  # announced first


def test_cached_pairs_are_not_announced(tmp_path):
    root = tmp_path / "claude"
    write_skill(root, "pdf-reader", "Read it.", description="Reads PDF files")
    write_skill(root, "pdf-viewer", "View it please.", description="Views PDF files")
    announced = []
    kwargs = {"embedder": FakeEmbedder({"PDF": [1.0, 0.0]}), "verifier": FakeVerifier(), "verdict_cache": tmp_path / "v.json"}
    scan(root, **kwargs)

    scan(root, on_verify=lambda *a: announced.append(a), **kwargs)

    assert announced == []
