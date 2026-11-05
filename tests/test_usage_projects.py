import json
from dataclasses import asdict
from pathlib import Path

import pytest
from fakes import write_skill
from test_usage import tool

from constellation import scan
from constellation.snapshot import snapshot
from constellation.usage import _encode, _label


@pytest.fixture
def home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home.resolve()


def put(config, folder, records, name="s.jsonl"):
    path = config / "projects" / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records))


def folder(home, tail):
    return _encode(home) + "-" + tail


def test_keys_labels_counts_and_dates(tmp_path, home):
    config = tmp_path / "cfg"
    write_skill(config, "tdd", "invented")
    write_skill(config, "spread", "invented")
    write_skill(config, "idle", "invented")
    put(config, folder(home, "dev-gamma-x"), [tool(value="tdd", id_="g1", day="2026-11-03"), tool(value="spread", id_="g2")])
    put(
        config,
        folder(home, "dev-alpha"),
        [tool(value="tdd", id_="a1"), tool(value="tdd", id_="a2", day="2026-11-04"), tool(value="spread", id_="a3")],
    )
    put(config, folder(home, "dev-beta"), [tool(value="spread", id_="b1")])
    put(config, folder(home, "dev-quiet"), [tool(value="absent", id_="q1")])  # no tracked invocation: no key
    result = scan(config)
    assert result.projects == {"p1": "dev-alpha", "p2": "dev-beta", "p3": "dev-gamma-x"}
    assert result.current_project is None
    got = {i: {k: asdict(u) for k, u in per.items()} for i, per in result.usage_by_project.items()}
    assert got["claude-code:skill:tdd"] == {"p1": {"count": 2, "last_used": "2026-11-04"}, "p3": {"count": 1, "last_used": "2026-11-03"}}
    assert set(got["claude-code:skill:spread"]) == {"p1", "p2", "p3"}
    assert "claude-code:skill:idle" not in got
    assert result.usage["claude-code:skill:tdd"].count == 3  # the global count is unchanged


def test_dedup_stays_global_across_projects(tmp_path, home):
    config = tmp_path / "cfg"
    write_skill(config, "tdd", "invented")
    put(config, folder(home, "a"), [tool(id_="same")])
    put(config, folder(home, "b"), [tool(id_="same")])
    result = scan(config)
    assert result.usage["claude-code:skill:tdd"].count == 1
    assert list(result.usage_by_project["claude-code:skill:tdd"]) == ["p1"]


def test_current_project_label_keeps_hyphens_and_gets_a_key_without_usage(tmp_path, home):
    repo = home / "dev" / "plan-43-44"
    repo.mkdir(parents=True)
    config = tmp_path / "cfg"
    write_skill(config, "tdd", "invented")
    put(config, _encode(repo), [tool(value="absent")])
    put(config, folder(home, "dev-other"), [tool(id_="o")])
    put(config, folder(home, "dev-quiet"), [tool(value="absent", id_="q")])  # uncredited and not current: no key
    put(config, "XXXX", [tool(value="absent", id_="x")])
    result = scan(config, project=repo)
    assert len(result.projects) == 2
    assert result.projects == {"p1": "plan-43-44", "p2": "dev-other"} or result.projects == {"p1": "dev-other", "p2": "plan-43-44"}
    assert result.projects[result.current_project] == "plan-43-44"
    assert result.usage_by_project["claude-code:skill:tdd"].keys() == {"p1", "p2"} - {result.current_project}


def test_no_project_means_no_current_key_even_for_an_odd_folder(tmp_path, home):
    config = tmp_path / "cfg"
    put(config, "XXXX", [tool(value="absent")])
    assert scan(config).projects == {} and scan(config).current_project is None


def test_current_project_without_a_transcript_folder_has_no_key(tmp_path, home):
    repo = home / "dev" / "fresh"
    repo.mkdir(parents=True)
    result = scan(tmp_path / "cfg", project=repo)
    assert result.current_project is None and result.projects == {}


def test_label_rules(home):
    assert _label(folder(home, "dev-constellation"), 1, None, home) == "dev-constellation"
    assert _label("-elsewhere-x", 1, None, home) == "elsewhere-x"  # no home prefix: the folder name itself
    assert _label(_encode(home) + "-", 4, None, home) == "project 4"
    assert _label("---", 2, None, home) == "project 2"
    assert len(_label("x" * 100, 1, None, home)) == 60
    assert _label(folder(home, "k-" + "sk-" + "a" * 30), 1, None, home).count("sk-") == 0  # redacted
    assert _label("anything", 1, home / "repo-name", home) == "anything"  # not the current folder
    assert _label("-no-home-given", 1, None, None) == "no-home-given"
    assert _label("-Mixed-CaseX-", 1, None, None) == "Mixed-CaseX"  # strips only dashes; keeps upper case
    assert _label(folder(home, "Dev-Z9"), 1, None, home) == "Dev-Z9"
    assert _label("-a.b_c", 1, None, None) == "a.b_c"
    assert _label("None-x", 1, None, None) == "None-x"  # no home: nothing is stripped
    assert _encode(Path("/A/b_c.d z")) == "-A-b-c-d-z"


def test_a_bare_home_never_shows_the_username(home):
    user = home.name
    assert _label(_encode(home), 3, None, home) == "project 3"  # Claude Code run in ~ itself
    assert _label(_encode(home), 3, home, home) == "project 3"  # --project ~
    assert user not in _label(_encode(home), 3, home, home)


def test_labels_drop_control_bidi_and_zero_width_characters(home):
    odd = "al\u202epha\u200b\x00\x1b-b\u00e9ta"
    assert _label(folder(home, odd), 1, None, home) == "alpha-bta"
    assert _label("x", 1, Path("/tmp/pr\u202eoj\u200b\x07"), None) == "x"  # not the current folder
    repo = home / "dev" / "pr\u202eoj\u200bect\x07"
    assert _label(_encode(repo), 1, repo, home) == "project"


def test_ambiguous_item_names_are_credited_to_the_project_of_each_item(tmp_path, home):
    from test_usage import plugin

    config = tmp_path / "cfg"
    for name in ("p", "q"):
        write_skill(plugin(config, name), "dup", name)
    put(config, folder(home, "a"), [tool(value="dup", id_="a1")])
    result = scan(config)
    ids = [i for i in result.usage if i.endswith("/dup")]
    assert len(ids) == 2
    assert all(result.usage_by_project[i] == {"p1": result.usage[i]} for i in ids)
    assert result.warnings == ["usage: 1 invocation names matched more than one Item; each was credited"]


def test_through_the_cli_json(tmp_path, home):
    from constellation.cli import main

    config, out = tmp_path / "cfg", tmp_path / "out.json"
    write_skill(config, "tdd", "invented")
    put(config, folder(home, "dev-alpha"), [tool(id_="a1")])
    assert main(["scan", str(config), "--out", str(out), "--offline"]) == 0
    data = json.loads(out.read_text())
    assert data["projects"] == {"p1": "dev-alpha"}
    assert data["usage_by_project"]["claude-code:skill:tdd"] == {"p1": {"count": 1, "last_used": "2026-11-02"}}
    assert data["current_project"] is None


def test_planted_folder_name_stays_local(tmp_path, home):
    from fakes import FakeCounter, FakeEmbedder, FakeLLM, FakeVerifier

    from constellation.report import render_cleanup, render_report
    from constellation.suggestions import suggest

    config = tmp_path / "cfg"
    write_skill(config, "tdd", "invented")
    write_skill(config, "unused", "invented")
    put(config, "-tmp-home-zzsecretclient", [tool(id_="z1"), tool(value="absent", id_="z2")])
    llm, embedder, counter, verifier = FakeLLM({}), FakeEmbedder({}), FakeCounter(), FakeVerifier()
    caches = {n: tmp_path / f"{n}.json" for n in ("cost", "verdict", "label")}
    result = scan(
        config,
        llm=llm,
        embedder=embedder,
        counter=counter,
        count_bodies=True,
        verifier=verifier,
        cost_cache=caches["cost"],
        verdict_cache=caches["verdict"],
        label_cache=caches["label"],
    )
    data = asdict(result)
    assert "zzsecretclient" in json.dumps(data["projects"])  # local only
    outputs = [
        "\n".join(result.warnings),
        render_report(data, top=10, color=False, width=120, show_all=True),
        render_cleanup(data, top=10),
        json.dumps([asdict(s) for s in suggest(data)]),
        json.dumps(snapshot(data)),
        "\n".join(llm.prompts + embedder.texts + counter.texts + verifier.prompts),
        *(p.read_text() for p in caches.values() if p.exists()),
    ]
    for text in outputs:
        assert "zzsecretclient" not in text
    for key in ("scope", "project", "projects", "usage_by_project", "current_project"):
        assert key not in snapshot(data)
        assert all(key not in item for item in snapshot(data).get("items", []))


def test_subagent_transcripts_count_for_their_project_and_bare_home_numbers_follow_order(tmp_path, home):
    config = tmp_path / "cfg"
    write_skill(config, "tdd", "invented")
    put(config, _encode(home), [tool(id_="h1")])  # Claude run in ~: sorts first, label "project 1"
    put(config, folder(home, "dev-a") + "/sess/subagents", [tool(id_="s1")], name="agent.jsonl")
    result = scan(config)
    assert result.projects == {"p1": "project 1", "p2": "dev-a"}
    assert result.usage_by_project["claude-code:skill:tdd"].keys() == {"p1", "p2"}
