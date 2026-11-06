from types import SimpleNamespace

import pytest

from constellation import banner
from constellation.cli_reports import Style

V = "1.2.3"
ESC = "\033"
WORD = (
    " _   _       _  ___  _           _  ___ ___  _     ",
    "|   | | |\\| |_   |  |_  |   |   |_|  |   |  | | |\\|",
    "|_  |_| | |  _|  |  |_  |_  |_  | |  |  ___ |_| | |",
)
URL = "github.com/esharif20/constellation"


def test_wide_exact():
    assert banner.render(Style(False, 87), V, utf8=True) == [
        "⋆   ✦   ⋆   " + WORD[0],
        " ╲ ╱ ╲ ╱    " + WORD[1] + "  Map your Claude setup",
        "  ⋆   ⋆     " + WORD[2] + "  " + V,
        " " * 12 + URL,
    ]


def test_narrow_with_glyph_exact():
    assert banner.render(Style(False, 63), V, utf8=True) == [
        "⋆   ✦   ⋆   " + WORD[0],
        " ╲ ╱ ╲ ╱    " + WORD[1],
        "  ⋆   ⋆     " + WORD[2],
        " " * 12 + "Map your Claude setup · 1.2.3",
        " " * 12 + URL,
    ]
    assert banner.render(Style(False, 86), V, utf8=True)[3] == " " * 12 + "Map your Claude setup · 1.2.3"
    assert banner.render(Style(False, 63), "x" * 60, utf8=True)[3] == " " * 12 + ("Map your Claude setup · " + "x" * 60)[:50] + "…"


def test_narrow_without_glyph_exact():
    assert banner.render(Style(False, 62), V, utf8=True) == [*WORD, "Map your Claude setup · 1.2.3", URL]
    assert banner.render(Style(False, 54), V, utf8=True) == [*WORD, "Map your Claude setup · 1.2.3", URL]
    assert banner.render(Style(False, 54), "x" * 40, utf8=True)[3] == ("Map your Claude setup · " + "x" * 40)[:53] + "…"


def test_compact_exact():
    assert banner.render(Style(False, 53), V, utf8=True) == ["⋆✦⋆ Constellation", "Map your Claude setup · 1.2.3"]
    assert banner.render(Style(False, 40), "1.2.3", utf8=True)[1] == "Map your Claude setup · 1.2.3"
    assert banner.render(Style(False, 28), "1.2.3", utf8=True)[1] == "Map your Claude setup · 1.2…"


def test_ascii_fallback_is_pure_ascii():
    for w in (100, 70, 54, 40, 30):
        lines = banner.render(Style(True, w), V, utf8=False)
        assert "".join(lines).replace(ESC, "").isascii()
    assert banner.render(Style(False, 87), V, utf8=False)[:2] == [
        "*   +   *   " + WORD[0],
        " \\ / \\ /    " + WORD[1] + "  Map your Claude setup",
    ]
    assert banner.render(Style(False, 40), V, utf8=False) == ["*+* Constellation", "Map your Claude setup - 1.2.3"]
    assert banner.render(Style(False, 28), V, utf8=False)[1] == "Map your Claude setup - 1.2."


def test_colours():
    wide = banner.render(Style(True, 100), "1", utf8=True)

    def c(code, t):
        return f"{ESC}[{code}m{t}{ESC}[0m"

    assert wide[0] == c(banner.STEEL, "⋆") + "   " + c(banner.TEAL, "✦") + "   " + c(banner.STEEL, "⋆") + "   " + c(banner.OLIVE, WORD[0])
    assert wide[1].startswith(" " + c(banner.DIM, "╲") + " " + c(banner.DIM, "╱"))
    assert wide[1].endswith("  " + c(banner.OLIVE, "Map your Claude setup"))
    assert wide[2].endswith("  " + c(banner.DIM, "1"))
    assert wide[3] == " " * 12 + c(banner.STEEL, URL)
    narrow = banner.render(Style(True, 70), "1", utf8=True)
    assert narrow[3] == " " * 12 + c(banner.OLIVE, "Map your Claude setup · 1")
    assert narrow[4] == " " * 12 + c(banner.STEEL, URL)
    compact = banner.render(Style(True, 40), "1", utf8=True)
    assert compact[0] == c(banner.STEEL, "⋆") + c(banner.TEAL, "✦") + c(banner.STEEL, "⋆") + " " + c(banner.OLIVE, "Constellation")
    assert compact[1] == c("2", "Map your Claude setup · 1")


def test_no_color_has_no_escapes():
    assert ESC not in "".join(banner.render(Style(False, 100), V, utf8=True))


@pytest.mark.parametrize(
    ("enc", "ok"),
    [("utf-8", True), ("UTF-8", True), ("utf8", True), ("UTF_8", True), ("ascii", False), ("latin-1", False), (None, False), ("", False)],
)
def test_is_utf8(enc, ok):
    assert banner.is_utf8(enc) is ok


def test_default_follows_stdout_encoding(monkeypatch):
    monkeypatch.setattr(banner.sys, "stdout", SimpleNamespace(encoding="ascii"))
    assert banner.render(Style(False, 40), V)[0] == "*+* Constellation"
    monkeypatch.setattr(banner.sys, "stdout", SimpleNamespace(encoding="utf-8"))
    assert banner.render(Style(False, 40), V)[0] == "⋆✦⋆ Constellation"
    monkeypatch.setattr(banner.sys, "stdout", SimpleNamespace())
    assert banner.render(Style(False, 40), V)[0] == "*+* Constellation"


def test_fit_keeps_text_exactly_as_wide_as_the_width():
    assert banner.render(Style(False, 40), "x" * 16, utf8=True)[1] == "Map your Claude setup · " + "x" * 16


def test_ascii_colours():
    def c(code, t):
        return f"{ESC}[{code}m{t}{ESC}[0m"

    wide = banner.render(Style(True, 100), "1", utf8=False)
    assert wide[0].startswith(c(banner.STEEL, "*") + "   " + c(banner.TEAL, "+") + "   " + c(banner.STEEL, "*"))
    assert wide[1].startswith(" " + c(banner.DIM, "\\") + " " + c(banner.DIM, "/") + " " + c(banner.DIM, "\\") + " " + c(banner.DIM, "/"))
