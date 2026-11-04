import json
import stat

import pytest
from fakes import FakeEmbedder, FakeVerifier, pairs, verdict, write_skill

from constellation import overlaps, scan


@pytest.fixture
def config(tmp_path):
    write_skill(tmp_path / "claude", "pdf-reader", "Open the file and read it.", description="Reads PDF files")
    write_skill(tmp_path / "claude", "pdf-viewer", "Parse the document and list points.", description="Views PDF files")
    return tmp_path / "claude"


def run(config, verifier, cache):
    return scan(config, embedder=FakeEmbedder({"PDF": [1.0, 0.0, 0.0]}), verifier=verifier, verdict_cache=cache)


def test_a_rescan_asks_the_verifier_nothing_and_gives_the_same_verdicts(config, tmp_path):
    cache = tmp_path / "verdicts.json"
    first, second = FakeVerifier(default=verdict("overlap", "both read PDFs")), FakeVerifier()

    one, two = run(config, first, cache), run(config, second, cache)

    assert len(first.prompts) == 1 and second.prompts == []
    assert one.overlaps == two.overlaps and one.overlaps[0].reason == "both read PDFs"


def test_a_cached_wrapper_keeps_its_direction(config, tmp_path):
    cache = tmp_path / "verdicts.json"
    reply = verdict("wrapper", "viewer calls reader", wraps="B")
    run(config, FakeVerifier(default=reply), cache)

    assert pairs(run(config, FakeVerifier(), cache)) == [("pdf-viewer", "pdf-reader", "wrapper")]


def test_a_changed_description_is_asked_again(config, tmp_path):
    cache = tmp_path / "verdicts.json"
    run(config, FakeVerifier(), cache)
    write_skill(config, "pdf-reader", "Open the file and read it.", description="Reads PDF files, quickly")
    verifier = FakeVerifier()

    run(config, verifier, cache)

    assert len(verifier.prompts) == 1


def test_a_body_edit_that_changes_a_signal_is_asked_again_but_one_that_does_not_is_not(config, tmp_path):
    cache = tmp_path / "verdicts.json"
    run(config, FakeVerifier(), cache)
    write_skill(config, "pdf-reader", "Open the document and read it.", description="Reads PDF files")  # same word count
    same = FakeVerifier()
    run(config, same, cache)
    write_skill(config, "pdf-reader", "Open the file and read it twice.", description="Reads PDF files")  # one more word
    longer = FakeVerifier()

    run(config, longer, cache)

    assert same.prompts == [] and len(longer.prompts) == 1


def test_the_cache_file_is_private_and_holds_no_secret(tmp_path):
    secret = "ghp_" + "aB3dE5gH" * 4 + "7jK9"
    root, cache = tmp_path / "claude", tmp_path / "cache" / "verdicts.json"
    write_skill(root, "pdf-reader", "Read it.", description=f"Reads PDF files with {secret}")
    write_skill(root, "pdf-viewer", "View it please.", description="Views PDF files")

    run(root, FakeVerifier(default=verdict("overlap", "same")), cache)

    assert stat.S_IMODE(cache.stat().st_mode) == 0o600
    assert secret not in cache.read_text() and "pdf-reader" not in cache.read_text()  # keys are hashes of the redacted prompt


def test_unreadable_replies_are_not_cached(config, tmp_path):
    cache = tmp_path / "verdicts.json"
    run(config, FakeVerifier(default="nonsense"), cache)
    verifier = FakeVerifier()

    run(config, verifier, cache)

    assert len(verifier.prompts) == 1


def test_a_failed_call_is_not_cached(config, tmp_path):
    cache = tmp_path / "verdicts.json"
    run(config, FakeVerifier(fail_for={"pdf-reader": "network blocked"}), cache)
    verifier = FakeVerifier()

    run(config, verifier, cache)

    assert len(verifier.prompts) == 1


@pytest.mark.parametrize("content", ["not json", json.dumps([1, 2]), json.dumps({"k": 5})], ids=["corrupt", "wrong-shape", "wrong-value"])
def test_a_damaged_cache_is_ignored(config, tmp_path, content):
    cache = tmp_path / "verdicts.json"
    cache.write_text(content)
    verifier = FakeVerifier(default=verdict("overlap", "same"))

    constellation = run(config, verifier, cache)

    assert len(verifier.prompts) == 1 and constellation.warnings == []


def test_a_cached_reply_that_no_longer_parses_is_asked_again(config, tmp_path):
    cache = tmp_path / "verdicts.json"
    run(config, FakeVerifier(), cache)
    stored = json.loads(cache.read_text())
    cache.write_text(json.dumps({key: "tampered" for key in stored}))
    verifier = FakeVerifier()

    run(config, verifier, cache)

    assert len(verifier.prompts) == 1


def test_an_unwritable_cache_is_a_warning_and_the_verdicts_still_come_out(config, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("a file where a directory is needed")

    constellation = run(config, FakeVerifier(default=verdict("overlap", "same")), blocker / "verdicts.json")

    assert [o.verdict for o in constellation.overlaps] == ["overlap"]
    assert len(constellation.warnings) == 1 and constellation.warnings[0].startswith("could not save the verdict cache: ")


def test_nothing_is_written_when_nothing_new_was_learned(config, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("a file")

    constellation = run(config, FakeVerifier(fail_for={"pdf-reader": "down"}), blocker / "verdicts.json")

    assert [w for w in constellation.warnings if "cache" in w] == []


def test_without_a_path_the_default_cache_location_is_used(config, tmp_path, monkeypatch):
    default = tmp_path / "default" / "verdicts.json"
    monkeypatch.setattr(overlaps, "DEFAULT_CACHE", default)

    run(config, FakeVerifier(), None)

    assert default.exists()


def test_a_different_verifier_model_is_not_served_the_old_models_verdicts(config, tmp_path):
    cache = tmp_path / "verdicts.json"
    embedder = FakeEmbedder({"PDF": [1.0, 0.0, 0.0]})
    scan(config, embedder=embedder, verifier=FakeVerifier(default=verdict("overlap", "same")), verdict_cache=cache, verifier_model="a")
    same, other = FakeVerifier(), FakeVerifier()

    scan(config, embedder=embedder, verifier=same, verdict_cache=cache, verifier_model="a")
    scan(config, embedder=embedder, verifier=other, verdict_cache=cache, verifier_model="b")

    assert same.prompts == [] and len(other.prompts) == 1
