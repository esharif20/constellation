"""Golden outputs of scan() on the invented fixtures. The graph refactor (#22) must not change any of them.
Re-record deliberately with: GOLDEN_RECORD=1 uv run --all-extras pytest tests/test_scan_golden.py"""

import dataclasses
import json
import os
from pathlib import Path

import pytest
from fakes import FakeCounter, FakeEmbedder, FakeLLM, FakeVerifier, verdict

from constellation import scan

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = FIXTURES / "golden"
CLAUDE, OVERLAP = FIXTURES / "claude_config", FIXTURES / "overlap_config"
LABELS = {"alpha": "alpha topic", "beta": "beta topic", "reviewer": "code review"}
PDF = frozenset({"pdf-reader", "pdf-viewer"})
PROSE = frozenset({"stop-slop", "tidy-prose"})


def _vectors():
    return {"PDF": [1.0, 0.0, 0.0], "prose": [0.0, 1.0, 0.0], "writing": [0.0, 1.0, 0.0]}


def _verifier(**kwargs):
    return FakeVerifier({PDF: verdict("overlap", "both read PDFs"), PROSE: verdict("duplicate", "same job")}, **kwargs)


def _run(tmp_path, config, calls, **kwargs):
    """scan() with caches under tmp_path; `calls` names the fakes whose recorded traffic is part of the golden output."""
    sent = []
    result = scan(
        config,
        cost_cache=tmp_path / "costs.json",
        verdict_cache=tmp_path / "verdicts.json",
        label_cache=tmp_path / "labels.json",
        on_verify=lambda n, t: sent.append([n, t]),
        **kwargs,
    )
    traffic = {name: sorted(getattr(fake, "prompts", None) or getattr(fake, "texts", None) or []) for name, fake in calls.items()}
    return {"result": dataclasses.asdict(result), "traffic": traffic, "on_verify": sent}


def _offline(tmp_path):
    fakes = {"llm": FakeLLM(LABELS), "counter": FakeCounter(), "verifier": _verifier(), "embedder": FakeEmbedder(_vectors())}
    return _run(
        tmp_path,
        CLAUDE,
        fakes,
        llm=fakes["llm"],
        counter=fakes["counter"],
        verifier=fakes["verifier"],
        embedder=fakes["embedder"],
        offline=True,
    )


def _labels_only(tmp_path):
    llm = FakeLLM(LABELS)
    return _run(tmp_path, CLAUDE, {"llm": llm}, llm=llm)


def _full(tmp_path):
    fakes = {"llm": FakeLLM({}, default="topic"), "embedder": FakeEmbedder(_vectors()), "verifier": _verifier(), "counter": FakeCounter()}
    return _run(
        tmp_path, OVERLAP, fakes, llm=fakes["llm"], embedder=fakes["embedder"], verifier=fakes["verifier"], counter=fakes["counter"]
    )


def _count_bodies(tmp_path):
    counter = FakeCounter()
    return _run(tmp_path, CLAUDE, {"counter": counter}, counter=counter, count_bodies=True)


def _failing_labels_and_embedder(tmp_path):
    llm, embedder = FakeLLM(LABELS, fail_for={"alpha": "boom"}), FakeEmbedder(_vectors(), fail_with="down")
    return _run(tmp_path, CLAUDE, {"llm": llm, "embedder": embedder}, llm=llm, embedder=embedder)


def _failing_verifier_and_counter(tmp_path):
    verifier, counter = _verifier(fail_for={"pdf-reader": "rate limited"}), FakeCounter(fail_with="no counts")
    return _run(
        tmp_path, OVERLAP, {"verifier": verifier, "counter": counter}, embedder=FakeEmbedder(_vectors()), verifier=verifier, counter=counter
    )


CASES = {
    f.__name__.lstrip("_"): f
    for f in (_offline, _labels_only, _full, _count_bodies, _failing_labels_and_embedder, _failing_verifier_and_counter)
}


@pytest.mark.parametrize("name", CASES)
def test_scan_matches_the_recorded_golden_output(name, tmp_path):
    text = json.dumps(CASES[name](tmp_path), default=list)
    home = str(Path.home())  # warnings show paths home-relative ("~/...")
    actual = json.loads(text.replace(str(FIXTURES), "<fixtures>").replace("~" + str(FIXTURES).removeprefix(home), "<fixtures>"))
    for item in actual["result"]["items"]:
        item["changed_on"] = None  # a file's mtime day depends on the checkout, not on the scan
    path = GOLDEN / f"{name}.json"
    if os.environ.get("GOLDEN_RECORD"):
        path.write_text(json.dumps(actual, indent=2, sort_keys=True) + "\n")
    assert actual == json.loads(path.read_text())
