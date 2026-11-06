"""The menu in a real pseudo-terminal, read back through a screen emulator (tests/vt.py): what a user would see, not what was written."""

import os
import re
import sys
from pathlib import Path

import pytest
from vt import Term

from constellation import banner, menu, progress
from constellation.cli_reports import Style

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="needs a pty")

SRC = str(Path(__file__).parent.parent / "src")
LAUNCH = "import sys; from constellation.cli import main; sys.exit(main([]))"
UP, DOWN, ENTER, ESC, CTRL_C = b"\x1b[A", b"\x1b[B", b"\r", b"\x1b", b"\x03"


def start(tmp_path: Path, rows: int, cols: int, **env: str) -> Term:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    base = {
        "HOME": str(home),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "TERM": "xterm-256color",
        "PYTHONPATH": SRC,
        "PATH": os.environ["PATH"],
    }
    term = Term([sys.executable, "-c", LAUNCH], rows, cols, {**base, **env})
    while not term.screen.text().strip():  # python takes a moment to start
        term.settle(0.3, 2)
    term.settle(0.5, 5)
    return term


def test_more_page_taller_than_the_screen_never_scrolls_and_keeps_the_selection_in_view(tmp_path):
    term = start(tmp_path, 24, 80)
    term.send("m")
    for _ in range(30):
        term.send(DOWN, quiet=0.05)
    screen = term.send(DOWN, quiet=0.2)
    term.close()
    assert term.screen.scrolled == 0
    assert "➤ 28." in screen and "Doctor --env" in screen
    assert len(term.screen.lines()) <= 23


@pytest.mark.parametrize("cols", [40, 54, 80])
def test_main_menu_fits_the_width_and_still_shows_how_to_quit(tmp_path, cols):
    term = start(tmp_path, 24, cols)
    screen = term.send(DOWN)
    term.close()
    assert all(len(line) <= cols for line in screen.splitlines())
    assert "Q Quit" in screen


def test_resizing_the_window_redraws_the_menu_at_the_new_width(tmp_path):
    term = start(tmp_path, 40, 100)
    term.resize(40, 44)
    term.settle(1.0, 5)
    screen = term.send(DOWN)
    term.close()
    assert max(len(line) for line in screen.splitlines()) <= 44
    assert screen.count("1. Scan") == 1  # one frame, not the old one plus the new one


def test_ctrl_c_on_the_main_menu_exits_130_and_shows_the_cursor(tmp_path):
    term = start(tmp_path, 24, 80)
    term.send(CTRL_C, quiet=0.2)
    assert term.exit_code() == 130
    shown = term.screen.cursor_visible
    term.close()
    assert shown


def test_a_terminal_that_is_not_utf8_gets_plain_symbols_instead_of_a_crash(tmp_path):
    term = start(tmp_path, 24, 80, PYTHONIOENCODING="latin-1", PYTHONUTF8="0")
    screen = term.send(DOWN)
    term.send(CTRL_C, quiet=0.2)
    code = term.exit_code()
    term.close()
    assert "Traceback" not in screen and "> 2. Open" in screen
    assert code == 130


def test_scan_progress_line_is_cut_to_the_terminal_width():
    line = "Scanning ~/.claude  [\x1b[32m████\x1b[2m░░░░\x1b[0m] 100%  counting tokens, grouping clusters 30/30"
    cut = progress._cut(line, 39)
    assert len(re.sub(r"\x1b\[[0-9;]*m", "", cut)) == 39
    assert "\x1b[0m" in cut


def test_reporter_never_draws_past_the_last_column():
    import io

    out = io.StringIO()
    rep = progress.Reporter("Scanning ~/.claude", True, False, columns=40, out=out)
    rep(progress.ProgressEvent("analyze", 5, 30))
    drawn = out.getvalue().split("\r")[-1].replace(progress.CLEAR_LINE, "")
    assert len(drawn) <= 39


def test_render_with_a_height_windows_a_long_list_and_never_fills_the_screen():
    st = Style(False, 80)
    entries = tuple((f"Entry {n}", "hint") for n in range(28))
    for index in (0, 14, 27):
        frame = menu.render(index, st, "1.0", entries, False, height=24)
        assert len(frame) <= 23
        assert any(f"Entry {index} " in line and "➤" in line for line in frame)


def test_footer_falls_back_to_a_shorter_hint_that_keeps_quit():
    assert "Q Quit" in menu.render(0, Style(False, 40), "1.0")[-1]


def test_ascii_safe_swaps_symbols_only_off_utf8():
    assert banner.ascii_safe("➤ ↑↓ · …", "utf-8") == "➤ ↑↓ · …"
    assert banner.ascii_safe("➤ ↑↓ · … é✦", "latin-1") == "> Up/Dn - ... é?"


def test_analyze_file_key_has_no_path_to_show_when_the_scan_only_names_the_tool():
    from constellation import analyze

    scan = {"items": [{"id": "a", "source": "claude-code"}, {"id": "b", "source": "/x/b/SKILL.md"}]}
    rows = analyze.rows_from({"top": [{"id": "a", "name": "a", "tokens": 5}, {"id": "b", "name": "b", "tokens": 4}]}, scan)
    assert [r.path for r in rows] == ["", "/x/b/SKILL.md"]
