"""Checkpointed scans (#22 T3): resume without re-paying, privacy of the checkpoint file, corrupt files, progress lines."""

import shutil
import sqlite3
import stat
from dataclasses import replace
from pathlib import Path

import pytest
from fakes import FakeCounter, FakeEmbedder, FakeLLM, FakeVerifier, verdict

from constellation import cli, scan, scan_graph
from constellation.checkpoint import open_checkpointer
from constellation.claude_code import read_items
from constellation.models import Item
from constellation.redact import REDACTED

OVERLAP = Path(__file__).parent / "fixtures" / "overlap_config"
SECRET = "sk-test-planted-4f9c2d71aa"
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
    (config / ".env").write_text(f"PLANTED_KEY={SECRET}\n")
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
    (config / ".env").write_text(f"PLANTED_KEY={SECRET}\n")
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
    (config / ".env").write_text(f"PLANTED_KEY={SECRET}\n")
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
    real, seen = scan_graph.labels_done, []

    def broken_once(state, runtime):
        seen.append(1)
        if len(seen) == 1:
            raise RuntimeError("stale")
        return real(state, runtime)

    broken_once.__name__ = "labels_done"
    monkeypatch.setattr(scan_graph, "labels_done", broken_once)
    lines: list[str] = []
    result = _run(config, tmp_path, llm=FakeLLM({}, default="topic"), checkpoint=db, on_progress=lines.append)

    assert result.warnings.count(scan_graph.CHECKPOINT_WARNING) == 1
    assert len(result.labels) == 6 and _threads(db) == set()
    assert lines.count("labelled 6/6") == 2  # the failed resume, then the restart, both reported


def test_a_failure_in_a_fresh_checkpointed_scan_is_raised_not_hidden(config, tmp_path, monkeypatch):
    def labels_done(state, runtime):
        raise RuntimeError("bug")

    monkeypatch.setattr(scan_graph, "labels_done", labels_done)
    with pytest.raises(RuntimeError, match="bug"):
        _run(config, tmp_path, llm=FakeLLM({}, default="topic"), checkpoint=tmp_path / "scan.sqlite")


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


def test_stream_asks_for_synchronous_saves_only_when_there_is_a_checkpointer():
    class Graph:
        def stream(self, start, config, **kwargs):
            self.kwargs = kwargs
            yield "values", {"final_warnings": []}

    for config, expected in (({"configurable": {"thread_id": "t"}}, "sync"), ({}, None)):
        graph = Graph()
        assert scan_graph._stream(graph, {}, None, config, None, {}) == {"final_warnings": []}
        assert graph.kwargs.get("durability") == expected
        assert graph.kwargs["stream_mode"] == ["updates", "values"]
