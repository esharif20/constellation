"""Optional human review uses real interrupts and invented setup data only."""

import json
import re
import sqlite3
import stat

import pytest
from fakes import FakeEmbedder, FakeLLM, FakeVerifier, verdict, write_skill

from constellation import cli, scan, scan_graph


@pytest.fixture
def config(tmp_path):
    root = tmp_path / "invented-setup"
    write_skill(root, "cedar", "First invented body", description="alpha topic")
    write_skill(root, "maple", "Second invented body", description="omega words")
    return root


def run_scan(config, tmp_path, **kwargs):
    ask = kwargs.pop("ask_pairs", None)
    seen = set()

    def ask_once(a, b):
        assert (a, b) not in seen, "A scan repeated a prompt instead of advancing"
        seen.add((a, b))
        return ask(a, b)

    return scan(
        config,
        embedder=FakeEmbedder({}, default=[1.0, 0.0]),
        verdict_cache=tmp_path / "verdicts.json",
        usage=False,
        origins=False,
        ask_pairs=ask_once if ask is not None else None,
        **kwargs,
    )


def test_review_without_checkpoint_does_not_pause(config, tmp_path):
    verifier = FakeVerifier(default=verdict("overlap", "Verifier fallback"))

    def ask(a, b):
        pytest.fail("A scan without a checkpointer must never pause")

    progress = []
    result = run_scan(config, tmp_path, verifier=verifier, ask_pairs=ask, on_progress=progress.append)
    assert "verified 1/1" in progress

    assert len(verifier.prompts) == 1
    assert result.overlaps[0].verdict == "overlap"


def test_default_checkpoint_thread_id_matches_the_pre_t5_scan(config, tmp_path):
    from constellation.checkpoint import close_checkpointer, open_checkpointer

    class Killed(BaseException):
        pass

    def verifier(prompt):
        raise Killed

    db = tmp_path / "scan.sqlite"
    with pytest.raises(Killed):
        run_scan(config, tmp_path, verifier=verifier, checkpoint=db)
    saver = open_checkpointer(db, scan_graph.STATE_TYPES)
    try:
        threads = {checkpoint.config["configurable"]["thread_id"] for checkpoint in saver.list(None)}
    finally:
        close_checkpointer(saver)
    # Recorded with thread_id() from origin/main 7019bc6 on this invented pair, not calculated by the implementation under test.
    assert threads == {"scan:8a289085c179843cb8b369c8399c67dd23d7b0d32bdbb410c3e1b5f916bbd44b"}


def test_same_job_is_reviewed_before_the_verifier_and_cached(config, tmp_path):
    verifier = FakeVerifier(default=verdict("overlap", "Verifier fallback"))
    asked = []

    def ask(a, b):
        assert verifier.prompts == []
        asked.append((a, b))
        return "same"

    options = {"verifier": verifier, "ask_pairs": ask, "checkpoint": tmp_path / "scan.sqlite"}
    result = run_scan(config, tmp_path, **options)

    assert asked == [("claude-code:skill:cedar", "claude-code:skill:maple")]
    assert verifier.prompts == []
    assert result.overlaps[0].verdict == "duplicate"
    assert result.overlaps[0].reason == "Human review: same job."
    assert run_scan(config, tmp_path, **options).overlaps == result.overlaps
    assert len(asked) == 1


def test_a_crash_mid_pause_resumes_the_same_pair_without_reusing_another_answer(config, tmp_path):
    write_skill(config, "birch", "Third invented body", description="delta topic")
    verifier = FakeVerifier()
    before = []

    def stop(a, b):
        before.append((a, b))
        if len(before) == 1:
            return "same"
        raise EOFError

    options = {"verifier": verifier, "checkpoint": tmp_path / "scan.sqlite"}
    with pytest.raises(EOFError):
        run_scan(config, tmp_path, ask_pairs=stop, **options)

    after, progress = [], []
    result = run_scan(
        config,
        tmp_path,
        ask_pairs=lambda a, b: after.append((a, b)) or "different",
        on_progress=progress.append,
        **options,
    )

    assert after[0] == before[1]
    assert before[0] not in after
    assert len(after) == 2 and len(set(after)) == 2
    assert len(result.overlaps) == 3
    assert {tuple((o.a_id, o.b_id)) for o in result.overlaps if o.verdict == "duplicate"} == {before[0]}
    assert sum(o.verdict == "distinct" for o in result.overlaps) == 2
    assert verifier.prompts == []
    assert [line for line in progress if line.startswith("verified")] == ["verified 2/3", "verified 3/3"]


def test_skip_falls_back_to_the_verifier_and_survives_a_failed_verdict(config, tmp_path):
    asked = []
    first = FakeVerifier(fail_for={"cedar": "Invented failure"})
    options = {"checkpoint": tmp_path / "scan.sqlite"}
    result = run_scan(config, tmp_path, verifier=first, ask_pairs=lambda a, b: asked.append((a, b)) or "skip", **options)
    assert len(first.prompts) == 1 and result.overlaps == []

    second = FakeVerifier(default=verdict("overlap", "Verifier fallback"))
    result = run_scan(config, tmp_path, verifier=second, ask_pairs=lambda a, b: asked.append((a, b)) or "same", **options)
    assert len(asked) == 1
    assert len(second.prompts) == 1 and result.overlaps[0].verdict == "overlap"


def test_failure_to_cache_an_accepted_answer_does_not_call_the_verifier(config, tmp_path):
    db = tmp_path / "scan.sqlite"
    verifier = FakeVerifier(default=verdict("overlap", "Verifier fallback"))

    def ask(a, b):
        with sqlite3.connect(db) as connection:
            connection.execute(
                "CREATE TRIGGER no_review_write BEFORE INSERT ON pair_reviews BEGIN SELECT RAISE(FAIL, 'invented cache write failure'); END"
            )
        return "same"

    result = run_scan(config, tmp_path, verifier=verifier, ask_pairs=ask, checkpoint=db)
    assert result.overlaps[0].verdict == "duplicate" and verifier.prompts == []
    assert "Could not cache pair review; this scan keeps the answer, but a later scan may ask again." in result.warnings


@pytest.mark.parametrize("method", ["put", "put_writes"])
def test_checkpoint_failure_during_the_resume_step_keeps_the_accepted_answer(config, tmp_path, monkeypatch, method):
    from langgraph.checkpoint.sqlite import SqliteSaver

    original = getattr(SqliteSaver, method)
    accepted = False

    def put(self, *args, **kwargs):
        if accepted:
            raise sqlite3.OperationalError("invented full disk")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(SqliteSaver, method, put)

    def ask(a, b):
        nonlocal accepted
        accepted = True
        return "same"

    verifier = FakeVerifier(default=verdict("overlap", "Verifier fallback"))
    result = run_scan(config, tmp_path, verifier=verifier, ask_pairs=ask, checkpoint=tmp_path / "scan.sqlite")
    assert result.overlaps[0].verdict == "duplicate" and verifier.prompts == []
    assert result.warnings.count(scan_graph.CHECKPOINT_WARNING) == 1


def test_checkpoint_failure_does_not_invent_answers_for_other_pairs(config, tmp_path, monkeypatch):
    from langgraph.checkpoint.sqlite import SqliteSaver

    write_skill(config, "birch", "Third invented body", description="delta topic")
    original = SqliteSaver.put_writes
    accepted = []

    def put(self, *args, **kwargs):
        if accepted:
            raise sqlite3.OperationalError("invented full disk")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(SqliteSaver, "put_writes", put)
    verifier = FakeVerifier(default=verdict("overlap", "Verifier fallback"))
    result = run_scan(
        config,
        tmp_path,
        verifier=verifier,
        ask_pairs=lambda a, b: accepted.append((a, b)) or "same",
        checkpoint=tmp_path / "scan.sqlite",
    )
    assert len(accepted) == 1 and len(verifier.prompts) == 2
    assert {(o.a_id, o.b_id) for o in result.overlaps if o.verdict == "duplicate"} == {accepted[0]}
    assert sum(o.verdict == "overlap" for o in result.overlaps) == 2


def test_resume_uses_an_answer_committed_before_the_task_checkpoint_failed(config, tmp_path, monkeypatch):
    from langgraph.checkpoint.sqlite import SqliteSaver

    original = SqliteSaver.put_writes

    def put(self, config, writes, *args, **kwargs):
        if any(channel == "verdicts" and value for channel, value in writes):
            raise sqlite3.OperationalError("invented failed task checkpoint")
        return original(self, config, writes, *args, **kwargs)

    monkeypatch.setattr(SqliteSaver, "put_writes", put)
    verifier = FakeVerifier()
    options = {"verifier": verifier, "checkpoint": tmp_path / "scan.sqlite"}
    first = run_scan(config, tmp_path, ask_pairs=lambda a, b: "same", **options)
    assert first.warnings.count(scan_graph.CHECKPOINT_WARNING) == 1
    monkeypatch.setattr(SqliteSaver, "put_writes", original)
    (tmp_path / "verdicts.json").unlink()

    def ask(a, b):
        pytest.fail("A committed human answer must not be asked again")

    result = run_scan(config, tmp_path, ask_pairs=ask, **options)
    assert result.overlaps[0].verdict == "duplicate" and verifier.prompts == []


def test_answers_are_content_cached_independently_of_the_verifier_model(config, tmp_path):
    asked = []
    options = {"checkpoint": tmp_path / "scan.sqlite", "verifier": FakeVerifier()}

    def ask(a, b):
        return asked.append((a, b)) or "same"

    first = run_scan(config, tmp_path, ask_pairs=ask, verifier_model="invented-first", **options)
    (tmp_path / "verdicts.json").unlink()
    second = run_scan(config, tmp_path, ask_pairs=ask, verifier_model="invented-second", **options)
    assert first.overlaps == second.overlaps and len(asked) == 1
    write_skill(config, "maple", "Second invented body", description="New invented topic")
    run_scan(config, tmp_path, ask_pairs=ask, verifier_model="invented-second", **options)
    assert len(asked) == 2 and options["verifier"].prompts == []


def test_cli_review_flag_asks_for_a_decision_before_verification(config, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_env", lambda: None)
    answers = iter(["not-a-choice", " DiFfErEnT "])
    monkeypatch.setattr("builtins.input", lambda: next(answers))
    verifier = FakeVerifier()
    out = tmp_path / "scan.json"
    code = cli.main(
        ["scan", str(config), "--review-ambiguous", "--no-usage", "--no-origins", "--no-history", "--out", str(out)],
        llm=FakeLLM({}, default="topic"),
        embedder=FakeEmbedder({}, default=[1.0, 0.0]),
        verifier=verifier,
    )
    assert code == 0 and verifier.prompts == []
    assert json.loads(out.read_text())["overlaps"][0]["verdict"] == "distinct"
    assert json.loads(out.read_text())["overlaps"][0]["reason"] == "Human review: different jobs."
    printed = capsys.readouterr()
    assert "cedar: alpha topic" in printed.err and "maple: omega words" in printed.err
    assert "not-a-choice" not in printed.err
    assert "invented body" not in printed.out + printed.err


@pytest.mark.parametrize("stop", [EOFError, KeyboardInterrupt])
def test_cli_leaves_a_pause_resumable_without_writing_a_partial_scan(config, tmp_path, monkeypatch, capsys, stop):
    monkeypatch.setattr(cli, "load_env", lambda: None)

    def closed_input():
        raise stop

    monkeypatch.setattr("builtins.input", closed_input)
    out = tmp_path / "scan.json"
    argv = ["scan", str(config), "--review-ambiguous", "--no-usage", "--no-origins", "--no-history", "--out", str(out)]
    providers = {"llm": FakeLLM({}, default="topic"), "embedder": FakeEmbedder({}, default=[1.0, 0.0]), "verifier": FakeVerifier()}
    assert cli.main(argv, **providers) == 130
    assert not out.exists()
    assert "paused" in capsys.readouterr().err.lower()
    monkeypatch.setattr("builtins.input", iter(["same"]).__next__)
    assert cli.main(argv, **providers) == 0
    assert json.loads(out.read_text())["overlaps"][0]["verdict"] == "duplicate"
    assert len(providers["llm"].prompts) == 2 and providers["verifier"].prompts == []


def test_default_cli_interrupt_behavior_is_unchanged(config, monkeypatch):
    monkeypatch.setattr(cli, "load_env", lambda: None)

    def interrupted(texts):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        cli.main(["scan", str(config), "--no-origins"], llm=FakeLLM({}), embedder=interrupted)


def test_pause_and_answer_cache_never_store_item_text_or_callback_errors(tmp_path):
    secret = "quietvioletbadger"
    root = tmp_path / f"invented-folder-{secret}"
    write_skill(root, f"cedar-{secret}", f"PRIVATE-BODY-LEFT {secret}", description=f"violet-description-marker {secret}")
    write_skill(root, f"maple-{secret}", f"PRIVATE-BODY-RIGHT {secret}", description=f"amber-description-marker {secret}")
    (root / "settings.json").write_text(json.dumps({"env": {"TOKEN": secret}}))
    db = tmp_path / "private" / "scan.sqlite"
    displayed, asked = [], []

    def stopped(a, b):
        asked.append((a, b))
        raise RuntimeError(secret)

    options = {"checkpoint": db, "verifier": FakeVerifier(), "on_progress": displayed.append}
    with pytest.raises(RuntimeError, match=secret):
        run_scan(root, tmp_path, ask_pairs=stopped, **options)
    assert len(asked) == 1 and all(type(id_) is str for id_ in asked[0])
    assert "violet-description-marker [REDACTED]" in "\n".join(displayed)
    assert secret not in "\n".join(displayed) and "PRIVATE-BODY" not in "\n".join(displayed)
    for path in db.parent.glob("scan.sqlite*"):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        contents = path.read_bytes()
        for text in (secret, "PRIVATE-BODY", "violet-description-marker", "amber-description-marker"):
            assert text.encode() not in contents
    assert stat.S_IMODE(db.parent.stat().st_mode) == 0o700
    result = run_scan(root, tmp_path, ask_pairs=lambda a, b: "same", **options)
    assert result.overlaps[0].verdict == "duplicate" and options["verifier"].prompts == []
    with sqlite3.connect(db) as connection:
        rows = connection.execute("SELECT content_hash, answer FROM pair_reviews").fetchall()
    assert len(rows) == 1 and re.fullmatch("[0-9a-f]{64}", rows[0][0]) and rows[0][1] == 1
    assert secret.encode() not in db.read_bytes()


@pytest.mark.parametrize("answer", [None, True, 1, [], "invented-private-invalid-answer"])
def test_invalid_callback_results_never_become_resume_payloads(config, tmp_path, answer):
    options = {"checkpoint": tmp_path / "scan.sqlite", "verifier": FakeVerifier()}
    with pytest.raises(ValueError, match="^Pair review must return same, different or skip$"):
        run_scan(config, tmp_path, ask_pairs=lambda a, b: answer, **options)
    assert b"invented-private-invalid-answer" not in options["checkpoint"].read_bytes()
    assert options["verifier"].prompts == []
    result = run_scan(config, tmp_path, ask_pairs=lambda a, b: "different", **options)
    assert result.overlaps[0].verdict == "distinct"


@pytest.mark.parametrize("corrupt", [17, True, 1.0, "invented-corrupt-answer"])
def test_corrupt_saved_resume_values_are_not_cached_as_human_answers(config, tmp_path, corrupt):
    from constellation.checkpoint import close_checkpointer, open_checkpointer

    db = tmp_path / "scan.sqlite"
    verifier = FakeVerifier()

    def paused(a, b):
        raise EOFError

    with pytest.raises(EOFError):
        run_scan(config, tmp_path, verifier=verifier, ask_pairs=paused, checkpoint=db)
    saver = open_checkpointer(db, scan_graph.STATE_TYPES)
    try:
        saved = next(saver.list(None))
        task = next(task for task, channel, value in saved.pending_writes if channel == "__interrupt__")
        saver.put_writes(saved.config, [("__resume__", [corrupt])], task)
    finally:
        close_checkpointer(saver)
    result = run_scan(config, tmp_path, verifier=verifier, ask_pairs=lambda a, b: "same", checkpoint=db)
    assert result.overlaps[0].verdict == "duplicate" and verifier.prompts == []
    assert result.warnings.count(scan_graph.CHECKPOINT_WARNING) == 1
    with sqlite3.connect(db) as connection:
        assert connection.execute("SELECT count(*) FROM pair_reviews").fetchone()[0] == 0


def test_review_pause_uses_a_separate_checkpoint_thread(config, tmp_path):
    from constellation.checkpoint import close_checkpointer, open_checkpointer

    def paused(a, b):
        raise EOFError

    db = tmp_path / "scan.sqlite"
    with pytest.raises(EOFError):
        run_scan(config, tmp_path, verifier=FakeVerifier(), ask_pairs=paused, checkpoint=db)
    saver = open_checkpointer(db, scan_graph.STATE_TYPES)
    try:
        threads = {checkpoint.config["configurable"]["thread_id"] for checkpoint in saver.list(None)}
    finally:
        close_checkpointer(saver)
    assert len(threads) == 1
    assert threads != {"scan:8a289085c179843cb8b369c8399c67dd23d7b0d32bdbb410c3e1b5f916bbd44b"}


@pytest.mark.parametrize("threshold, expected", [(0.5, 1), (0.500001, 0)])
def test_pause_uses_the_existing_inclusive_band_boundary(config, tmp_path, monkeypatch, threshold, expected):
    monkeypatch.setattr(scan_graph, "BAND_LOW", threshold)
    asked = []
    verifier = FakeVerifier()
    result = run_scan(
        config,
        tmp_path,
        verifier=verifier,
        ask_pairs=lambda a, b: asked.append((a, b)) or "same",
        checkpoint=tmp_path / "scan.sqlite",
    )
    assert len(asked) == expected and len(result.overlaps) == expected
    assert verifier.prompts == []


def test_an_unavailable_checkpointer_uses_the_existing_noninteractive_fallback(config, tmp_path):
    db = tmp_path / "directory-not-a-database"
    db.mkdir()
    verifier = FakeVerifier(default=verdict("overlap", "Verifier fallback"))

    def ask(a, b):
        pytest.fail("A failed checkpointer cannot pause")

    result = run_scan(config, tmp_path, verifier=verifier, ask_pairs=ask, checkpoint=db)
    assert len(verifier.prompts) == 1 and result.overlaps[0].verdict == "overlap"
    assert result.warnings.count(scan_graph.CHECKPOINT_WARNING) == 1


def test_no_verifier_means_no_human_review_job(config, tmp_path):
    def ask(a, b):
        pytest.fail("No verifier job exists to review")

    assert run_scan(config, tmp_path, ask_pairs=ask, checkpoint=tmp_path / "scan.sqlite").overlaps == []


def test_dry_run_ignores_review_flag_and_writes_no_checkpoint(config, tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "load_env", lambda: None)
    db, out = tmp_path / "scan.sqlite", tmp_path / "scan.json"
    monkeypatch.setattr(scan_graph, "DEFAULT_CHECKPOINT", db)

    def ask():
        pytest.fail("A dry run cannot pause")

    monkeypatch.setattr("builtins.input", ask)
    assert (
        cli.main(
            ["scan", str(config), "--review-ambiguous", "--dry-run", "--no-usage", "--no-origins", "--out", str(out)],
            embedder=FakeEmbedder({}, default=[1.0, 0.0]),
        )
        == 0
    )
    assert not db.exists() and not out.exists()


def test_cached_human_answers_skip_new_interrupt_writes(config, tmp_path, monkeypatch):
    from langgraph.checkpoint.sqlite import SqliteSaver

    options = {"verifier": FakeVerifier(), "checkpoint": tmp_path / "scan.sqlite"}
    run_scan(config, tmp_path, ask_pairs=lambda a, b: "same", **options)
    (tmp_path / "verdicts.json").unlink()
    original = SqliteSaver.put_writes
    interrupts = []

    def put(self, config, writes, *args, **kwargs):
        interrupts.extend(value for channel, value in writes if channel == "__interrupt__")
        return original(self, config, writes, *args, **kwargs)

    monkeypatch.setattr(SqliteSaver, "put_writes", put)

    def ask(a, b):
        pytest.fail("A cached pair must not pause")

    result = run_scan(config, tmp_path, ask_pairs=ask, **options)
    assert result.overlaps[0].verdict == "duplicate"
    assert interrupts == [] and options["verifier"].prompts == []


def test_cached_human_answer_survives_a_later_checkpoint_write_failure(config, tmp_path, monkeypatch):
    from langgraph.checkpoint.sqlite import SqliteSaver

    options = {"verifier": FakeVerifier(), "checkpoint": tmp_path / "scan.sqlite"}
    run_scan(config, tmp_path, ask_pairs=lambda a, b: "same", **options)
    (tmp_path / "verdicts.json").unlink()
    (tmp_path / "verdicts.json").mkdir()  # the model cache cannot mask loss of the human answer
    original = SqliteSaver.put_writes

    def put(self, config, writes, *args, **kwargs):
        if any(channel == "verdicts" and value for channel, value in writes):
            raise sqlite3.OperationalError("invented full disk")
        return original(self, config, writes, *args, **kwargs)

    monkeypatch.setattr(SqliteSaver, "put_writes", put)
    result = run_scan(config, tmp_path, ask_pairs=lambda a, b: pytest.fail("Already answered"), **options)
    assert result.overlaps[0].verdict == "duplicate" and options["verifier"].prompts == []
    assert result.warnings.count(scan_graph.CHECKPOINT_WARNING) == 1


def test_answer_added_to_a_paused_scan_is_reused_without_asking(config, tmp_path):
    paused_db, answered_db = tmp_path / "paused.sqlite", tmp_path / "answered.sqlite"

    def stopped(a, b):
        raise EOFError

    with pytest.raises(EOFError):
        run_scan(config, tmp_path, verifier=FakeVerifier(), ask_pairs=stopped, checkpoint=paused_db)
    run_scan(config, tmp_path, verifier=FakeVerifier(), ask_pairs=lambda a, b: "different", checkpoint=answered_db)
    (tmp_path / "verdicts.json").unlink()
    with sqlite3.connect(answered_db) as connection:
        answer = connection.execute("SELECT content_hash, answer FROM pair_reviews").fetchone()
    with sqlite3.connect(paused_db) as connection:
        connection.execute("INSERT INTO pair_reviews VALUES (?, ?)", answer)
    verifier = FakeVerifier()
    result = run_scan(config, tmp_path, verifier=verifier, ask_pairs=lambda a, b: pytest.fail("Already answered"), checkpoint=paused_db)
    assert result.overlaps[0].verdict == "distinct" and verifier.prompts == []


def test_resume_progress_does_not_count_the_completed_cluster_as_a_pair(config, tmp_path):
    def stopped(a, b):
        raise EOFError

    options = {"verifier": FakeVerifier(), "checkpoint": tmp_path / "scan.sqlite"}
    with pytest.raises(EOFError):
        run_scan(config, tmp_path, ask_pairs=stopped, **options)
    progress = []
    result = run_scan(config, tmp_path, ask_pairs=lambda a, b: "same", on_progress=progress.append, **options)
    assert result.overlaps[0].verdict == "duplicate"
    assert [line for line in progress if line.startswith("verified")] == ["verified 1/1"]
