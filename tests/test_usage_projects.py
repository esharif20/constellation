import json
from dataclasses import asdict

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
    result = scan(config, project=repo)
    assert result.projects == {"p1": "plan-43-44", "p2": "dev-other"} or result.projects == {"p1": "dev-other", "p2": "plan-43-44"}
    assert result.projects[result.current_project] == "plan-43-44"
    assert result.usage_by_project["claude-code:skill:tdd"].keys() == {"p1", "p2"} - {result.current_project}


def test_current_project_without_a_transcript_folder_has_no_key(tmp_path, home):
    repo = home / "dev" / "fresh"
    repo.mkdir(parents=True)
    result = scan(tmp_path / "cfg", project=repo)
    assert result.current_project is None and result.projects == {}


def test_label_rules(home):
    assert _label(folder(home, "dev-constellation"), 1, None) == "dev-constellation"
    assert _label("-elsewhere-x", 1, None) == "elsewhere-x"  # no home prefix: the folder name itself
    assert _label(_encode(home) + "-", 4, None) == "project 4"
    assert _label("---", 2, None) == "project 2"
    assert len(_label("x" * 100, 1, None)) == 60
    assert _label(folder(home, "k-" + "sk-" + "a" * 30), 1, None).count("sk-") == 0  # redacted
    assert _label("anything", 1, home / "repo-name") == "anything"  # not the current folder


def test_planted_folder_name_stays_local(tmp_path, home, monkeypatch):
    from constellation.report import render_cleanup, render_report
    from constellation.suggestions import suggest

    config = tmp_path / "cfg"
    write_skill(config, "tdd", "invented")
    write_skill(config, "unused", "invented")
    put(config, "-tmp-home-zzsecretclient", [tool(id_="z1"), tool(value="absent", id_="z2")])
    seen = []

    def llm(prompt):
        seen.append(prompt)
        return "label"

    result = scan(config, llm=llm)
    data = asdict(result)
    assert "zzsecretclient" in json.dumps(data["projects"])  # local only
    outputs = [
        "\n".join(result.warnings),
        render_report(data, top=10, color=False, width=120, show_all=True),
        json.dumps([asdict(s) for s in suggest(data)]),
        json.dumps(snapshot(data)),
        "\n".join(seen),
    ]
    try:
        outputs.append(render_cleanup(data))
    except TypeError:
        pass
    for text in outputs:
        assert "zzsecretclient" not in text
    for key in ("scope", "project", "projects", "usage_by_project", "current_project"):
        assert key not in snapshot(data)
        assert all(key not in item for item in snapshot(data).get("items", []))
