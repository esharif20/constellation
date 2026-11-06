import pytest

from constellation import analyze
from constellation.cli_reports import Style
from constellation.keys import Action

PLAIN = Style(False, 80)
ROWS = [
    analyze.Row("a", "quarterly-ledger", 410, "/x/a.md"),
    analyze.Row("b", "flashcard", 136, ""),
    analyze.Row("c", "yaml", 20, "/x/c.md"),
]


def test_rows_from_keeps_measured_items_in_order_with_their_source():
    cost = {"top": [{"id": "a", "name": "A", "tokens": 5}, {"id": "b", "name": "B", "tokens": None}, {"id": "c", "name": "C", "tokens": 0}]}
    scan = {"items": [{"id": "a", "source": "/s/a"}, {"id": "b", "source": "/s/b"}, {"id": "c"}]}
    assert analyze.rows_from(cost, scan) == [analyze.Row("a", "A", 5, "/s/a"), analyze.Row("c", "C", 0, "")]
    assert analyze.rows_from({"top": [{"id": "z", "name": "Z", "tokens": 1}]}, {}) == [analyze.Row("z", "Z", 1, "")]
    assert analyze.rows_from({"top": []}, {"items": []}) == []


def test_step_moves_and_clamps():
    assert analyze.step(0, "up", 3) == 0
    assert analyze.step(2, "up", 3) == 1
    assert analyze.step(2, "down", 3) == 2
    assert analyze.step(0, "down", 3) == 1
    assert analyze.step(1, "x", 3) == 1


@pytest.mark.parametrize(
    "key,kind",
    [("enter", "why"), ("right", "why"), ("r", "refresh"), ("o", "open"), ("p", "preview"), ("f", "file"), ("esc", "back"), ("q", "back")],
)
def test_step_actions_carry_the_selected_row(key, kind):
    assert analyze.step(2, key, 3) == Action(kind, 2)


def test_step_ctrl_c_and_empty_lists():
    assert analyze.step(1, "ctrl-c", 3) == Action("back")
    assert analyze.step(1, "left", 3) == Action("back", 1) and analyze.step(1, "b", 3) == Action("back", 1)
    assert analyze.step(0, "left", 0) == Action("back", 0) and analyze.step(0, "b", 0) == Action("back", 0)
    assert analyze.step(0, "r", 0) == Action("refresh", 0)
    assert analyze.step(0, "q", 0) == Action("back", 0)
    for key in ("enter", "o", "p", "f", "right"):
        assert analyze.step(0, key, 0) == 0


def test_shade_thresholds():
    assert analyze._shade(6, 10) == analyze.RED
    assert analyze._shade(5, 10) == analyze.BLUE
    assert analyze._shade(2, 10) == analyze.BLUE
    assert analyze._shade(1, 10) == analyze.GREEN
    assert analyze._shade(10, 10) == analyze.RED
    assert analyze._shade(6, 11) == analyze.BLUE  # 6/11 is under 60 percent
    assert analyze._shade(2, 11) == analyze.GREEN  # and 2/11 is under 20 percent
    assert analyze._shade(7, 11) == analyze.RED
    assert analyze._shade(3, 11) == analyze.BLUE


def test_fit():
    assert analyze._fit("abc", 3) == "abc"
    assert analyze._fit("abcd", 3) == "ab…"


def test_render_exact_frame():
    assert "\n".join(analyze.render(ROWS, 1, PLAIN, 5503, "3 Items")) == (
        "Analyze Setup  (5,503 tokens at session start)\n"
        "What loads at the start of every session, biggest first:  3 Items\n"
        "\n"
        "   1. " + "█" * 24 + "   7% | quarterly-ledger 410 tok\n"
        "▶  2. " + "█" * 8 + " " * 16 + "   2% | flashcard        136 tok\n"
        "   3. █" + " " * 23 + "   0% | yaml              20 tok\n"
        "\n"
        "↑↓→ | Enter | R Refresh | O Open | P Preview | F File | Esc/Q Back"
    )


def test_render_unknown_total_empty_and_narrow():
    lines = analyze.render(ROWS[:1], 0, PLAIN, None, "x")
    assert lines[0] == "Analyze Setup  (unknown tokens at session start)" and " -- | " in lines[3]
    assert " -- | " in analyze.render(ROWS[:1], 0, PLAIN, 0, "x")[3]
    empty = analyze.render([], 0, PLAIN, 10, "Scanning…")
    assert empty == [
        "Analyze Setup  (10 tokens at session start)",
        "What loads at the start of every session, biggest first:  Scanning…",
        "",
        "",
        "↑↓→ | Enter | R Refresh | O Open | P Preview | F File | Esc/Q Back",
    ]
    narrow = analyze.render(ROWS, 0, Style(False, 40), 5503, "3 Items")
    assert all(len(line) <= 40 for line in narrow)
    assert narrow[1].endswith("…") and narrow[-1].endswith("…")
    assert narrow[3] == "▶  1. █████   7% | quarterly-le… 410 tok"
    assert analyze.render(ROWS, 0, Style(False, 40), 5503, "x")[0] == "Analyze Setup  (5,503 tokens at session…"
    long = analyze.render([analyze.Row("a", "n" * 60, 1, "")], 0, Style(False, 60), 1, "x")[3]
    assert "n" * 19 + "… " in long and len(long) <= 60


def test_render_colours_by_size_and_marks_the_selection():
    lines = analyze.render(ROWS, 0, Style(True, 80), 5503, "3 Items")
    assert lines[0].startswith("\033[1;" + analyze.MAGENTA + "mAnalyze Setup\033[0m")
    assert lines[3].startswith("\033[" + analyze.BLUE + "m▶\033[0m \033[" + analyze.BLUE + "m 1.\033[0m ")
    assert "\033[" + analyze.RED + "m" + "█" * 24 + "\033[0m" in lines[3]
    assert "\033[" + analyze.BLUE + "m" + "█" * 8 + "\033[0m" in lines[4] and lines[4].startswith("  ")
    assert "\033[" + analyze.GREEN + "m█\033[0m" in lines[5]
    assert lines[3].endswith("\033[" + analyze.RED + "m410 tok\033[0m")
    assert lines[-1] == "\033[2m" + analyze.FOOTER + "\033[0m"
    assert "\033" not in "".join(analyze.render(ROWS, 0, PLAIN, 5503, "x"))


def test_view_wraps_render_and_step():
    view = analyze.View(ROWS, 5503)
    assert view.lines(1, PLAIN) == analyze.render(ROWS, 1, PLAIN, 5503, "3 Items")
    assert view.key(0, "down") == 1
    assert view.key(0, "enter") == Action("why", 0)
    assert analyze.View([], None).key(0, "enter") == 0


def test_colours_every_part_of_the_frame():
    lines = analyze.render(ROWS[:2], 0, Style(True, 80), 5503, "2 Items")
    dim = "\033[2m"
    assert lines[0] == "\033[1;" + analyze.MAGENTA + "mAnalyze Setup\033[0m" + dim + "  (5,503 tokens at session start)\033[0m"
    assert lines[1] == dim + "What loads at the start of every session, biggest first:  2 Items\033[0m"
    blue, red = analyze.BLUE, analyze.RED
    assert lines[3] == (
        f"\033[{blue}m▶\033[0m \033[{blue}m 1.\033[0m \033[{red}m"
        + "█" * 24
        + "\033[0m"
        + " " * 0
        + "   7% | "
        + f"\033[{blue}mquarterly-ledger\033[0m \033[{red}m410 tok\033[0m"
    )
    assert lines[4] == (
        f"   2. \033[{blue}m" + "█" * 8 + "\033[0m" + " " * 16 + "   2% | flashcard        \033[" + f"{blue}m136 tok\033[0m"
    )
    assert lines[-1] == dim + analyze.FOOTER + "\033[0m"


def test_narrow_widths_shorten_the_name_and_the_bar():
    row = analyze.Row("a", "n" * 16, 1, "")
    at_30 = analyze.render([row], 0, Style(False, 30), 1, "x")[3]
    assert "| " + "n" * 9 + "… " in at_30
    one = [analyze.Row("a", "n" * 13, 5, "")]
    widths = {w: analyze.render(one, 0, Style(False, w), 5, "x")[3].count("█") for w in (36, 37, 38, 40, 90)}
    assert widths == {36: 4, 37: 5, 38: 6, 40: 7, 90: 24}
