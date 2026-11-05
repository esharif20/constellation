import json
import socket
import stat
from pathlib import Path

import pytest

from constellation import cli
from constellation.cli import main
from constellation.preview import delta, render_delta, render_preview

PACK = Path(__file__).parent / "fixtures" / "preview_pack" / "pdf-kit"


def run(capsys, *argv):
    code = main([str(a) for a in argv])
    out = capsys.readouterr()
    return code, out.out, out.err


def saved_scan(tmp_path) -> Path:
    path = tmp_path / "scan.json"
    items = [{"id": "s-mine", "kind": "skill", "name": "trace-canvas", "description": "Mine.", "source": ""}]
    path.write_text(json.dumps({"items": items}))
    return path


def test_preview_prints_summary(tmp_path, capsys):
    code, out, _ = run(capsys, "preview", PACK, "--against", saved_scan(tmp_path))
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == "pdf-kit (plugin): 5 Items - 2 skills, 1 command, 1 MCP server, 1 plugin"
    assert lines[1].startswith("Every session: about ") and lines[1].endswith(
        " estimated from text length); 1 MCP server or hook unknown until installed"
    )
    assert "Possible overlap with your setup: 1" in lines
    assert "  trace-canvas (skill) and your trace-canvas (skill): same name" in lines
    assert lines[-1] == "Nothing was run or sent. Hook commands and MCP servers are shown as text only."
    assert "Meaning-based overlap is off" in out  # no embedder was asked for


def test_preview_writes_private_file(tmp_path, capsys):
    out = tmp_path / "p.json"
    scan = saved_scan(tmp_path)
    assert run(capsys, "preview", PACK, "--against", scan, "--out", out)[0] == 0
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    assert json.loads(out.read_text())["pack"]["name"] == "pdf-kit"
    code, _, err = run(capsys, "preview", PACK, "--against", scan, "--out", out)
    assert (code, "already exists" in err) == (2, True)
    assert run(capsys, "preview", PACK, "--against", scan, "--out", out, "--force")[0] == 0


def test_preview_never_touches_network_or_env(tmp_path, capsys, monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("network")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(cli, "load_env", refuse)
    monkeypatch.setattr(cli, "_local_embedder", refuse)  # --meaning is off by default: the model is never loaded
    scan = saved_scan(tmp_path)
    assert run(capsys, "preview", PACK, "--against", scan)[0] == 0
    code, out, _ = run(capsys, "delta", scan, scan)
    assert code == 0 and "New Overlaps" in out


def test_preview_refusal_exit_2(tmp_path, capsys):
    pack = tmp_path / "evil-pack"
    (pack / "skills").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (pack / "skills" / "evil").symlink_to(outside)
    code, out, err = run(capsys, "preview", pack, "--against", tmp_path / "none.json")
    assert code == 2 and "skills/evil" in err and str(tmp_path) not in err.replace(str(pack), "") and out.count("pdf") == 0


def test_preview_not_a_dir_or_empty(tmp_path, capsys):
    code, _, err = run(capsys, "preview", tmp_path / "missing")
    assert (code, err) == (2, f"{tmp_path / 'missing'} is not a directory.\n")
    (tmp_path / "empty").mkdir()
    code, _, err = run(capsys, "preview", tmp_path / "empty", "--against", tmp_path / "none.json")
    assert (code, err) == (2, "No plugin, skill pack or SKILL.md found in empty.\n")


def test_preview_without_saved_scan_says_so(tmp_path, capsys):
    code, out, _ = run(capsys, "preview", PACK, "--against", tmp_path / "constellation.json")
    assert code == 0
    assert (
        f"No saved scan at {tmp_path / 'constellation.json'}, so overlap with your setup was not checked. Run `constellation scan` first."
        in out
    )
    assert "Possible overlap" not in out


def test_preview_meaning_flag_uses_injected_or_local_embedder(tmp_path, capsys, monkeypatch):
    scan = saved_scan(tmp_path)
    calls: list[int] = []

    def embedder(texts):
        calls.append(len(texts))
        return [[1.0, 0.0] for _ in texts]

    assert main(["preview", str(PACK), "--against", str(scan)], embedder=embedder) == 0
    assert calls
    capsys.readouterr()
    monkeypatch.setattr(cli, "_local_embedder", lambda: embedder)
    calls.clear()
    code, _, err = run(capsys, "preview", PACK, "--against", scan, "--meaning")
    assert code == 0 and "downloads it from the network" in err and calls
    monkeypatch.setattr(cli, "_local_embedder", lambda: None)
    code, out, err = run(capsys, "preview", PACK, "--against", scan, "--meaning")
    assert code == 0 and "downloads" not in err and "Meaning-based overlap is off" in out


def scan_of(*items, costs=None, overlaps=None):
    return {
        "items": [{"id": i, "kind": k, "name": n, "description": "", "source": ""} for i, k, n in items],
        "costs": {i: {"always_on": c, "on_use": None} for i, c in (costs or {}).items()},
        "overlaps": overlaps or [],
    }


def test_delta_counts_added_removed_and_cost(capsys, tmp_path):
    before = scan_of(("a", "skill", "alpha"), ("b", "skill", "beta"), costs={"a": 10, "b": 5})
    after = scan_of(
        ("a", "skill", "alpha"),
        ("c", "skill", "gamma"),
        ("d", "skill", "delta"),
        ("e", "mcp_server", "epsilon"),
        costs={"a": 10, "c": 40, "d": 21},
    )
    d = delta(before, after)
    assert d["added"] == ["c", "d", "e"] and d["removed"] == ["b"]
    assert d["added_by_kind"] == {"mcp_server": 1, "skill": 2}
    assert d["always_on_known"] == 71 - 15 and d["unknown_added"] == 1
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps(before))
    b.write_text(json.dumps(after))
    code, out, _ = run(capsys, "delta", a, b)
    assert code == 0
    assert out.splitlines() == [
        "+3 Items, -1 (2 skills, 1 MCP server)",
        "Removed: beta",
        "Every session: +56 known tokens; 1 added Items have unknown cost",
        "New Overlaps with added Items: 0",
    ]
    assert run(capsys, "delta", a, tmp_path / "x.json")[0] == 2


def test_delta_new_overlaps_only():
    both = {"a_id": "a", "b_id": "b", "verdict": "overlap", "reason": "old"}
    new = {"a_id": "a", "b_id": "c", "verdict": "duplicate", "reason": "same job"}
    distinct = {"a_id": "b", "b_id": "c", "verdict": "distinct", "reason": "no"}
    untouched = {"a_id": "a", "b_id": "d", "verdict": "overlap", "reason": "no added item"}
    before = scan_of(("a", "skill", "alpha"), ("b", "skill", "beta"), ("d", "skill", "dee"), overlaps=[both])
    after = scan_of(
        ("a", "skill", "alpha"),
        ("b", "skill", "beta"),
        ("c", "skill", "gamma"),
        ("d", "skill", "dee"),
        overlaps=[both, new, distinct, untouched],
    )
    d = delta(before, after)
    assert d["new_overlaps"] == [new]
    text = render_delta(d, {"a": "alpha", "c": "gamma"})
    assert text.splitlines()[-2:] == ["New Overlaps with added Items: 1", "  alpha and gamma: duplicate - same job"]


def test_render_plurals_and_warnings():
    p = {
        "pack": {"name": "x", "layout": "pack"},
        "counts": {"hook": 2, "skill": 1, "agent": 1},
        "always_on": {"counted": 3, "estimated": 4, "unknown": 2},
        "already_installed": True,
        "compared": True,
        "overlaps": [{"new_id": "new:1", "existing_id": "s", "existing_name": "pdf-tools", "why": "similar meaning"}],
        "items": [{"id": "new:1", "kind": "skill", "name": "pdf-reader"}],
        "note": "n",
        "warnings": ["w"],
    }
    assert render_preview(p).splitlines() == [
        "x (pack): 4 Items - 2 hooks, 1 agent, 1 skill",
        "Every session: about 7 tokens (3 counted, 4 estimated from text length); 2 MCP servers or hooks unknown until installed",
        "A plugin with this name is already in your setup.",
        "Possible overlap with your setup: 1",
        "  pdf-reader (skill) and your pdf-tools: similar meaning",
        "n",
        "Warning: w",
        "Nothing was run or sent. Hook commands and MCP servers are shown as text only.",
    ]


def test_render_one_unknown_and_none():
    p = {
        "pack": {"name": "x", "layout": "skill"},
        "counts": {"skill": 1},
        "always_on": {"counted": 0, "estimated": 2, "unknown": 1},
        "already_installed": False,
        "compared": False,
        "overlaps": [],
        "items": [],
        "note": None,
        "warnings": [],
    }
    lines = render_preview(p).splitlines()
    assert lines[1].endswith("; 1 MCP server or hook unknown until installed")
    p["always_on"]["unknown"] = 0
    lines = render_preview(p).splitlines()
    assert lines == [
        "x (skill): 1 Items - 1 skill",
        "Every session: about 2 tokens (0 counted, 2 estimated from text length)",
        "Nothing was run or sent. Hook commands and MCP servers are shown as text only.",
    ]


def test_delta_without_overlap_keys_and_removed_lines():
    before = {"items": [{"id": "a", "kind": "skill", "name": "alpha"}]}
    after = {"items": [{"id": "b", "kind": "skill", "name": "beta"}]}
    d = delta(before, after)
    assert d["new_overlaps"] == [] and d["always_on_known"] == 0 and d["unknown_added"] == 1
    assert render_delta(d, {"a": "alpha", "b": "beta"}).splitlines()[:2] == ["+1 Items, -1 (1 skill)", "Removed: alpha"]
    two = {**d, "removed": ["a", "b"]}
    assert render_delta(two, {"a": "alpha", "b": "beta"}).splitlines()[1] == "Removed: alpha, beta"


@pytest.mark.parametrize("name", ["preview", "delta"])
def test_help_text(name, capsys):
    with pytest.raises(SystemExit):
        main([name, "--help"])
    assert f"constellation {name}" in capsys.readouterr().out
