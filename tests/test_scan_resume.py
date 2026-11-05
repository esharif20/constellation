"""Checkpointed scans (#22 T3): resume without re-paying, privacy of the checkpoint file, corrupt files, progress lines."""

import json
import re
import shutil
import sqlite3
import stat
from dataclasses import replace
from pathlib import Path

import pytest
from fakes import FakeCounter, FakeEmbedder, FakeLLM, FakeVerifier, verdict

from constellation import cli, scan, scan_graph
from constellation.checkpoint import close_checkpointer, open_checkpointer
from constellation.claude_code import read_items
from constellation.models import Item
from constellation.redact import REDACTED

OVERLAP = Path(__file__).parent / "fixtures" / "overlap_config"
SECRET = "quietorangewalrus"  # letters only: matches no built-in pattern, so only the known-secret list can catch it
BODY_MARKER = "zebra-body-marker-text"
DESC_MARKER = "violet-description-marker"
PDF, PROSE = frozenset({"pdf-reader", "pdf-viewer"}), frozenset({"stop-slop", "tidy-prose"})
VECTORS = {"PDF": [1.0, 0.0, 0.0], "prose": [0.0, 1.0, 0.0], "writing": [0.0, 1.0, 0.0]}


class Crash(BaseException):
    """Not an Exception, so the guarded provider does not turn it into a warning: it stands for a killed process."""


class Crashing:
    """Wraps a fake provider: counts calls and raises Crash on call number `at` (1-based)."""

    def __init__(self, inner, at=None):
        self.inner, self.at, self.calls = inner, at, 0

    def __call__(self, prompt):
        self.calls += 1
        if self.calls == self.at:
            raise Crash
        return self.inner(prompt)


@pytest.fixture(autouse=True)
def one_at_a_time(monkeypatch):
    monkeypatch.setattr(scan_graph, "MAX_CONCURRENCY", 1)  # branches finish in order, so "crash on call k" is exact


@pytest.fixture
def config(tmp_path):
    root = tmp_path / "config"
    shutil.copytree(OVERLAP, root)
    return root


def _run(config, tmp_path, **kwargs):
    return scan(
        config,
        cost_cache=tmp_path / "costs.json",
        verdict_cache=tmp_path / "verdicts.json",
        label_cache=tmp_path / "labels.json",
        usage=False,
        origins=False,
        **kwargs,
    )


def _verifier(**kwargs):
    return FakeVerifier({PDF: verdict("overlap", "both read PDFs"), PROSE: verdict("duplicate", "same job")}, **kwargs)


def _threads(path):
    saver = open_checkpointer(path)
    try:
        return {c.config["configurable"]["thread_id"] for c in saver.list(None)}
    finally:
        saver.conn.close()


def test_a_scan_killed_while_labelling_resumes_and_pays_only_for_the_unfinished_labels(config, tmp_path):
    db = tmp_path / "cp" / "scan.sqlite"
    first = Crashing(FakeLLM({}, default="topic"), at=3)
    with pytest.raises(Crash):
        _run(config, tmp_path, llm=first, checkpoint=db)
    assert first.calls == 6  # LangGraph lets the other branches of the step finish, and saves them
    assert len(_threads(db)) == 1  # the unfinished scan is saved

    second = Crashing(FakeLLM({}, default="topic"))
    result = _run(config, tmp_path, llm=second, checkpoint=db)

    assert len(result.items) == 6 and len(result.labels) == 6
    assert second.calls == 1  # only the killed call is repeated; the five finished labels came from the checkpoint
    assert _threads(db) == set()  # finished: nothing left


def test_a_scan_killed_while_verifying_resumes_and_does_not_ask_the_finished_pair_again(config, tmp_path):
    db = tmp_path / "cp" / "scan.sqlite"
    first = Crashing(_verifier(), at=2)
    with pytest.raises(Crash):
        _run(config, tmp_path, embedder=FakeEmbedder(VECTORS), verifier=first, checkpoint=db)
    second = Crashing(_verifier())
    result = _run(config, tmp_path, embedder=FakeEmbedder(VECTORS), verifier=second, checkpoint=db)

    assert (first.calls, second.calls) == (2, 1)
    assert "both read PDFs" in [o.reason for o in result.overlaps]
    assert _threads(db) == set()


def test_an_unchanged_scan_makes_no_paid_call_at_all(config, tmp_path):
    db = tmp_path / "cp" / "scan.sqlite"

    def go():
        llm, verifier, counter = FakeLLM({}, default="topic"), _verifier(), FakeCounter()
        _run(config, tmp_path, llm=llm, verifier=verifier, counter=counter, embedder=FakeEmbedder(VECTORS), checkpoint=db)
        return len(llm.prompts), len(verifier.prompts), len(counter.texts)

    paid_first = go()
    assert all(paid_first)
    assert go() == (0, 0, 0)


def test_the_checkpoint_never_holds_a_secret_a_body_a_description_or_an_item(config, tmp_path):
    (config / ".env").write_text(f"FOO={SECRET}\n")
    skill = config / "skills" / "pdf-reader" / "SKILL.md"
    skill.write_text(
        f"---\nname: pdf-reader\ndescription: Reads PDF files {DESC_MARKER} {SECRET}.\n---\n{BODY_MARKER} {SECRET} Steps. Open the file.\n"
    )
    db = tmp_path / "cp" / "scan.sqlite"

    class Echo:  # a provider that repeats the secret in its reply and in an extra field
        def __init__(self):
            self.calls = 0

        def label(self, prompt):
            return f"label {SECRET}"

        def verify(self, prompt):
            self.calls += 1
            if self.calls == 2:
                raise Crash
            return verdict("overlap", f"echoes {SECRET}", extra=SECRET)

    echo = Echo()
    with pytest.raises(Crash):
        _run(config, tmp_path, llm=echo.label, verifier=echo.verify, embedder=FakeEmbedder(VECTORS), checkpoint=db)

    saved = b"".join(p.read_bytes() for p in db.parent.iterdir())
    assert b"skill:pdf-reader" in saved and REDACTED.encode() in saved  # the test is not vacuous
    for planted in (SECRET, BODY_MARKER, DESC_MARKER):
        assert planted.encode() not in saved
    for path in db.parent.iterdir():
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(db.parent.stat().st_mode) == 0o700

    saver = open_checkpointer(db)
    values = [c.checkpoint["channel_values"] for c in saver.list(None)]
    saver.conn.close()
    assert values and not any(_holds_item(v) for v in values)


def _holds_item(node):
    if isinstance(node, Item):
        return True
    if isinstance(node, dict):
        return any(_holds_item(k) or _holds_item(v) for k, v in node.items())
    if isinstance(node, (list, tuple, set)):
        return any(_holds_item(v) for v in node)
    return False


def test_a_model_reply_that_echoes_a_secret_is_redacted_in_the_result_and_in_both_caches(config, tmp_path):
    (config / ".env").write_text(f"FOO={SECRET}\n")
    result = _run(
        config,
        tmp_path,
        llm=lambda p: f"topic {SECRET}",
        verifier=lambda p: verdict("overlap", f"echoes {SECRET}"),
        embedder=FakeEmbedder(VECTORS),
        checkpoint=tmp_path / "scan.sqlite",
    )
    assert SECRET not in repr(result)
    assert SECRET not in (tmp_path / "labels.json").read_text() + (tmp_path / "verdicts.json").read_text()
    assert REDACTED in "".join(result.labels.values()) and any(REDACTED in o.reason for o in result.overlaps)


def test_a_verifier_reply_that_cannot_be_read_after_redaction_is_not_cached_but_the_verdict_stays(config, tmp_path):
    (config / ".env").write_text(f"FOO={SECRET}\n")
    reply = verdict("overlap", "same", x=SECRET, api_key=SECRET)
    result = _run(config, tmp_path, verifier=lambda p: reply, embedder=FakeEmbedder(VECTORS), checkpoint=tmp_path / "scan.sqlite")
    assert any(o.verdict == "overlap" for o in result.overlaps)
    cache = tmp_path / "verdicts.json"
    assert not cache.exists() or SECRET not in cache.read_text()


def test_the_default_checkpoint_is_scan_sqlite_in_the_constellation_cache():
    assert scan_graph.DEFAULT_CHECKPOINT.name == "scan.sqlite"


def test_without_a_checkpoint_path_nothing_is_written_next_to_the_caches(config, tmp_path):
    before = set(tmp_path.rglob("*"))
    _run(config, tmp_path, llm=FakeLLM({}, default="topic"))
    assert {p.name for p in set(tmp_path.rglob("*")) - before} == {"labels.json"}  # the label cache only


@pytest.mark.parametrize("junk", ["garbage", "sqlite"])
def test_a_corrupt_or_foreign_checkpoint_is_ignored_with_a_fixed_warning(config, tmp_path, junk):
    db = tmp_path / "cp" / "scan.sqlite"
    db.parent.mkdir()
    if junk == "garbage":
        db.write_bytes(b"not a database at all" * 50)
    else:
        connection = sqlite3.connect(db)
        connection.execute("CREATE TABLE checkpoints (c TEXT)")
        connection.commit()
        connection.close()
    before = db.read_bytes()

    llm, lines = FakeLLM({}, default="topic"), []
    result = _run(config, tmp_path, llm=llm, checkpoint=db, on_progress=lines.append)

    assert result.warnings.count(scan_graph.CHECKPOINT_WARNING) == 1
    assert len(result.labels) == 6 and len(llm.prompts) == 6
    assert lines[-1] == "labelled 6/6"  # progress still reported
    if junk == "garbage":
        assert db.read_bytes() == before  # a file that is not ours is left alone (SQLite itself may touch a foreign database's header)


def test_an_unusable_checkpoint_location_is_ignored_too(config, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    lines: list[str] = []
    result = _run(config, tmp_path, llm=FakeLLM({}, default="topic"), checkpoint=blocker / "scan.sqlite", on_progress=lines.append)
    assert result.warnings.count(scan_graph.CHECKPOINT_WARNING) == 1 and len(result.labels) == 6
    assert lines[-1] == "labelled 6/6"


def test_an_ignored_checkpoint_also_works_with_no_provider_at_all(config, tmp_path):
    db = tmp_path / "scan.sqlite"
    db.write_bytes(b"junk" * 100)
    result = _run(config, tmp_path, checkpoint=db)
    assert result.warnings.count(scan_graph.CHECKPOINT_WARNING) == 1 and len(result.items) == 6


def test_a_saved_step_that_no_longer_fits_the_graph_is_dropped_and_the_scan_starts_over(config, tmp_path, monkeypatch):
    db = tmp_path / "cp" / "scan.sqlite"
    with pytest.raises(Crash):
        _run(config, tmp_path, llm=Crashing(FakeLLM({}, default="topic"), at=3), checkpoint=db)
    real, seen = scan_graph.label_flush, []

    def broken_once(path, fresh):
        seen.append(1)
        if len(seen) == 1:
            raise RuntimeError("stale")
        return real(path, fresh)

    monkeypatch.setattr(scan_graph, "label_flush", broken_once)
    lines: list[str] = []
    llm = FakeLLM({}, default="topic")
    result = _run(config, tmp_path, llm=llm, checkpoint=db, on_progress=lines.append)

    assert result.warnings.count(scan_graph.CHECKPOINT_WARNING) == 1
    assert len(result.labels) == 6 and _threads(db) == set()
    assert lines[-1] == "labelled 6/6"  # the failed resume labelled the killed Item; the restart then found all six in the cache
    assert len(llm.prompts) == 1  # the five finished labels were salvaged into the cache before the thread was dropped


def test_a_restart_after_a_failed_resume_still_reports_progress(config, tmp_path, monkeypatch):
    db = tmp_path / "cp" / "scan.sqlite"
    with pytest.raises(Crash):
        _run(config, tmp_path, llm=Crashing(FakeLLM({}, default="topic"), at=3), checkpoint=db)
    real, seen = scan_graph.label_flush, []

    def broken_once(path, fresh):
        seen.append(1)
        if len(seen) == 1:
            raise RuntimeError("stale")
        return real(path, fresh)

    monkeypatch.setattr(scan_graph, "label_flush", broken_once)
    monkeypatch.setattr(scan_graph, "_salvage", lambda saver, tid, context: None)  # so the restart has all six labels to pay for
    lines: list[str] = []
    _run(config, tmp_path, llm=FakeLLM({}, default="topic"), checkpoint=db, on_progress=lines.append)
    assert lines.count("labelled 1/6") == 2


def test_a_failure_in_a_fresh_checkpointed_scan_is_raised_and_its_thread_deleted(config, tmp_path, monkeypatch):
    def label_flush(path, fresh):
        raise RuntimeError("bug")

    monkeypatch.setattr(scan_graph, "label_flush", label_flush)
    db = tmp_path / "scan.sqlite"
    with pytest.raises(RuntimeError, match="bug"):
        _run(config, tmp_path, llm=FakeLLM({}, default="topic"), checkpoint=db)
    assert _threads(db) == set()


def test_a_different_scan_replaces_the_unfinished_one_so_the_file_holds_only_one(config, tmp_path):
    db = tmp_path / "cp" / "scan.sqlite"
    with pytest.raises(Crash):
        _run(config, tmp_path, llm=Crashing(FakeLLM({}, default="topic"), at=2), checkpoint=db)
    first = _threads(db)
    (config / "skills" / "bake-bread" / "SKILL.md").write_text("---\nname: bake-bread\ndescription: Changed description.\n---\nx\n")
    with pytest.raises(Crash):
        _run(config, tmp_path, llm=Crashing(FakeLLM({}, default="topic"), at=2), checkpoint=db)
    second = _threads(db)

    assert len(first) == len(second) == 1 and first != second


def test_progress_lines_count_labels_and_verdicts(config, tmp_path):
    lines: list[str] = []
    _run(config, tmp_path, llm=FakeLLM({}, default="topic"), verifier=_verifier(), embedder=FakeEmbedder(VECTORS), on_progress=lines.append)
    assert [line for line in lines if line.startswith("labelled")] == [f"labelled {n}/6" for n in range(1, 7)]
    assert [line for line in lines if line.startswith("verified")] == ["verified 1/2", "verified 2/2"]


def test_a_resumed_scan_says_so_and_continues_the_count(config, tmp_path):
    db = tmp_path / "cp" / "scan.sqlite"
    with pytest.raises(Crash):
        _run(config, tmp_path, llm=Crashing(FakeLLM({}, default="topic"), at=3), checkpoint=db)
    lines: list[str] = []
    second = FakeLLM({}, default="topic")
    result = _run(config, tmp_path, llm=second, checkpoint=db, on_progress=lines.append)
    assert len(second.prompts) == 1 and scan_graph.CHECKPOINT_WARNING not in result.warnings  # a real resume, not a silent restart
    assert lines == ["resuming an interrupted scan", *(f"labelled {n}/6" for n in range(1, 7))]


def test_no_progress_is_printed_when_nothing_asks_for_it(config, tmp_path, capsys):
    _run(config, tmp_path, llm=FakeLLM({}, default="topic"))
    assert capsys.readouterr() == ("", "")


# --- thread id ---


def _context(config, **overrides):
    items, _, _, bodies = read_items(config, None, None)
    base = scan_graph.Context(config, items, bodies, set(), llm=lambda p: "x")
    return replace(base, **overrides)


def test_the_thread_id_names_the_setup_and_holds_only_a_hash(config):
    base = scan_graph.thread_id(_context(config))
    assert base == scan_graph.thread_id(_context(config)) and base.startswith("scan:") and len(base) == len("scan:") + 64
    for change in (
        {"label_model": "m"},
        {"verifier_model": "m"},
        {"offline": True},
        {"count_bodies": True},
        {"cluster_threshold": 0.5},
        {"llm": None},
        {"verifier": lambda p: ""},
        {"counter": lambda t: []},
        {"embedder": lambda t: []},
    ):
        assert scan_graph.thread_id(_context(config, **change)) != base, change


def test_the_thread_id_changes_with_an_item_description_or_a_body(config):
    base = _context(config)
    other_desc = replace(base, items=[replace(base.items[0], description="different"), *base.items[1:]])
    other_body = replace(base, bodies={**base.bodies, base.items[0].id: "different body"})
    assert len({scan_graph.thread_id(c) for c in (base, other_desc, other_body)}) == 3
    assert scan_graph.thread_id(replace(base, items=base.items[::-1])) == scan_graph.thread_id(base)  # order does not matter


# --- the CLI ---


def test_a_real_cli_scan_uses_the_default_checkpoint_and_prints_progress_to_stderr(config, tmp_path, capsys):
    out = tmp_path / "out.json"
    assert cli.main(["scan", str(config), "--out", str(out), "--no-usage", "--no-history"], llm=FakeLLM({}, default="topic")) == 0
    captured = capsys.readouterr()
    assert "labelled 6/6" in captured.err and "labelled" not in captured.out
    db = scan_graph.DEFAULT_CHECKPOINT
    assert stat.S_IMODE(db.stat().st_mode) == 0o600 and stat.S_IMODE(db.parent.stat().st_mode) == 0o700
    assert _threads(db) == set()


def test_a_dry_run_writes_no_checkpoint_and_no_progress(config, capsys):
    assert cli.main(["scan", str(config), "--dry-run", "--no-usage"]) == 0
    assert not scan_graph.DEFAULT_CHECKPOINT.exists()
    assert "labelled" not in capsys.readouterr().err


def test_a_resumed_verify_count_uses_the_saved_pair_total(config, tmp_path):
    db = tmp_path / "cp" / "scan.sqlite"
    with pytest.raises(Crash):
        _run(config, tmp_path, embedder=FakeEmbedder(VECTORS), verifier=Crashing(_verifier(), at=2), checkpoint=db)
    lines: list[str] = []
    verifier = _verifier()
    result = _run(config, tmp_path, embedder=FakeEmbedder(VECTORS), verifier=verifier, checkpoint=db, on_progress=lines.append)
    assert len(verifier.prompts) == 1 and scan_graph.CHECKPOINT_WARNING not in result.warnings
    assert lines == ["resuming an interrupted scan", "verified 1/2", "verified 2/2"]


def test_the_checkpoint_connection_can_be_used_from_other_threads(tmp_path):
    import threading

    saver = open_checkpointer(tmp_path / "x.sqlite")
    errors: list[BaseException] = []

    def use():
        try:
            saver.conn.execute("SELECT 1")
        except BaseException as error:  # noqa: BLE001
            errors.append(error)

    thread = threading.Thread(target=use)
    thread.start()
    thread.join()
    assert errors == []
    saver.conn.close()


def test_a_checkpoint_cannot_make_us_build_types_outside_the_state_types(tmp_path):
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    from constellation.models import Overlap

    permissive = JsonPlusSerializer(allowed_msgpack_modules=True)
    saver = open_checkpointer(tmp_path / "x.sqlite", scan_graph.STATE_TYPES)
    item = Item("id", "skill", "name", "d", "s")
    overlap = Overlap("a", "b", "duplicate", "r")
    assert saver.serde.loads_typed(permissive.dumps_typed(overlap)) == overlap
    assert not isinstance(saver.serde.loads_typed(permissive.dumps_typed(item)), Item)
    saver.conn.close()


def test_the_thread_id_hides_secrets_and_treats_a_missing_body_as_empty(config):
    base = _context(config)
    secret = "sk-planted-thread-secret-9"
    leaky = replace(base, items=[replace(base.items[0], description=f"uses {secret}"), *base.items[1:]], secrets={secret})
    masked = replace(base, items=[replace(base.items[0], description=f"uses {REDACTED}"), *base.items[1:]], secrets={secret})
    assert scan_graph.thread_id(leaky) == scan_graph.thread_id(masked)
    assert scan_graph.thread_id(replace(base, bodies={})) == scan_graph.thread_id(replace(base, bodies={i.id: "" for i in base.items}))


def test_the_safe_helpers_redact_with_the_scan_secrets(config):
    context = replace(_context(config), secrets={"plain-helper-secret-value"})
    assert context.safe("a plain-helper-secret-value b") == f"a {REDACTED} b"
    assert context.safe_warnings("x", ["k plain-helper-secret-value"]) == {"x": [f"k {REDACTED}"]}


def test_cluster_names_are_redacted_again_before_they_enter_state(config):
    from types import SimpleNamespace

    secret = "plain-cluster-secret-value"
    base = _context(config, embedder=lambda t: [], secrets={secret})
    ctx = replace(base, vectors={i.id: [1.0, 0.0] for i in base.items})
    state = {"labels": {i.id: f"topic {secret}" for i in ctx.items}}
    update = scan_graph.cluster_items(state, SimpleNamespace(context=ctx))
    assert update["clusters"] and all(secret not in c.name and REDACTED in c.name for c in update["clusters"])


def test_stream_asks_for_synchronous_saves_only_when_there_is_a_checkpointer(config):
    class Graph:
        def stream(self, start, config, **kwargs):
            self.kwargs = kwargs
            yield "values", {"final_warnings": []}

    for cfg, expected in (({"configurable": {"thread_id": "t"}}, "sync"), ({}, None)):
        graph = Graph()
        assert scan_graph._stream(graph, {}, _context(config), cfg, None, {}) == {"final_warnings": []}
        assert graph.kwargs.get("durability") == expected
        assert graph.kwargs["stream_mode"] == ["updates", "values"]


# --- privacy review fixes ---

HOME_LEAK = "private/projects/acme"


def _home():
    return str(Path.home())


def test_a_precondition_the_test_secret_matches_no_builtin_pattern():
    from constellation.redact import redact

    assert redact(f"x {SECRET} y") == f"x {SECRET} y"


def _bytes(folder):
    return b"".join(p.read_bytes() for p in sorted(folder.iterdir()))


def test_an_exception_message_never_reaches_the_checkpoint_files(config, tmp_path, monkeypatch):
    (config / ".env").write_text(f"FOO={SECRET}\n")
    db = tmp_path / "cp" / "scan.sqlite"

    def label_flush(path, fresh):
        raise RuntimeError(f"disk said {SECRET} at {Path.home()}/{HOME_LEAK}/x")

    monkeypatch.setattr(scan_graph, "label_flush", label_flush)
    with pytest.raises(RuntimeError) as caught:
        _run(config, tmp_path, llm=FakeLLM({}, default="topic"), checkpoint=db)
    assert SECRET not in str(caught.value) and _home() not in str(caught.value)
    saved = _bytes(db.parent)
    assert SECRET.encode() not in saved and _home().encode() not in saved


def test_a_node_error_is_redacted_and_stripped_of_paths_before_langgraph_can_save_it(config):
    from types import SimpleNamespace

    context = replace(_context(config), secrets={SECRET})

    def boom(state, runtime):
        raise OSError(13, f"nope {SECRET}", f"{Path.home()}/{HOME_LEAK}/f.json")

    with pytest.raises(OSError) as caught:
        scan_graph._guarded(boom)(None, SimpleNamespace(context=context))
    text = repr(caught.value)
    assert SECRET not in text and _home() not in text and caught.value.__cause__ is None and caught.value.__suppress_context__


def test_an_exception_class_that_cannot_be_rebuilt_from_a_message_becomes_a_node_error(config):
    from types import SimpleNamespace

    class Odd(Exception):
        def __init__(self, a, b):
            super().__init__(a, b)

    def boom(state, runtime):
        raise Odd("x", "y")

    with pytest.raises(scan_graph.NodeError, match="^Odd: "):
        scan_graph._guarded(boom)(None, SimpleNamespace(context=_context(config)))


def test_a_hard_killed_scan_leaves_no_secret_and_private_files(config, tmp_path):
    import os
    import subprocess
    import sys
    import textwrap

    (config / ".env").write_text(f"FOO={SECRET}\n")
    (config / "skills" / f"tool-{SECRET}").mkdir()
    (config / "skills" / f"tool-{SECRET}" / "SKILL.md").write_text(
        f"---\nname: tool-{SECRET}\ndescription: Reads PDF files {DESC_MARKER} {SECRET}.\n---\n{BODY_MARKER} {SECRET}\n"
    )
    (config / "agents").mkdir()
    (config / "agents" / f"agent-{SECRET}.md").write_text(f"---\nname: agent-{SECRET}\ndescription: An agent {SECRET}.\n---\nBody\n")
    db = tmp_path / "cp" / "scan.sqlite"
    script = textwrap.dedent(
        f"""
        import os, sys
        from pathlib import Path
        from fakes import FakeLLM
        from constellation import scan, scan_graph
        scan_graph.MAX_CONCURRENCY = 1
        calls = []
        def llm(prompt):
            calls.append(1)
            if len(calls) == 4:
                os._exit(7)  # a hard kill: no cleanup, no checkpoint close
            return "label {SECRET}"
        scan(Path({str(config)!r}), llm=llm, checkpoint=Path({str(db)!r}), usage=False, origins=False,
             label_cache=Path({str(tmp_path / "labels.json")!r}), cost_cache=Path({str(tmp_path / "costs.json")!r}))
        """
    )
    env = {**os.environ, "HOME": str(tmp_path / "home"), "PYTHONPATH": str(Path(__file__).parent)}
    done = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, timeout=120)
    assert done.returncode == 7, done.stderr.decode()[-2000:]

    names = sorted(p.name for p in db.parent.iterdir())
    assert "scan.sqlite-wal" in names  # the sidecar a hard kill leaves behind: the check below is not vacuous
    saved = _bytes(db.parent)
    assert b"skill:" in saved or b"agent" in saved
    for planted in (SECRET, BODY_MARKER, DESC_MARKER):
        assert planted.encode() not in saved
    for path in db.parent.iterdir():
        assert stat.S_IMODE(path.stat().st_mode) == 0o600, path.name
    assert stat.S_IMODE(db.parent.stat().st_mode) == 0o700


def test_item_ids_are_redacted_in_the_checkpoint_but_the_result_keeps_them(config, tmp_path):
    (config / ".env").write_text(f"FOO={SECRET}\n")
    (config / "skills" / f"tool-{SECRET}").mkdir()
    (config / "skills" / f"tool-{SECRET}" / "SKILL.md").write_text(f"---\nname: tool-{SECRET}\ndescription: A tool.\n---\nBody\n")
    db = tmp_path / "cp" / "scan.sqlite"
    with pytest.raises(Crash):
        _run(config, tmp_path, llm=Crashing(FakeLLM({}, default="topic"), at=4), checkpoint=db)
    assert SECRET.encode() not in _bytes(db.parent)

    result = _run(config, tmp_path, llm=FakeLLM({}, default="topic"), checkpoint=db)
    assert f"claude-code:skill:tool-{SECRET}" in {i.id for i in result.items}
    assert f"claude-code:skill:tool-{SECRET}" in result.labels  # keyed by the real id again


def test_ids_that_redact_to_the_same_text_stay_distinct_and_map_back(config):
    secrets = {"firstsecretvalue", "secondsecretvalue"}
    base = _context(config, secrets=secrets)
    items = [replace(base.items[0], id="x:skill:firstsecretvalue"), replace(base.items[1], id="x:skill:secondsecretvalue"), *base.items[2:]]
    context = replace(base, items=items)
    first, second = context.sid(items[0].id), context.sid(items[1].id)
    assert first == "x:skill:[REDACTED]" and second.startswith("x:skill:[REDACTED]#") and "secretvalue" not in first + second
    assert context.sid("zzz:firstsecretvalue") == "zzz:[REDACTED]"  # an id that is not an Item's is redacted on the spot
    assert context.rid("not:an:alias") == "not:an:alias"
    assert (context.rid(first), context.rid(second)) == (items[0].id, items[1].id)
    assert context.item(first) is items[0]
    assert context.sid(base.items[2].id) == base.items[2].id  # ids with no secret are unchanged


def test_warnings_lose_home_directories_and_quoted_paths(config):
    context = _context(config)
    text = f"could not save: [Errno 13] Permission denied: '{Path.home()}/.cache/x/labels.json' and {Path.home()}/y"
    [(_, [shown])] = context.safe_warnings("s", [text]).items()
    assert shown == "could not save: [Errno 13] Permission denied: '<path>' and ~/y"


def test_the_checkpoint_directory_lock_keeps_a_second_scan_off_the_file_and_off_the_other_threads(config, tmp_path):
    db = tmp_path / "cp" / "scan.sqlite"
    with pytest.raises(Crash):
        _run(config, tmp_path, llm=Crashing(FakeLLM({}, default="topic"), at=3), checkpoint=db)
    before = _threads(db)
    holder = open_checkpointer(db, scan_graph.STATE_TYPES, lock=True)  # another running scan
    try:
        llm = FakeLLM({}, default="topic")
        result = _run(config, tmp_path, llm=llm, checkpoint=db)
    finally:
        close_checkpointer(holder)
    assert result.warnings.count(scan_graph.CHECKPOINT_WARNING) == 1 and len(result.labels) == 6
    assert _threads(db) == before  # the other scan's thread was not deleted
    assert stat.S_IMODE((db.parent / "scan.sqlite.lock").stat().st_mode) == 0o600
    close_checkpointer(open_checkpointer(db, lock=True))  # and the lock is free again afterwards


def test_a_sqlite_error_while_saving_never_crashes_the_scan(config, tmp_path, monkeypatch):
    from langgraph.checkpoint.sqlite import SqliteSaver

    def full(self, *args, **kwargs):
        raise sqlite3.OperationalError("database or disk is full")

    monkeypatch.setattr(SqliteSaver, "put_writes", full)
    monkeypatch.setattr(SqliteSaver, "put", full)
    llm = FakeLLM({}, default="topic")
    lines: list[str] = []
    result = _run(config, tmp_path, llm=llm, checkpoint=tmp_path / "cp" / "scan.sqlite", on_progress=lines.append)
    assert result.warnings.count(scan_graph.CHECKPOINT_WARNING) == 1 and len(result.labels) == 6
    assert lines[-1] == "labelled 6/6"


def test_a_checkpoint_path_that_is_a_symlink_is_refused(config, tmp_path):
    target = tmp_path / "elsewhere.sqlite"
    target.write_bytes(b"precious")
    db = tmp_path / "cp" / "scan.sqlite"
    db.parent.mkdir()
    db.symlink_to(target)
    result = _run(config, tmp_path, llm=FakeLLM({}, default="topic"), checkpoint=db)
    assert result.warnings.count(scan_graph.CHECKPOINT_WARNING) == 1 and target.read_bytes() == b"precious"


def test_editing_one_file_after_a_kill_does_not_throw_away_the_paid_labels(config, tmp_path):
    db = tmp_path / "cp" / "scan.sqlite"
    first_inner = FakeLLM({}, default="topic")
    with pytest.raises(Crash):
        _run(config, tmp_path, llm=Crashing(first_inner, at=5), checkpoint=db)  # 5 of 6 labelled, one call killed
    labelled = {re.search(r"Name: (.*)", p)[1] for p in first_inner.prompts}
    edited = sorted(labelled)[0]
    (config / "skills" / edited / "SKILL.md").write_text(f"---\nname: {edited}\ndescription: Now different.\n---\nBody\n")

    second = FakeLLM({}, default="topic")
    result = _run(config, tmp_path, llm=second, checkpoint=db)

    assert len(second.prompts) == 2  # the edited Item and the killed one; the other four came from the salvaged replies
    assert len(result.labels) == 6 and _threads(db) == set()


def test_a_salvaged_reply_must_look_like_a_cache_entry(config, tmp_path):
    from types import SimpleNamespace

    saver = SimpleNamespace(
        get_tuple=lambda cfg: SimpleNamespace(
            checkpoint={"channel_values": {"label_replies": {"x" * 64: "not hex", "a" * 64: "good", "b" * 64: 5}}},
            pending_writes=[("t", "verdict_replies", {"c" * 64: '{"verdict":"overlap","reason":"r"}'})],
        )
    )
    context = replace(_context(config), label_cache=tmp_path / "l.json", verdict_cache=tmp_path / "v.json")
    scan_graph._salvage(saver, "t", context)
    import json

    assert json.loads((tmp_path / "l.json").read_text()) == {"a" * 64: "good"}
    assert list(json.loads((tmp_path / "v.json").read_text())) == ["c" * 64]


def test_the_thread_id_also_follows_ids_scope_hook_scripts_and_claude_md_size(config):
    base = _context(config)
    other_id = replace(base, items=[replace(base.items[0], id=base.items[0].id + "x"), *base.items[1:]])
    other_scope = replace(base, items=[replace(base.items[0], scope="project"), *base.items[1:]])
    assert len({scan_graph.thread_id(c) for c in (base, other_id, other_scope)}) == 3
    before = scan_graph.thread_id(base)
    (config / "CLAUDE.md").write_text("twelve bytes")
    assert scan_graph.thread_id(base) != before


def test_the_thread_id_follows_a_prompt_time_hook_script(tmp_path):
    root = tmp_path / "cfg"
    (root / "hooks").mkdir(parents=True)
    script = root / "hooks" / "inject.sh"
    script.write_text("echo one\n")
    hook = {"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", "command": f"cat {script}"}]}]}}
    (root / "settings.json").write_text(json.dumps(hook))
    items, _, _, bodies = read_items(root, None, None)
    context = scan_graph.Context(root, items, bodies, set())
    before = scan_graph.thread_id(context)
    script.write_text("echo two, longer\n")
    assert scan_graph.thread_id(context) != before


def test_a_failed_open_releases_the_lock_and_keeps_the_original_error(tmp_path):
    target = tmp_path / "elsewhere.sqlite"
    target.write_bytes(b"x")
    db = tmp_path / "cp" / "scan.sqlite"
    db.parent.mkdir()
    db.symlink_to(target)
    with pytest.raises(OSError):  # refused symlink, without a lock to release
        open_checkpointer(db)
    with pytest.raises(OSError):  # refused symlink, with the lock taken first
        open_checkpointer(db, lock=True)
    assert sorted(p.name for p in db.parent.iterdir()) == ["scan.sqlite", "scan.sqlite.lock"]
    db.unlink()
    close_checkpointer(open_checkpointer(db, lock=True))  # the lock was released by the failure


def test_a_second_lock_on_the_same_file_is_refused(tmp_path):
    db = tmp_path / "cp" / "scan.sqlite"
    first = open_checkpointer(db, lock=True)
    with pytest.raises(BlockingIOError):
        open_checkpointer(db, lock=True)
    open_checkpointer(db).conn.close()  # an unlocked handle (the review's) is not blocked
    close_checkpointer(first)


def test_scrub_never_rewrites_a_one_character_home(config, monkeypatch):
    context = _context(config)
    monkeypatch.setenv("HOME", "/")
    assert context.scrub("a/b/c") == "a/b/c"
    monkeypatch.setenv("HOME", "/h")
    assert context.scrub("see /h/file and '/etc/x'") == "see ~/file and '<path>'"


def test_safe_overlap_maps_both_ids_and_redacts_the_reason(config):
    base = _context(config, secrets={"firstsecretvalue", "secondsecretvalue"})
    items = [replace(base.items[0], id="x:skill:firstsecretvalue"), replace(base.items[1], id="x:skill:secondsecretvalue"), *base.items[2:]]
    context = replace(base, items=items)
    from constellation.models import Overlap

    safe = context.safe_overlap(Overlap(items[0].id, items[1].id, "overlap", "firstsecretvalue is shared"))
    assert (safe.a_id, safe.reason) == ("x:skill:[REDACTED]", f"{REDACTED} is shared") and safe.b_id.startswith("x:skill:[REDACTED]#")


def test_restore_puts_the_real_ids_back_into_every_keyed_part_of_the_final_state(config):
    from constellation.models import Cluster, Cost, Overlap, Weight

    base = _context(config, secrets={"firstsecretvalue", "secondsecretvalue"})
    items = [replace(base.items[0], id="x:skill:firstsecretvalue"), replace(base.items[1], id="y:skill:secondsecretvalue"), *base.items[2:]]
    context = replace(base, items=items)
    shown, other = context.sid(items[0].id), context.sid(items[1].id)
    state = {
        "labels": {shown: "l"},
        "clusters": [Cluster("c", (shown, other))],
        "costs": {shown: Cost(1, 2)},
        "hook_weights": {shown: Weight(1, None)},
        "final_overlaps": [Overlap(shown, other, "overlap", "r")],
        "final_warnings": ["w"],
    }
    back = context.restore(state)
    real, real_other = items[0].id, items[1].id
    assert back["labels"] == {real: "l"} and back["costs"] == {real: Cost(1, 2)} and back["hook_weights"] == {real: Weight(1, None)}
    assert back["clusters"] == [Cluster("c", (real, real_other))]
    assert back["final_overlaps"] == [Overlap(real, real_other, "overlap", "r")] and back["final_warnings"] == ["w"]
    assert context.restore({}) == {}
