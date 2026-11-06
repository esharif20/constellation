import io
import json
import shlex
from pathlib import Path

import pytest

from constellation import cli
from constellation import next_step as ns
from constellation.cli_reports import Style


@pytest.mark.parametrize(
    ("command", "result", "expected"),
    [
        ("unused", {"rows": [{"name": "old-skill"}, {"name": "b"}]}, "constellation why old-skill"),
        ("unused", {"rows": [{"name": "two words"}]}, "constellation why 'two words'"),
        ("unused", {"rows": []}, None),
        ("unused", None, None),
        ("unused", {"rows": [{"label": "x"}]}, None),
        ("find", {"hits": [{"name": "pdf-tool"}]}, "constellation why pdf-tool"),
        ("find", {"hits": []}, None),
        ("cost", None, "constellation clean"),
        ("scan", None, "constellation status"),
        ("clean", {}, "constellation open"),
        ("status", None, "constellation unused"),
        ("doctor", None, "constellation cost"),
        ("twins", {"rows": [{"name": "x"}]}, None),
        ("nonsense", None, None),
    ],
)
def test_next_step_is_chosen_from_the_result(command, result, expected):
    assert ns.next_step(command, result) == expected


def test_the_suggestion_is_a_runnable_command_line():
    assert shlex.split(ns.next_step("unused", {"rows": [{"name": "two words"}]})) == ["constellation", "why", "two words"]


def test_hint_line_is_dim_with_colour_and_plain_without():
    assert ns.hint_line(Style(False, 80), "cost", None) == "Next: constellation clean"
    assert ns.hint_line(Style(True, 80), "cost", None) == "\033[2mNext: constellation clean\033[0m"
    assert ns.hint_line(Style(True, 80), "twins", None) is None


class Tty(io.StringIO):
    def isatty(self):
        return True


DEMO = Path(__file__).parent.parent / "docs" / "design" / "demo.json"


def run_main(monkeypatch, tty, *argv):
    out = Tty() if tty else io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    monkeypatch.setenv("NO_COLOR", "1")
    assert cli.main(list(argv)) == 0
    return out.getvalue()


def test_a_terminal_run_ends_with_a_next_line_chosen_from_the_result(monkeypatch, tmp_path):
    scan = json.loads(DEMO.read_text())
    scan["usage_window"] = {"files": 3, "first": "2026-01-01", "last": "2026-03-01"}
    scan["usage"] = {i["id"]: {"count": 0 if i["name"] == "yaml-lint" else 5, "last_used": "2026-03-01"} for i in scan["items"]}
    (tmp_path / "s.json").write_text(json.dumps(scan))
    assert run_main(monkeypatch, True, "unused", str(tmp_path / "s.json")).endswith("Next: constellation why atlas\n")
    assert "Next:" not in run_main(monkeypatch, True, "unused", str(DEMO))
    assert run_main(monkeypatch, True, "cost", str(DEMO)).endswith("Next: constellation clean\n")


def test_no_next_line_when_piped_or_json(monkeypatch):
    assert "Next:" not in run_main(monkeypatch, False, "cost", str(DEMO))
    assert "Next:" not in run_main(monkeypatch, True, "cost", str(DEMO), "--json")
    assert "Next:" not in run_main(monkeypatch, False, "status", str(DEMO))


def test_status_in_a_terminal_suggests_the_next_command(monkeypatch):
    assert run_main(monkeypatch, True, "status", str(DEMO)).endswith("Next: constellation unused\n")
