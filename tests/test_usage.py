import json
from dataclasses import asdict

import pytest
from fakes import write_skill

from constellation import scan

CAVEAT = " Claude Code deletes old transcripts and {} skipped files were not read, so this is not proof it is unused."


def write_transcript(root, records, name="session.jsonl"):
    path = root / "projects" / "invented" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return path


def tool(name="Skill", value="tdd", id_="one", day="2026-11-02"):
    return {
        "type": "assistant",
        "timestamp": day + "T12:00:00Z",
        "message": {
            "content": [{"type": "tool_use", "name": name, "id": id_, "input": {"skill" if name == "Skill" else "subagent_type": value}}]
        },
    }


def test_skill_counts_dates_and_opt_out(tmp_path):
    write_skill(tmp_path, "tdd", "invented")
    write_skill(tmp_path, "unused", "different")
    write_transcript(tmp_path, [tool(), tool(id_="two", day="2026-11-04"), tool()])
    result = scan(tmp_path)
    assert asdict(result.usage["claude-code:skill:tdd"]) == {"count": 2, "last_used": "2026-11-04"}
    assert asdict(result.usage["claude-code:skill:unused"]) == {"count": 0, "last_used": None}
    assert asdict(result.usage_window) == {"files": 1, "first": "2026-11-02", "last": "2026-11-04", "skipped": 0}
    assert scan(tmp_path, usage=False).usage_window is None


def test_unused_report_and_suggestions(tmp_path):
    from constellation.report import render_cleanup, render_report
    from constellation.suggestions import suggest

    write_skill(tmp_path, "unused", "invented")
    write_transcript(tmp_path, [tool(value="absent")])
    data = asdict(scan(tmp_path))
    data["costs"] = {"claude-code:skill:unused": {"always_on": 42}}
    suggestions = suggest(data)
    assert len(suggestions) == 1
    assert suggestions[0].kind == "remove_unused"
    assert suggestions[0].tokens_saved == 42
    assert (
        suggestions[0].reason
        == "unused (skill) was never seen in 1 transcripts (2026-11-02 to 2026-11-02, 1 days). It costs 42 always-on tokens every session."
        + CAVEAT.format(0)
    )
    report = render_report(data, top=10, color=False, width=120, show_all=False)
    assert "Never used (in the transcripts scanned)" in report
    assert "unused (skill)  42 tokens" in report
    assert "Claude Code deletes old transcripts" in " ".join(report.split())
    assert "## Never used" in render_cleanup(data, top=10)


def plugin(root, name):
    path = root / "plugins" / "cache" / "market" / name / "1"
    (path / ".claude-plugin").mkdir(parents=True)
    (path / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": name}))
    return path


def counts(result):
    return {k.split(":", 2)[-1]: v.count for k, v in result.usage.items()}


def test_matching_scopes_slashes_agents_and_mcp(tmp_path):
    write_skill(tmp_path, "local", "local")
    for p in ("p", "q"):
        root = plugin(tmp_path, p)
        for name in ("local", "alone", "shared") if p == "p" else ("shared",):
            write_skill(root, name, name)
        (root / ".mcp.json").write_text(json.dumps({"mcpServers": {"s": {"command": "invented"}}}))
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "worker.md").write_text("---\nname: worker\ndescription: invented\n---\nwork")
    (tmp_path / ".mcp.json").write_text(
        json.dumps(
            {"mcpServers": {"s": {"command": "invented"}, "s__long": {"command": "invented"}, "a.b-c": {"url": "https://example.test"}}}
        )
    )
    records = [tool(value=v, id_=str(n)) for n, v in enumerate(("p:local", "local", "alone", "shared"))]
    records += [tool(name=n, value="worker", id_=n) for n in ("Agent", "Task")]
    records += [tool(name=n, id_=n) for n in ("mcp__s__t", "mcp__s__long__t", "mcp__a_b-c__t", "mcp__plugin_p_s__t", "mcp__claude_ai_x__t")]
    for n, content in enumerate(("<command-name>/local</command-name>", [{"type": "text", "text": "<command-name>/local</command-name>"}])):
        records.append({"type": "user", "uuid": "user-" + str(n), "message": {"content": content}})
    write_transcript(tmp_path, records)
    result = scan(tmp_path)
    assert counts(result) == {
        "local": 3,
        "p/local": 1,
        "p/alone": 1,
        "p/shared": 1,
        "q/shared": 1,
        "worker": 2,
        "s": 1,
        "s__long": 1,
        "a.b-c": 1,
        "p/s": 1,
        "q/s": 0,
    }
    assert result.warnings == ["usage: 1 invocation names matched more than one Item; each was credited"]


def test_scope_window_symlinks_and_missing(tmp_path):
    write_skill(tmp_path, "tdd", "invented")
    assert scan(tmp_path).usage_window.files == 0
    assert scan(tmp_path).warnings == []
    main = write_transcript(tmp_path, [tool(day="2026-11-04")])
    write_transcript(tmp_path, [tool(id_="sub", day="2026-10-01")], "session/subagents/sub.jsonl")
    for folder in ("tool-results", "memory"):
        write_transcript(tmp_path, [tool(id_=folder)], f"{folder}/ignored.jsonl")
    outside = tmp_path.parent / (tmp_path.name + "-outside")
    target = write_transcript(outside, [tool(id_="outside")])
    (main.parent / "link.jsonl").symlink_to(target)
    (main.parent.parent / "link").symlink_to(target.parent, target_is_directory=True)
    result = scan(tmp_path)
    assert counts(result) == {"tdd": 2}
    assert asdict(result.usage_window) == {"files": 2, "first": "2026-10-01", "last": "2026-11-04", "skipped": 2}
    config = tmp_path / "other"
    config.mkdir()
    (config / "projects").symlink_to(outside / "projects", target_is_directory=True)
    assert scan(config).warnings == ["usage: projects folder is a symlink; not read"]


def test_caps_drain_and_malformed(tmp_path, monkeypatch):
    import constellation.usage as reader

    write_skill(tmp_path, "tdd", "invented")
    valid = json.dumps(tool()).encode()
    cap = len(valid) + 1
    monkeypatch.setattr(reader, "LINE_CAP", cap)
    path = write_transcript(tmp_path, [])
    path.write_bytes(b"x" * (cap * 3) + b"\n" + valid + b"\n" + b'{"tool_use":' + b"\n")
    got = scan(tmp_path)
    assert counts(got) == {"tdd": 1}
    assert got.warnings == [
        "usage: skipped 1 malformed lines, 1 oversize line, 0 files (0 too big, 0 symlinks skipped on purpose, 0 unreadable)"
    ]
    monkeypatch.setattr(reader, "FILE_CAP", path.stat().st_size)
    assert scan(tmp_path).usage_window.files == 1
    monkeypatch.setattr(reader, "FILE_CAP", path.stat().st_size - 1)
    assert scan(tmp_path).usage_window.skipped == 1
    assert counts(scan(tmp_path)) == {"tdd": 0}


def test_wrong_shapes_and_bad_dates(tmp_path):
    import copy

    write_skill(tmp_path, "tdd", "invented")
    records = []
    for value in (None, [], 1, "oops"):
        r = tool(id_=str(value))
        r["message"] = value
        r["tool_use"] = True
        records.append(r)
    for field, value in (("input", []), ("name", None), ("id", 3)):
        r = tool()
        r["message"]["content"][0][field] = value
        records.append(r)
    r = tool()
    r["message"]["content"][0]["input"]["skill"] = []
    records.append(r)
    r = copy.deepcopy(tool())
    r["message"]["content"] = "tool_use"
    records.append(r)
    records += [tool(id_="bad", day="2026-99-99"), tool(id_="bad2", day="secret")]
    path = write_transcript(tmp_path, records)
    with path.open("a") as f:
        f.write('["tool_use"]\n')
    got = scan(tmp_path)
    assert counts(got) == {"tdd": 2}
    assert got.usage["claude-code:skill:tdd"].last_used is None
    assert got.warnings == [
        "usage: skipped 10 malformed lines, 0 oversize line, 0 files (0 too big, 0 symlinks skipped on purpose, 0 unreadable)"
    ]


def test_no_usage_never_calls_reader(tmp_path, monkeypatch):
    from constellation.cli import main

    def fail(*args):
        raise AssertionError("reader called")

    monkeypatch.setattr("constellation.read_usage", fail)
    assert scan(tmp_path, usage=False).usage == {}
    monkeypatch.chdir(tmp_path)
    assert main(["scan", str(tmp_path), "--offline", "--no-usage", "--out", str(tmp_path / "out.json")]) == 0
    data = json.loads((tmp_path / "out.json").read_text())
    assert data["usage"] == {} and data["usage_window"] is None


def test_planted_secret_all_sinks_and_provider_isolation(tmp_path, monkeypatch, capsys):
    import importlib
    import re

    from fakes import FakeCounter, FakeEmbedder, FakeLLM, FakeVerifier

    from constellation.cli import main

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("constellation.cli._local_embedder", lambda: None)
    root = tmp_path / "config"
    for name in ("tdd", "unused"):
        write_skill(root, name, name + " invented body")
    secret = "sk-ant-" + "PLANTED" * 6
    marker = "ZZQ-MARKER-7f3a"
    planted = secret + marker
    record = tool(id_=planted, day="2026-11-02")
    record["cwd"] = planted
    record["timestamp"] += planted
    record["message"]["content"][0]["input"]["other"] = planted
    record["message"]["content"] += [{"type": "text", "text": planted}]
    write_transcript(
        root,
        [record, tool(name="mcp__" + planted, id_="unmatched"), {"type": "user", "uuid": planted, "message": {"content": planted}}],
        planted + "/" + planted + ".jsonl",
    )
    # The filename above is at the main-session depth beneath a secret-bearing project folder.
    nested = root / "projects" / "invented" / planted / (planted + ".jsonl")
    dest = root / "projects" / planted / (planted + ".jsonl")
    dest.parent.mkdir()
    nested.rename(dest)
    output = tmp_path / "scan.json"
    llm, embedder, counter, verifier = FakeLLM({}), FakeEmbedder({}), FakeCounter(), FakeVerifier()
    assert main(["scan", str(root), "--out", str(output)], llm=llm, embedder=embedder, counter=counter, verifier=verifier) == 0
    data = json.loads(output.read_text())
    assert data["usage"]["claude-code:skill:tdd"] == {"count": 1, "last_used": "2026-11-02"}
    assert set(data["usage"]) <= {i["id"] for i in data["items"]}
    for value in data["usage"].values():
        assert type(value["count"]) is int
        assert value["last_used"] is None or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value["last_used"])
    for value in data["usage_window"].values():
        assert value is None or type(value) is int or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value)
    assert main(["report", str(output), "--cleanup", str(tmp_path / "cleanup.md")]) == 0
    assert main(["review", str(output), "--out", str(tmp_path / "approved.md")], decide=lambda s: "a") == 0
    checkpoint = importlib.import_module("constellation.review").DEFAULT_CHECKPOINT
    sinks = [
        output.read_bytes(),
        (tmp_path / "cleanup.md").read_bytes(),
        (tmp_path / "approved.md").read_bytes(),
        checkpoint.read_bytes(),
        capsys.readouterr().out.encode(),
        repr([llm.prompts, embedder.texts, counter.texts, verifier.prompts]).encode(),
    ]
    for sink in sinks:
        assert marker.encode() not in sink and secret.encode() not in sink

    # Separate fresh caches compare every provider input with usage disabled.
    def run(enabled, folder):
        a, b, c, d = FakeLLM({}), FakeEmbedder({}), FakeCounter(), FakeVerifier()
        scan(
            root,
            usage=enabled,
            llm=a,
            embedder=b,
            counter=c,
            verifier=d,
            label_cache=folder / "labels",
            cost_cache=folder / "costs",
            verdict_cache=folder / "verdicts",
        )
        return sorted(a.prompts), b.texts, c.texts, sorted(d.prompts)

    assert run(True, tmp_path / "on") == run(False, tmp_path / "off")
    # Unchanged setup uses cached paid work even with transcript reading enabled.
    a, c, d = FakeLLM({}), FakeCounter(), FakeVerifier()
    scan(root, llm=a, counter=c, verifier=d)
    assert a.prompts == [] and c.texts == [] and d.prompts == []


def test_reader_does_not_consult_environment(tmp_path, monkeypatch):
    import os
    from pathlib import Path

    import constellation.usage as reader
    from constellation.claude_code import read_items
    from constellation.usage import read_usage

    write_skill(tmp_path, "tdd", "invented")
    write_transcript(tmp_path, [tool()])
    items = read_items(tmp_path)[0]

    class Forbidden(dict):
        def __getitem__(self, key):
            raise AssertionError("environment read")

        def get(self, *args):
            raise AssertionError("environment read")

    with monkeypatch.context() as scoped:

        class LocalOS:
            environ = Forbidden()

            def __getattr__(self, name):
                return getattr(os, name)

        scoped.setattr(reader, "os", LocalOS())
        scoped.setattr(Path, "home", classmethod(lambda cls: (_ for _ in ()).throw(AssertionError("home read"))))
        got, window, warnings, _ = read_usage(tmp_path, items, [])
    assert got["claude-code:skill:tdd"].count == 1 and window.files == 1 and warnings == []


def test_synced_skill_dedup_across_files_and_window_noninvocations(tmp_path):
    synced = tmp_path / "skills" / "synced" / "account"
    (synced / "tdd").mkdir(parents=True)
    (synced / "tdd" / "SKILL.md").write_text("---\nname: tdd\ndescription: invented\n---\ninvented")
    write_transcript(tmp_path, [tool(), tool(id_="two", day="2026-10-01"), tool(id_="three", day="2026-11-04")])
    write_transcript(tmp_path, [tool(), {"timestamp": "2025-01-01T00:00:00Z"}], "other.jsonl")
    got = scan(tmp_path)
    assert counts(got) == {"synced/tdd": 3}
    assert got.usage["claude-code:skill:synced/tdd"].last_used == "2026-11-04"
    assert got.usage_window.first == "2025-01-01"


def test_unreadable_file_and_read_failure_do_not_abort(tmp_path, monkeypatch):
    import os

    import constellation.usage as reader

    write_skill(tmp_path, "tdd", "invented")
    path = write_transcript(tmp_path, [tool()], "unreadable.jsonl")
    write_transcript(tmp_path, [tool(id_="good")], "good.jsonl")
    original = os.open

    def fail(path_, flags, **kwargs):
        if path_ == path.name:
            raise PermissionError("must not escape")
        return original(path_, flags, **kwargs)

    monkeypatch.setattr(reader.os, "open", fail)
    got = scan(tmp_path)
    assert counts(got) == {"tdd": 1}
    assert got.usage_window.skipped == 1
    assert got.warnings == [
        "usage: skipped 0 malformed lines, 0 oversize line, 1 files (0 too big, 0 symlinks skipped on purpose, 1 unreadable)"
    ]


def test_report_unused_order_limits_unknown_and_window_states(tmp_path):
    from constellation.report import render_cleanup, render_report
    from constellation.suggestions import suggest

    for name in ("cheap", "expensive", "unknown", "used"):
        write_skill(tmp_path, name, name)
    write_transcript(tmp_path, [tool(value="used")])
    data = asdict(scan(tmp_path))
    data["costs"] = {"claude-code:skill:cheap": {"always_on": 1}, "claude-code:skill:expensive": {"always_on": 100}}
    unused = [s for s in suggest(data) if s.kind == "remove_unused"]
    assert [s.tokens_saved for s in unused] == [100, 1, None]
    assert unused[-1].reason == "unknown (skill) was never seen in 1 transcripts (2026-11-02 to 2026-11-02, 1 days)." + CAVEAT.format(0)
    assert unused == [s for s in suggest(data) if s.kind == "remove_unused"]
    out = render_cleanup(data, top=2).split("## Never used")[1]
    assert out.endswith("- [ ] expensive (skill)  100 tokens\n- [ ] cheap (skill)  1 tokens\n")
    assert "unknown (skill)  unknown cost" in render_cleanup(data, top=3)
    data["usage_window"]["files"] = 0
    assert suggest(data) == []
    assert "No transcripts found." in render_cleanup(data, top=3)
    assert "No transcripts found." in render_report(data, top=3, width=80, color=False, show_all=False)
    data["usage_window"] = None
    assert suggest(data) == []
    assert "Usage was not read in this scan." in render_cleanup(data, top=3)


def test_empty_windows_and_scope_extensions(tmp_path):
    write_skill(tmp_path, "tdd", "invented")
    assert asdict(scan(tmp_path).usage_window) == {"files": 0, "first": None, "last": None, "skipped": 0}
    path = write_transcript(tmp_path, [], "empty.jsonl")
    write_transcript(tmp_path, [tool()], "ignored.txt")
    write_transcript(tmp_path, [tool()], "session/subagents/ignored.txt")
    got = scan(tmp_path)
    assert asdict(got.usage_window) == {"files": 1, "first": None, "last": None, "skipped": 0}
    assert counts(got) == {"tdd": 0}
    path.unlink()
    path.parent.parent.rename(tmp_path / "saved-projects")
    (tmp_path / "projects").symlink_to(tmp_path / "saved-projects", target_is_directory=True)
    assert asdict(scan(tmp_path).usage_window) == {"files": 0, "first": None, "last": None, "skipped": 1}


def test_line_boundaries_without_newline_and_multiple_oversizes(tmp_path, monkeypatch):
    import constellation.usage as reader

    write_skill(tmp_path, "tdd", "invented")
    valid = json.dumps(tool()).encode()
    monkeypatch.setattr(reader, "LINE_CAP", len(valid))
    path = write_transcript(tmp_path, [])
    path.write_bytes(valid)
    assert counts(scan(tmp_path)) == {"tdd": 1}
    assert scan(tmp_path).warnings == []
    path.write_bytes(b"x" * (len(valid) + 1))
    assert scan(tmp_path).warnings == [
        "usage: skipped 0 malformed lines, 1 oversize line, 0 files (0 too big, 0 symlinks skipped on purpose, 0 unreadable)"
    ]
    path.write_bytes(b"x" * (len(valid) * 3) + b"\n" + b"y" * (len(valid) * 2) + b"\n" + valid)
    assert counts(scan(tmp_path)) == {"tdd": 1}
    assert scan(tmp_path).warnings == [
        "usage: skipped 0 malformed lines, 2 oversize line, 0 files (0 too big, 0 symlinks skipped on purpose, 0 unreadable)"
    ]


def test_multiple_oversize_files_and_open_errors(tmp_path, monkeypatch):
    import constellation.usage as reader

    write_skill(tmp_path, "tdd", "invented")
    for n in range(2):
        write_transcript(tmp_path, [tool(id_=str(n))], f"{n}.jsonl")
    monkeypatch.setattr(reader, "FILE_CAP", 1)
    got = scan(tmp_path)
    assert asdict(got.usage_window) == {"files": 0, "first": None, "last": None, "skipped": 2}
    assert counts(got) == {"tdd": 0}
    assert got.warnings == [
        "usage: skipped 0 malformed lines, 0 oversize line, 2 files (2 too big, 0 symlinks skipped on purpose, 0 unreadable)"
    ]
    (tmp_path / "projects" / "invented" / "link.jsonl").symlink_to(tmp_path / "nowhere")
    assert scan(tmp_path).warnings == [
        "usage: skipped 0 malformed lines, 0 oversize line, 3 files (2 too big, 1 symlinks skipped on purpose, 0 unreadable)"
    ]
    (tmp_path / "projects" / "invented" / "link.jsonl").unlink()

    original = reader.os.open

    def fail_file(name, flags, **kwargs):
        if str(name).endswith(".jsonl"):
            raise OSError("private")
        return original(name, flags, **kwargs)

    monkeypatch.setattr(reader.os, "open", fail_file)
    assert scan(tmp_path).usage_window.skipped == 2

    def fail(*args):
        raise OSError("private")

    monkeypatch.setattr(reader.os, "scandir", fail)
    assert scan(tmp_path).usage_window.skipped == 1


def test_unmatched_slash_and_invalid_user_shapes(tmp_path):
    write_skill(tmp_path, "tdd", "invented")
    records = [{"type": "user", "uuid": "u", "message": {"content": "<command-name>/missing</command-name>"}}]
    for content, uuid in (([{"type": "text", "text": []}], "u"), ("<command-name>/tdd</command-name>", 1)):
        records.append({"type": "user", "uuid": uuid, "message": {"content": content}, "tool_use": True})
    r = tool(name="Agent", value="missing", id_="agent")
    r["message"]["content"][0]["input"]["skill"] = "tdd"
    records.append(r)
    write_transcript(tmp_path, records)
    got = scan(tmp_path)
    assert counts(got) == {"tdd": 0}
    assert got.warnings == [
        "usage: skipped 2 malformed lines, 0 oversize line, 0 files (0 too big, 0 symlinks skipped on purpose, 0 unreadable)"
    ]


def test_normalized_plugin_and_server_preserve_uppercase(tmp_path):
    root = plugin(tmp_path, "P.dot")
    (root / ".mcp.json").write_text(json.dumps({"mcpServers": {"S.dot": {"command": "invented"}}}))
    write_transcript(tmp_path, [tool(name="mcp__plugin_P_dot_S_dot__t")])
    assert counts(scan(tmp_path)) == {"P.dot/S.dot": 1}


def test_saved_usage_report_exact_rows_kinds_redaction_and_limits():
    from constellation.report import render_cleanup, render_report
    from constellation.suggestions import suggest

    data = {
        "items": [
            {"id": str(n), "kind": kind, "name": str(n), "description": "", "source": ""}
            for n, kind in enumerate(("skill", "agent", "mcp_server", "connector", "hook", "plugin"))
        ],
        "usage": {str(n): {"count": 0} for n in range(6)},
        "usage_window": {"files": 2, "first": "2026-10-01", "last": "2026-11-04", "skipped": 0},
        "costs": {"0": {"always_on": 0}, "1": {"always_on": 0}},
    }
    text = render_report(data, top=3, color=False, width=200, show_all=False)
    section = text.split("Never used (in the transcripts scanned)")[1].split("Overlaps")[0]
    assert section.endswith("  0 (skill)  0 tokens\n  1 (agent)  0 tokens\n  2 (mcp_server)  unknown cost\n\n")
    note = (
        "Covers 2 transcript files from 2026-10-01 to 2026-11-04 (35 days); 0 files skipped. "
        "Claude Code deletes old transcripts, so 'never seen' covers only these files and is not proof an Item is unused."
    )
    assert note in section
    cleanup = render_cleanup(data, top=10).split("## Never used\n\n")[1]
    assert (
        cleanup
        == note
        + "\n- [ ] 0 (skill)  0 tokens\n- [ ] 1 (agent)  0 tokens\n- [ ] 2 (mcp_server)  unknown cost\n- [ ] 3 (connector)  unknown cost\n"
    )
    assert len(suggest(data)) == 4
    data["usage_window"]["files"] = 0
    assert render_cleanup(data, top=3).split("## Never used\n\n")[1] == "No transcripts found.\n"


def test_bounded_reads_and_subagent_symlinks(tmp_path, monkeypatch):
    import os

    import constellation.usage as reader

    write_skill(tmp_path, "tdd", "invented")
    path = write_transcript(tmp_path, [])
    valid = json.dumps(tool()).encode()
    monkeypatch.setattr(reader, "LINE_CAP", len(valid) + 1)
    path.write_bytes(b"x" * (len(valid) * 4) + b"\n" + valid + b"\n")
    original = os.fdopen

    class Bounded:
        def __init__(self, fd, mode):
            self.stream = original(fd, mode)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def fileno(self):
            return self.stream.fileno()

        def readline(self, limit):
            assert limit == len(valid) + 2
            return self.stream.readline(limit)

    monkeypatch.setattr(reader.os, "fdopen", Bounded)
    assert counts(scan(tmp_path)) == {"tdd": 1}
    outside = write_transcript(tmp_path / "outside", [tool(id_="outside")])
    sub = path.parent / "session" / "subagents"
    sub.mkdir(parents=True)
    (sub / "link.jsonl").symlink_to(outside)
    assert scan(tmp_path).usage_window.skipped == 1
    (sub / "link.jsonl").unlink()
    sub.rmdir()
    sub.symlink_to(outside.parent, target_is_directory=True)
    assert scan(tmp_path).usage_window.skipped == 1


def test_two_distinct_ambiguous_names_are_counted(tmp_path):
    for p in ("p", "q"):
        root = plugin(tmp_path, p)
        for name in ("a", "b"):
            write_skill(root, name, name)
    write_transcript(tmp_path, [tool(value="a", id_="a"), tool(value="b", id_="b")])
    assert scan(tmp_path).warnings == ["usage: 2 invocation names matched more than one Item; each was credited"]


def test_excluded_folders_and_recursive_json(tmp_path):
    write_skill(tmp_path, "tdd", "invented")
    for folder in ("memory", "tool-results"):
        write_transcript(tmp_path, [tool(id_=folder)], folder + "/subagents/ignored.jsonl")
    path = write_transcript(tmp_path, [])
    path.write_text(
        '{"type":"user","message":{"content":"ordinary text"}}\n'
        + "[" * 2000
        + '"tool_use"'
        + "]" * 2000
        + "\n"
        + json.dumps(tool())
        + "\n"
    )
    got = scan(tmp_path)
    assert counts(got) == {"tdd": 1}
    assert got.usage_window.files == 1
    assert got.warnings == [
        "usage: skipped 1 malformed lines, 0 oversize line, 0 files (0 too big, 0 symlinks skipped on purpose, 0 unreadable)"
    ]


def test_synced_item_shadows_bare_plugin_name(tmp_path):
    synced = tmp_path / "skills" / "synced" / "account" / "tdd"
    synced.mkdir(parents=True)
    (synced / "SKILL.md").write_text("---\nname: tdd\ndescription: invented\n---\nbody")
    write_skill(plugin(tmp_path, "p"), "tdd", "plugin")
    write_transcript(tmp_path, [tool()])
    assert counts(scan(tmp_path)) == {"synced/tdd": 1, "p/tdd": 0}


def test_prefilter_continues_and_copied_blocks_do_not_hide_new_ids(tmp_path):
    write_skill(tmp_path, "tdd", "invented")
    r = tool(id_="second")
    r["message"]["content"] = tool()["message"]["content"] + r["message"]["content"]
    write_transcript(tmp_path, [tool(), {"timestamp": "2026-10-01T00:00:00Z"}, r])
    assert counts(scan(tmp_path)) == {"tdd": 2}


def test_full_cap_line_with_newline_is_still_parsed(tmp_path, monkeypatch):
    import constellation.usage as reader

    write_skill(tmp_path, "tdd", "invented")
    valid = json.dumps(tool()).encode()
    monkeypatch.setattr(reader, "LINE_CAP", len(valid))
    path = write_transcript(tmp_path, [])
    path.write_bytes(valid + b"\n")
    assert counts(scan(tmp_path)) == {"tdd": 1}
    assert scan(tmp_path).warnings == []


def test_scandir_failure_adds_to_prior_skips(tmp_path, monkeypatch):
    import os

    import constellation.usage as reader

    write_skill(tmp_path, "tdd", "invented")
    path = write_transcript(tmp_path, [])
    (path.parent.parent / "a-link").symlink_to(path.parent, target_is_directory=True)
    original = os.scandir

    def fail(folder):
        if os.fstat(folder).st_ino == path.parent.stat().st_ino:
            raise PermissionError("private")
        return original(folder)

    monkeypatch.setattr(reader.os, "scandir", fail)
    assert scan(tmp_path).usage_window.skipped == 2


def test_record_and_block_types_must_be_strings(tmp_path):
    write_skill(tmp_path, "tdd", "invented")
    a, b = tool(), tool()
    a["type"] = []
    b["message"]["content"][0]["type"] = None
    b["tool_use"] = True
    write_transcript(tmp_path, [a, b])
    assert scan(tmp_path).warnings == [
        "usage: skipped 2 malformed lines, 0 oversize line, 0 files (0 too big, 0 symlinks skipped on purpose, 0 unreadable)"
    ]


@pytest.mark.parametrize("swapped", ["projects", "invented", "session", "subagents", "session.jsonl"])
def test_directory_and_file_swaps_never_read_outside_config(tmp_path, monkeypatch, swapped):
    import os

    import constellation.usage as reader

    config = tmp_path / "config"
    write_skill(config, "tdd", "invented")
    main = write_transcript(config, [], "session/subagents/session.jsonl")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "session.jsonl").write_text(json.dumps(tool()) + "\n")
    original = os.open
    triggered = []

    def swap(path, flags, *args, **kwargs):
        if os.fspath(path) == swapped and not triggered:
            triggered.append(True)
            target = next(
                p for p in [config / "projects", main.parent.parent.parent, main.parent.parent, main.parent, main] if p.name == swapped
            )
            target.rename(target.with_name(target.name + "-moved"))
            target.symlink_to(
                outside / "session.jsonl" if swapped.endswith(".jsonl") else outside, target_is_directory=not swapped.endswith(".jsonl")
            )
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(reader.os, "open", swap)
    result = scan(config)
    assert triggered
    assert counts(result) == {"tdd": 0}
    assert result.usage_window.skipped == 1


@pytest.mark.parametrize("read_fails", [False, True])
def test_directory_descriptors_close_after_scan_even_when_read_fails(tmp_path, monkeypatch, read_fails):
    import os

    import constellation.usage as reader

    write_skill(tmp_path, "tdd", "invented")
    write_transcript(tmp_path, [tool()], "session/subagents/sub.jsonl")
    opened = []
    original_open, original_close = os.open, os.close

    def track(name, flags, **kwargs):
        fd = original_open(name, flags, **kwargs)
        if flags & os.O_DIRECTORY:
            opened.append(fd)
        return fd

    closed = []

    def close(fd):
        closed.append(fd)
        original_close(fd)

    monkeypatch.setattr(reader.os, "open", track)
    monkeypatch.setattr(reader.os, "close", close)
    if read_fails:

        class FailingReader:
            def __init__(self, fd, mode):
                self.fd = fd

            def __enter__(self):
                return self

            def __exit__(self, *args):
                original_close(self.fd)

            def fileno(self):
                return self.fd

            def readline(self, limit):
                raise OSError("private transcript read failure")

        monkeypatch.setattr(reader.os, "fdopen", FailingReader)
    result = scan(tmp_path)
    assert counts(result) == {"tdd": 0 if read_fails else 1}
    assert result.usage_window.skipped == (1 if read_fails else 0)
    assert len(opened) == 5 and sorted(closed) == sorted(opened)


def test_fifo_swap_is_rejected_without_blocking(tmp_path, monkeypatch):
    import os

    import constellation.usage as reader

    write_skill(tmp_path, "tdd", "invented")
    path = write_transcript(tmp_path, [tool()])
    original = os.open

    def swap(name, flags, **kwargs):
        if name == path.name:
            assert flags & os.O_NONBLOCK
            path.unlink()
            os.mkfifo(path)
        return original(name, flags, **kwargs)

    monkeypatch.setattr(reader.os, "open", swap)
    got = scan(tmp_path)
    assert counts(got) == {"tdd": 0}
    assert asdict(got.usage_window) == {"files": 0, "first": None, "last": None, "skipped": 1}


def test_only_main_and_subagent_depths_are_read(tmp_path):
    write_skill(tmp_path, "tdd", "invented")
    main = write_transcript(tmp_path, [tool()], "z-main.jsonl")
    write_transcript(tmp_path, [tool(id_="sub")], "session/subagents/sub.jsonl")
    write_transcript(tmp_path, [tool(id_="wrong-session")], "session/ignored.jsonl")
    write_transcript(tmp_path, [tool(id_="wrong-project")], "../ignored.jsonl")
    deep = main.parent / "session" / "subagents" / "deeper"
    deep.mkdir()
    (deep / "link.jsonl").symlink_to(main)
    ignored = main.parent / "session" / "a-ignored"
    ignored.mkdir()
    (ignored / "ignored.jsonl").write_text(json.dumps(tool(id_="ignored")) + "\n")
    (main.parent / "memory" / "subagents").mkdir(parents=True)
    (main.parent / "memory" / "subagents" / "private.jsonl").write_text(json.dumps(tool(id_="memory")) + "\n")
    (main.parent / "tool-results" / "subagents").mkdir(parents=True)
    (main.parent / "tool-results" / "subagents" / "private.jsonl").write_text(json.dumps(tool(id_="results")) + "\n")
    result = scan(tmp_path)
    assert counts(result) == {"tdd": 2}
    assert result.usage_window.files == 2 and result.usage_window.skipped == 0
    assert result.warnings == []


def test_root_close_failure_preserves_prior_skip_count(tmp_path, monkeypatch):
    import os

    import constellation.usage as reader

    write_skill(tmp_path, "tdd", "invented")
    main = write_transcript(tmp_path, [])
    (main.parent / "link.jsonl").symlink_to(main)
    original_open, original_close = os.open, os.close
    root = []

    def track(name, flags, **kwargs):
        fd = original_open(name, flags, **kwargs)
        if name == tmp_path:
            root.append(fd)
        return fd

    def close(fd):
        original_close(fd)
        if fd in root:
            raise OSError("private close failure")

    monkeypatch.setattr(reader.os, "open", track)
    monkeypatch.setattr(reader.os, "close", close)
    result = scan(tmp_path)
    assert result.usage_window.skipped == 2
    assert result.warnings == [
        "usage: skipped 0 malformed lines, 0 oversize line, 2 files (0 too big, 1 symlinks skipped on purpose, 1 unreadable)"
    ]


@pytest.mark.parametrize("metadata_check", ["is_symlink", "is_file", "is_dir"])
def test_unreadable_entry_metadata_does_not_hide_later_transcripts(tmp_path, monkeypatch, metadata_check):
    import os
    from contextlib import contextmanager

    import constellation.usage as reader

    write_skill(tmp_path, "tdd", "invented")
    good = write_transcript(tmp_path, [tool()], "z-good.jsonl")
    bad = good.parent / ("a-unreadable.jsonl" if metadata_check == "is_file" else "a-unreadable")
    if metadata_check == "is_file":
        bad.write_text("")
    else:
        bad.mkdir()
    original = os.scandir
    failures = []

    class Entry:
        def __init__(self, entry):
            self.entry = entry

        def __getattr__(self, name):
            if self.entry.name == bad.name and name == metadata_check:

                def fail(**kwargs):
                    failures.append(name)
                    raise PermissionError("invented private metadata failure")

                return fail
            return getattr(self.entry, name)

    @contextmanager
    def entries(path):
        with original(path) as stream:
            yield (Entry(entry) for entry in stream) if isinstance(path, int) else stream

    monkeypatch.setattr(reader.os, "scandir", entries)
    result = scan(tmp_path)
    assert failures == [metadata_check]
    assert counts(result) == {"tdd": 1}
    assert asdict(result.usage_window) == {"files": 1, "first": "2026-11-02", "last": "2026-11-02", "skipped": 1}
    assert result.warnings == [
        "usage: skipped 0 malformed lines, 0 oversize line, 1 files (0 too big, 0 symlinks skipped on purpose, 1 unreadable)"
    ]


def user(text, uuid="u1"):
    return {"type": "user", "uuid": uuid, "timestamp": "2026-11-02T12:00:00Z", "message": {"content": text}}


def test_non_message_records_are_not_malformed(tmp_path):
    write_skill(tmp_path, "tdd", "invented")
    write_transcript(
        tmp_path,
        [
            {"type": "summary", "note": "tool_use", "timestamp": "2026-11-02T00:00:00Z"},
            {"type": "x", "text": "<command-name>"},
            {"type": "system", "message": "tool_use"},
            tool(),
        ],
    )
    got = scan(tmp_path)
    assert got.warnings == []
    assert counts(got) == {"tdd": 1}


def test_two_slash_commands_in_one_message_are_not_ambiguous(tmp_path):
    for name in ("a", "b"):
        write_skill(tmp_path, name, name)
    write_transcript(tmp_path, [user("<command-name>/a</command-name><command-name>/b</command-name>")])
    got = scan(tmp_path)
    assert counts(got) == {"a": 1, "b": 1}
    assert got.warnings == []


def test_ambiguity_is_per_lookup_even_beside_a_clear_command(tmp_path):
    write_skill(tmp_path, "b", "b")
    for p in ("p", "q"):
        write_skill(plugin(tmp_path, p), "a", "a")
    write_transcript(tmp_path, [user("<command-name>/a</command-name><command-name>/b</command-name>")])
    assert scan(tmp_path).warnings == ["usage: 1 invocation names matched more than one Item; each was credited"]


def test_symlinked_config_dir_is_read(tmp_path):
    real = tmp_path / "real"
    write_skill(real, "tdd", "invented")
    write_transcript(real, [tool()])
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    got = scan(link)
    assert counts(got) == {"tdd": 1}
    assert got.warnings == []
    assert got.usage_window.files == 1


def test_window_uses_top_level_timestamp_only(tmp_path):
    write_skill(tmp_path, "tdd", "invented")
    nested = {"message": {"content": [{"timestamp": "1999-01-01T00:00:00Z"}]}, "timestamp": "2026-11-03T00:00:00Z"}
    only_nested = {"message": {"content": [{"timestamp": "1998-01-01T00:00:00Z"}]}}
    write_transcript(tmp_path, [nested, only_nested, tool(day="2026-11-04")])
    got = scan(tmp_path)
    assert asdict(got.usage_window) == {"files": 1, "first": "2026-11-03", "last": "2026-11-04", "skipped": 0}
    assert got.usage["claude-code:skill:tdd"].last_used == "2026-11-04"


def test_undated_transcripts_never_print_none_and_skips_are_reported(tmp_path, monkeypatch, capsys):
    from constellation.cli import main
    from constellation.report import render_report

    write_skill(tmp_path, "unused", "invented")
    write_transcript(tmp_path, [{"type": "x"}])
    (tmp_path / "projects" / "invented" / "gone.jsonl").symlink_to(tmp_path / "nowhere")
    data = asdict(scan(tmp_path))
    assert data["usage_window"] == {"files": 1, "first": None, "last": None, "skipped": 1}
    report = render_report(data, top=5, color=False, width=200, show_all=False)
    assert "Covers 1 transcript files; 1 files skipped. Claude Code deletes old transcripts" in report
    monkeypatch.chdir(tmp_path)
    (tmp_path / "constellation.json").write_text(json.dumps(data))
    assert main(["review"], decide=lambda s: "s") == 0
    out = capsys.readouterr().out
    assert "unused (skill) was never seen in 1 transcripts." + CAVEAT.format(1) in out
    assert "None to None" not in out + report


def test_attachment_with_nested_tool_use_is_silent(tmp_path):
    write_skill(tmp_path, "tdd", "invented")
    nested = {"type": "tool_use", "name": "Skill", "id": "n", "input": {"skill": "tdd"}}
    write_transcript(tmp_path, [{"type": "attachment", "attachment": {"items": [nested]}}])
    got = scan(tmp_path)
    assert counts(got) == {"tdd": 0}
    assert got.warnings == []


def agent_and_skill(first):
    skill = {"type": "tool_use", "name": "Skill", "id": "s", "input": {"skill": "tdd"}}
    return {"type": "assistant", "message": {"content": [first, skill]}}


def test_agent_without_subagent_type_is_valid_and_credits_nothing(tmp_path):
    write_skill(tmp_path, "tdd", "invented")
    for name in ("Agent", "Task"):
        write_transcript(tmp_path, [agent_and_skill({"type": "tool_use", "name": name, "id": "a", "input": {}})])
        got = scan(tmp_path)
        assert counts(got) == {"tdd": 1}
        assert got.warnings == []


def test_one_bad_block_keeps_its_valid_neighbours(tmp_path):
    write_skill(tmp_path, "tdd", "invented")
    bad = [
        "oops",
        {"type": "tool_use", "name": "Agent", "id": "a", "input": {"subagent_type": 3}},
        {"type": "tool_use", "name": "Skill", "id": "a", "input": {}},
    ]
    write_transcript(tmp_path, [agent_and_skill(b) for b in bad] + [agent_and_skill(bad[0])])
    got = scan(tmp_path)
    assert counts(got) == {"tdd": 1}
    assert got.warnings == [
        "usage: skipped 4 malformed lines, 0 oversize line, 0 files (0 too big, 0 symlinks skipped on purpose, 0 unreadable)"
    ]
    two_bad = {"type": "assistant", "message": {"content": ["x", "y", agent_and_skill("z")["message"]["content"][1]]}}
    write_transcript(tmp_path, [two_bad])
    assert scan(tmp_path).warnings == [
        "usage: skipped 1 malformed lines, 0 oversize line, 0 files (0 too big, 0 symlinks skipped on purpose, 0 unreadable)"
    ]
    assert counts(scan(tmp_path)) == {"tdd": 1}


def test_skip_causes_are_counted_separately(tmp_path, monkeypatch):
    import constellation.usage as reader

    write_skill(tmp_path, "tdd", "invented")
    big = write_transcript(tmp_path, [tool()], "big.jsonl")
    (big.parent / "link.jsonl").symlink_to(big)
    original = reader.os.open

    def fail_file(name, flags, **kwargs):
        if str(name) == "nope.jsonl":
            raise OSError("private")
        return original(name, flags, **kwargs)

    (big.parent / "nope.jsonl").write_text("")
    monkeypatch.setattr(reader.os, "open", fail_file)
    monkeypatch.setattr(reader, "FILE_CAP", big.stat().st_size - 1)
    got = scan(tmp_path)
    assert got.usage_window.skipped == 3
    assert got.warnings == [
        "usage: skipped 0 malformed lines, 0 oversize line, 3 files (1 too big, 1 symlinks skipped on purpose, 1 unreadable)"
    ]


def test_blocks_only_count_for_their_own_role(tmp_path):
    write_skill(tmp_path, "tdd", "invented")
    use = {"type": "tool_use", "name": "Skill", "id": "s", "input": {"skill": "tdd"}}
    text = {"type": "text", "text": "<command-name>/tdd</command-name>"}
    write_transcript(
        tmp_path,
        [
            {"type": "user", "uuid": "u", "message": {"content": [use]}},
            {"type": "assistant", "uuid": "a", "message": {"content": [text]}},
        ],
    )
    got = scan(tmp_path)
    assert counts(got) == {"tdd": 0}
    assert got.warnings == []
