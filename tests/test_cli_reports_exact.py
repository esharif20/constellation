"""Exact-output tests for the terminal commands: goldens against the demo scan, plus small hand-built cases for every branch."""

import json
import os
import re
from pathlib import Path

import pytest

from constellation import cli_reports as cr
from constellation.cli import main

ROOT = Path(__file__).parent.parent
DEMO = ROOT / "docs" / "design" / "demo.json"
GOLDEN = Path(__file__).parent / "golden" / "cli"
ARGS = {"why": ["review-diff"], "ask": ["what costs the most?"]}
PLAIN, COLOUR = cr.Style(), cr.Style(color=True)
NAMES = [c.name for c in cr.COMMANDS if c.name not in ("clean", "share")]


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("as_json", [False, True])
def test_demo_output_matches_golden(name, as_json, capsys):
    assert main([name, *ARGS.get(name, []), str(DEMO), *(["--json"] if as_json else [])]) == 0

    assert capsys.readouterr().out == (GOLDEN / f"{name}{'.json' if as_json else '.txt'}").read_text()


# ---- Style ----


@pytest.mark.parametrize(("style", "code"), [("bold", "1"), (cr.OK, "32"), (cr.WARN, "33"), (cr.BAD, "31")])
def test_paint_wraps_in_the_ansi_code_only_with_colour(style, code):
    assert COLOUR.paint("hi", style) == f"\033[{code}m" + "hi\033[0m"
    assert PLAIN.paint("hi", style) == "hi"


def test_head_is_a_blank_line_then_the_bold_title():
    assert PLAIN.head("Top") == "\nTop"
    assert COLOUR.head("Top") == "\n\033[1mTop\033[0m"


def test_mark_paints_with_its_own_colour():
    assert [COLOUR.mark(m) for m in (cr.OK, cr.WARN, cr.BAD)] == ["\033[32m✓\033[0m", "\033[33m!\033[0m", "\033[31m✗\033[0m"]
    assert PLAIN.mark(cr.BAD) == "✗"


def test_style_defaults_are_plain_and_eighty_wide():
    assert (cr.Style().color, cr.Style().width) == (False, 80)


def test_table_pads_every_column_but_the_last_and_drops_trailing_blanks():
    assert PLAIN.table([["ab", "c", ""], ["abcd", "efg", "z"]]) == ["  ab    c", "  abcd  efg  z"]


def test_table_uses_the_given_indent_and_handles_one_column_and_unicode():
    assert PLAIN.table([["é", "x"], ["ab", "y"]], indent=">>") == [">>é   x", ">>ab  y"]
    assert PLAIN.table([["only"], ["a"]]) == ["  only", "  a"]


def test_table_leaves_blank_cells_blank():
    assert PLAIN.table([["none", "", ""]]) == ["  none"]
    assert PLAIN.table([["a", "", "c"], ["bb", "d", "e"]]) == ["  a      c", "  bb  d  e"]


@pytest.mark.parametrize(("width", "limit"), [(20, 12), (25, 12), (26, 12), (27, 13), (40, 26)])
def test_table_shortens_only_the_first_column_to_the_terminal(width, limit):
    first = cr.Style(width=width).table([["x" * 30, "aaa", "bbb"]])[0]

    assert first == "  " + "x" * (limit - 1) + "…" + "  aaa  bbb"


def test_table_keeps_a_first_column_that_exactly_fits():
    st = cr.Style(width=40)  # 40 - 6 (rest) - 6 (two gaps and the third... 2 * 3) - 2 (indent) = 26
    assert st.table([["x" * 26, "aaa", "bbb"]]) == ["  " + "x" * 26 + "  aaa  bbb"]
    assert st.table([["x" * 27, "aaa", "bbb"]]) == ["  " + "x" * 25 + "…  aaa  bbb"]


def test_table_width_counts_the_indent():
    assert cr.Style(width=40).table([["x" * 30, "aaa", "bbb"]], indent="    ") == ["    " + "x" * 23 + "…  aaa  bbb"]


def test_table_pads_to_the_widest_cell_in_each_column():
    rows = [["a", "bbbbb", "c"], ["aaa", "b", "ccc"]]

    assert PLAIN.table(rows) == ["  a    bbbbb  c", "  aaa  b      ccc"]


# ---- stdout style ----


def test_style_for_stdout_reads_the_terminal_width(monkeypatch):
    monkeypatch.setattr("sys.stdout.isatty", lambda: False, raising=False)
    for columns, expected in [(30, 40), (40, 40), (77, 77), (100, 100), (250, 100)]:
        monkeypatch.setattr("shutil.get_terminal_size", lambda columns=columns: os.terminal_size((columns, 24)))
        assert cr.style_for_stdout() == cr.Style(False, expected)


@pytest.mark.parametrize(
    ("tty", "no_color", "colour"), [(True, False, True), (True, True, False), (False, False, False), (False, True, False)]
)
def test_style_for_stdout_colour_needs_a_terminal_and_no_no_color(monkeypatch, tty, no_color, colour):
    monkeypatch.setattr("sys.stdout.isatty", lambda: tty, raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    if no_color:
        monkeypatch.setenv("NO_COLOR", "")

    assert cr.style_for_stdout().color is colour


def test_n_and_plural():
    assert (cr._n(None), cr._n(0), cr._n(1234567)) == ("unknown", "0", "1,234,567")
    assert (cr._plural(1, "day"), cr._plural(0, "day"), cr._plural(2000, "day")) == ("1 day", "0 days", "2,000 days")


# ---- load ----

BAD = "{} is missing or not a usable constellation scan; run `constellation scan` first."


def item(id_="a", **over):
    return {"id": id_, "name": id_, "kind": "skill", "description": "d", **over}


def scan_file(tmp_path, content):
    path = tmp_path / "scan.json"
    path.write_text(content if isinstance(content, str) else json.dumps(content))
    return path


def test_load_reads_the_demo_with_its_verdicts():
    s = cr.load(DEMO)

    assert len(s.data["items"]) == 97
    assert sorted(s.names.values()) == sorted(i["name"] for i in s.data["items"])
    assert set(s.found.assessments) == {i["id"] for i in s.data["items"]}


def test_load_passes_the_habits_path_to_compute(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(cr, "compute", lambda data, habits: seen.append(habits) or "found")
    habits = tmp_path / "habits.json"

    assert cr.load(scan_file(tmp_path, {"items": [item()]}), habits).found == "found"
    assert cr.load(scan_file(tmp_path, {"items": []})).found == "found"
    assert seen == [habits, None]


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "[]",
        "null",
        '{"items": 3}',
        '{"items": null}',
        '{"items": [3]}',
        '{"items": [{"id": "a"}]}',
        '{"items": [{"id": "a", "name": "a", "kind": "skill"}]}',
        '{"items": [{"id": "a", "name": "a", "kind": "skill", "description": 1}]}',
        '{"items": [{"id": 1, "name": "a", "kind": "skill", "description": "d"}]}',
        '{"items": [{"id": "a", "name": null, "kind": "skill", "description": "d"}]}',
        '{"items": [{"id": "a", "name": "a", "kind": 2, "description": "d"}]}',
        json.dumps({"items": [item("a"), item("a", name="b")]}),
    ],
)
def test_load_rejects_an_unusable_scan_with_the_exact_message(tmp_path, content):
    path = scan_file(tmp_path, content)

    with pytest.raises(cr.ReportError, match=f"^{re.escape(BAD.format(path))}$") as raised:
        cr.load(path)

    assert str(raised.value) == BAD.format(path) and raised.value.__cause__ is None


@pytest.mark.parametrize("make", ["missing", "directory", "binary"])
def test_load_rejects_missing_directory_and_unreadable_paths(tmp_path, make):
    path = tmp_path / "scan.json"
    if make == "directory":
        path.mkdir()
    if make == "binary":
        path.write_bytes(b"\xff\xfe\x00")

    with pytest.raises(cr.ReportError) as raised:
        cr.load(path)

    assert str(raised.value) == BAD.format(path)


def test_load_rejects_a_file_it_may_not_read(tmp_path):
    path = scan_file(tmp_path, {"items": []})
    path.chmod(0)
    try:
        if os.access(path, os.R_OK):
            pytest.skip("running as a user that ignores file modes")
        with pytest.raises(cr.ReportError) as raised:
            cr.load(path)
        assert str(raised.value) == BAD.format(path)
    finally:
        path.chmod(0o600)


def test_load_accepts_an_empty_item_list_and_unique_ids(tmp_path):
    assert cr.load(scan_file(tmp_path, {"items": []})).data == {"items": []}
    assert len(cr.load(scan_file(tmp_path, {"items": [item("a"), item("b")]})).data["items"]) == 2


def test_the_default_scan_path_is_read_when_none_is_given(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    code = main(["doctor"])

    assert code == 2
    assert capsys.readouterr().err == BAD.format("constellation.json") + "\n"
