import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from constellation.cli import main
from constellation.review import DEFAULT_CHECKPOINT  # noqa: F401  (conftest redirects it)
from constellation.suggestions import Suggestion

FIXTURE = Path(__file__).parent / "fixtures" / "scan.json"
SECRET = "".join(["ghp_", "aB3dE5gH" * 4, "7jK9"])


@pytest.fixture
def scan(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "constellation.json").write_text(FIXTURE.read_text())
    return tmp_path


def scripted(*answers):
    asked: list[Suggestion] = []
    queue = list(answers)

    def decide(s: Suggestion) -> str:
        asked.append(s)
        return queue.pop(0)

    decide.asked = asked  # type: ignore[attr-defined]
    return decide


def test_approved_appear_in_cleanup_and_skipped_do_not(scan, capsys):
    decide = scripted("a", "s")
    assert main(["review"], decide=decide) == 0
    text = (scan / "cleanup.md").read_text()
    assert "Remove one of these two: deploy (skill) and ship (skill)" in text
    assert "reviewer (agent) only calls" not in text
    assert [s.kind for s in decide.asked] == ["remove_duplicate", "use_underlying"]  # one at a time, in order
    assert "1 approved, 1 skipped, 0 left" in capsys.readouterr().out


def test_quit_then_rerun_starts_at_the_same_suggestion(scan, capsys):
    first = scripted("a", "q")
    assert main(["review"], decide=first) == 0
    assert "1 approved, 0 skipped, 1 left" in capsys.readouterr().out
    second = scripted("s")
    assert main(["review", "--force"], decide=second) == 0
    assert [s.kind for s in second.asked] == ["use_underlying"]  # the approved one is not asked again
    assert "1 approved, 1 skipped, 0 left" in capsys.readouterr().out
    assert "deploy (skill)" in (scan / "cleanup.md").read_text()  # the earlier approval is kept


def test_ctrl_c_and_end_of_input_leave_it_paused(scan):
    def interrupted(s):
        raise KeyboardInterrupt

    assert main(["review"], decide=interrupted) == 0
    again = scripted("s", "s")
    assert main(["review", "--force"], decide=again) == 0
    assert len(again.asked) == 2


def test_anything_else_quits_and_nothing_is_decided(scan):
    assert main(["review"], decide=scripted("x")) == 0
    again = scripted("s", "s")
    main(["review", "--force"], decide=again)
    assert len(again.asked) == 2


def test_missing_file_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["review"], decide=scripted()) == 2
    assert "run `constellation scan` first" in capsys.readouterr().err


def test_refuses_to_overwrite_cleanup_without_force(scan, capsys):
    (scan / "cleanup.md").write_text("mine")
    decide = scripted()
    assert main(["review"], decide=decide) == 2
    assert (scan / "cleanup.md").read_text() == "mine"
    assert decide.asked == []
    assert "--force" in capsys.readouterr().err


def test_custom_out_and_file_arguments(scan):
    (scan / "other.json").write_text(FIXTURE.read_text())
    assert main(["review", "other.json", "--out", "todo.md"], decide=scripted("a", "a")) == 0
    assert "id " in (scan / "todo.md").read_text()
    assert not (scan / "cleanup.md").exists()


def test_no_overlaps_prints_no_suggestions_and_writes_nothing(scan, capsys):
    data = json.loads(FIXTURE.read_text())
    data["overlaps"] = []
    (scan / "constellation.json").write_text(json.dumps(data))
    assert main(["review"], decide=scripted()) == 0
    assert "No Suggestions" in capsys.readouterr().out
    assert not (scan / "cleanup.md").exists()


def test_suggestion_is_shown_with_reason_and_tokens(scan, capsys):
    main(["review"], decide=scripted("q"))
    out = capsys.readouterr().out
    assert "[1/2]" in out and "deploy (skill) and ship (skill)" in out and "415" in out
    data = json.loads(FIXTURE.read_text())
    data["costs"] = {}
    (scan / "constellation.json").write_text(json.dumps(data))
    main(["review", "--force"], decide=scripted("q"))
    assert "unknown" in capsys.readouterr().out


def test_default_prompt_reads_stdin_and_retries_bad_input(scan, monkeypatch, capsys):
    answers = iter(["huh", "A", "s"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    assert main(["review"]) == 0
    assert "1 approved, 1 skipped, 0 left" in capsys.readouterr().out


def test_end_of_stdin_quits(scan, monkeypatch):
    def eof(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)
    assert main(["review"]) == 0


def test_checkpoint_never_holds_descriptions_or_reasons(scan):
    data = json.loads(FIXTURE.read_text())
    data["items"][0]["description"] = f"secret {SECRET}"
    data["overlaps"][1]["reason"] = f"same as {SECRET}"
    data["items"][0]["name"] = "NAME-SENTINEL"
    (scan / "constellation.json").write_text(json.dumps(data))
    main(["review"], decide=scripted("a", "s"))
    db = _checkpoint_path()
    raw = db.read_bytes() + Path(str(db) + "-wal").read_bytes() if Path(str(db) + "-wal").exists() else db.read_bytes()
    assert b"approve" in raw  # we really are looking at the checkpoint
    for forbidden in (SECRET.encode(), b"NAME-SENTINEL", b"identical instructions"):
        assert forbidden not in raw
    assert SECRET not in (scan / "cleanup.md").read_text()
    assert sqlite3.connect(db).execute("select count(*) from checkpoints").fetchone()[0] > 0


def _tree(root: Path) -> dict[str, tuple[bytes, int]]:
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns) for p in sorted(root.rglob("*")) if p.is_file()}


def test_scan_and_review_never_write_to_the_config_directory(scan, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("constellation.cli._local_embedder", lambda: None)
    config = scan / "claude"
    shutil.copytree(Path(__file__).parent / "fixtures" / "claude_config", config)
    before = _tree(config)
    assert main(["scan", str(config), "--out", str(scan / "fresh.json")]) == 0
    assert main(["review", "fresh.json", "--out", "todo.md"], decide=scripted("a", "a", "a", "a")) == 0
    assert _tree(config) == before  # same files, bytes and mtimes: nothing added, changed or deleted


def _checkpoint_path() -> Path:
    from constellation import review

    return review.DEFAULT_CHECKPOINT
