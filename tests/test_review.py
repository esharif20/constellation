import os
import stat
from pathlib import Path
from typing import Any

from langgraph.types import Command

from constellation.review import build_review_graph, open_checkpointer, thread_id

IDS = ["a1", "b2", "c3"]


def _cfg(path: Path, n: int = len(IDS)) -> Any:
    return {"configurable": {"thread_id": thread_id(path)}, "recursion_limit": n * 2 + 10}


def _pending(result: dict[str, Any]) -> str:
    return str(result["__interrupt__"][0].value)


def test_approve_and_skip_are_recorded(tmp_path):
    graph, cfg = build_review_graph(open_checkpointer(tmp_path / "r.sqlite")), _cfg(tmp_path / "scan.json")
    assert _pending(graph.invoke({"suggestions": IDS}, cfg)) == "a1"
    assert _pending(graph.invoke(Command(resume="approve"), cfg)) == "b2"
    assert _pending(graph.invoke(Command(resume="skip"), cfg)) == "c3"
    done = graph.invoke(Command(resume="approve"), cfg)
    assert "__interrupt__" not in done
    assert done["decisions"] == {"a1": "approve", "b2": "skip", "c3": "approve"}


def test_resume_after_restart_continues_at_the_same_suggestion(tmp_path):
    db, cfg = tmp_path / "r.sqlite", _cfg(tmp_path / "scan.json")
    first = build_review_graph(open_checkpointer(db))
    first.invoke({"suggestions": IDS}, cfg)
    first.invoke(Command(resume="approve"), cfg)
    del first  # "process A" is gone; only the file remains
    second = build_review_graph(open_checkpointer(db))
    assert second.get_state(cfg).next == ("ask",)  # still paused on b2
    assert _pending(second.invoke(Command(resume="skip"), cfg)) == "c3"


def test_fresh_invoke_replaces_the_stale_pause_and_keeps_answers(tmp_path):
    db, cfg = tmp_path / "r.sqlite", _cfg(tmp_path / "scan.json")
    graph = build_review_graph(open_checkpointer(db))
    graph.invoke({"suggestions": IDS}, cfg)
    graph.invoke(Command(resume="approve"), cfg)  # paused on b2; the CLI now quits
    again = build_review_graph(open_checkpointer(db)).invoke({"suggestions": IDS}, cfg)
    assert _pending(again) == "b2"  # a1 is not asked again
    assert again["decisions"] == {"a1": "approve"}


def test_fresh_invoke_after_finishing_asks_nothing(tmp_path):
    graph, cfg = build_review_graph(open_checkpointer(tmp_path / "r.sqlite")), _cfg(tmp_path / "scan.json")
    graph.invoke({"suggestions": IDS}, cfg)
    for answer in ("approve", "skip", "skip"):
        graph.invoke(Command(resume=answer), cfg)
    again = graph.invoke({"suggestions": IDS}, cfg)
    assert "__interrupt__" not in again
    assert len(again["decisions"]) == 3


def test_new_suggestion_after_a_rescan_is_asked_old_ones_are_not(tmp_path):
    graph, cfg = build_review_graph(open_checkpointer(tmp_path / "r.sqlite")), _cfg(tmp_path / "scan.json")
    graph.invoke({"suggestions": ["a1"]}, cfg)
    graph.invoke(Command(resume="approve"), cfg)
    assert _pending(graph.invoke({"suggestions": ["a1", "z9"]}, cfg)) == "z9"


def test_thirty_suggestions_fit_the_recursion_limit(tmp_path):
    ids = [f"s{n:02}" for n in range(30)]
    graph, cfg = build_review_graph(open_checkpointer(tmp_path / "r.sqlite")), _cfg(tmp_path / "scan.json", 30)
    result = graph.invoke({"suggestions": ids}, cfg)
    for _ in ids:
        result = graph.invoke(Command(resume="skip"), cfg)
    assert len(result["decisions"]) == 30


def test_checkpoint_file_is_private_and_holds_only_ids_and_answers(tmp_path):
    db, cfg = tmp_path / "r.sqlite", _cfg(tmp_path / "scan.json")
    db.touch()
    os.chmod(db, 0o644)  # an existing, too-open file is tightened
    graph = build_review_graph(open_checkpointer(db))
    graph.invoke({"suggestions": IDS}, cfg)
    graph.invoke(Command(resume="approve"), cfg)
    assert stat.S_IMODE(db.stat().st_mode) == 0o600


def test_thread_id_is_stable_per_file(tmp_path):
    assert thread_id(tmp_path / "x.json") == thread_id(tmp_path / "." / "x.json")
    assert thread_id(tmp_path / "x.json") != thread_id(tmp_path / "y.json")
