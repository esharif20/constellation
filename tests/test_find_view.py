import json
from pathlib import Path

from constellation.cli_reports import Style
from constellation.find_view import as_json, clean, fit, origin, render, split_warnings, trim


def hit(name="alpha", desc="Does a thing", why="heading: Intro", invoke="/alpha", kind="skill"):
    return {"id": "x", "kind": kind, "name": name, "description": desc, "invoke": invoke, "why": why}


def test_dim_style_is_ansi_2():
    assert Style(color=True).paint("x", "dim") == "\033[2mx\033[0m"


def test_card_frame_exact():
    out = render([hit(), hit("beta", "Other", "file: a.md", "/plug:beta")], "thing", 0, Style(), 60)
    assert out == [
        'Found 2 skills for "thing"',
        "",
        "1. alpha  skill · yours",
        "   Does a thing",
        "   matched: heading: Intro",
        "   /alpha",
        "",
        "2. beta  skill · plug",
        "   Other",
        "   matched: file: a.md",
        "   /plug:beta",
    ]


def test_singular_header_and_warning_line_exact():
    out = render([hit()], "q", 1, Style(), 120)
    assert out[0] == 'Found 1 skill for "q"'
    assert out[-2:] == ["", "1 file had loose frontmatter and was read leniently (--verbose lists them)"]
    assert render([hit()], "q", 3, Style(), 120)[-1] == "3 files had loose frontmatter and were read leniently (--verbose lists them)"
    assert "loose" not in "".join(render([hit()], "q", 0, Style(), 120))


def test_color_paints_title_meta_and_matched_and_warning():
    out = render([hit()], "q", 2, Style(color=True), 80)
    assert out[0] == '\033[1mFound 1 skill for "q"\033[0m'
    assert out[2] == "1. \033[1malpha\033[0m  \033[2mskill · yours\033[0m"
    assert out[4] == "   \033[2mmatched: heading: Intro\033[0m"
    assert out[-1].startswith("\033[2m2 files") and out[-1].endswith("\033[0m")


def test_limit_and_all():
    hits = [hit(f"s{n}", invoke=f"/s{n}") for n in range(10)]
    out = render(hits, "q", 0, Style(), 100)
    assert out[0] == 'Found 10 skills for "q"' and "8. s7  skill · yours" in out and not any(line.startswith("9.") for line in out)
    assert out[-1] == "Showing 8 of 10 (--all shows every match, --limit N sets it)."
    assert render(hits, "q", 0, Style(), 100, limit=None)[-1] == "    /s9"
    assert render(hits, "q", 0, Style(), 100, limit=10)[-1] == "    /s9"
    assert render(hits, "q", 0, Style(), 100, limit=2)[-1].startswith("Showing 2 of 10")
    assert render(hits[:8], "q", 0, Style(), 100)[-1] == "   /s7"


def test_no_match_with_and_without_closest():
    assert render([], "zzz", 0, Style(), 80) == ['No match for "zzz". Try fewer or different words.']
    assert render([], "zzz", 0, Style(), 80, closest=["a", "b", "c"]) == [
        'No match for "zzz". Try fewer or different words.',
        "",
        "Closest names: a, b, c",
    ]
    assert render([], "z", 1, Style(), 80)[-1] == "1 file had loose frontmatter and was read leniently (--verbose lists them)"


def test_lines_are_cut_to_width():
    long = "w" * 100
    out = render([hit(name=long, desc=long, why=long, invoke="/" + long)], "q", 0, Style(), 40)
    assert all(len(line) <= 40 for line in out)
    assert all(out[i].endswith("…") for i in (3, 4, 5))
    assert render([hit()], "x" * 100, 0, Style(), 30)[0] == "Found 1 skill for " + '"' + "x" * 10 + "…"
    assert len(render([], "x" * 100, 0, Style(), 30)[0]) == 30


def test_name_gets_at_least_eight_columns():
    out = render([hit(name="n" * 30)], "q", 0, Style(), 12)
    assert out[2] == "1. nnnnnnn…  skill · yours"


def test_trim_word_boundary():
    assert trim("abc def", 7) == "abc def"
    assert trim("abc def ghi", 7) == "abc def…"
    assert trim("abc defghi", 7) == "abc…"
    assert trim("abcdefghij", 5) == "abcde…"
    assert trim("abc, def ghi", 5) == "abc…"
    assert trim("abc def ghi", 4) == "abc…"


def test_fit():
    assert fit("abcd", 4) == "abcd"
    assert fit("abcde", 4) == "abc…"


def test_clean_home_redaction_and_whitespace():
    home = str(Path.home())
    assert clean(f"see {home}/x/y\n\n  now [REDACTED] ok") == "see ~/x/y now ok"
    assert clean("a[REDACTED]b") == "a b"


def test_origin():
    assert origin("/name") == "yours"
    assert origin("/plug:name") == "plug"
    assert origin("/a:b:c") == "a"


def test_split_warnings():
    loose = "frontmatter is not valid YAML, read name and description leniently (~/a)"
    assert split_warnings([loose, "other", loose]) == ([loose, loose], ["other"])


def test_json_has_structured_hits_and_no_loose_text():
    data = as_json([hit(desc="a\n b", invoke="/p:alpha")], "q", ["note"])
    assert data == {
        "query": "q",
        "hits": [
            {
                "name": "alpha",
                "kind": "skill",
                "description": "a b",
                "invoke": "/p:alpha",
                "why": "heading: Intro",
                "origin": "p",
                "rank": 1,
                "last_used": None,
                "always_on": None,
                "last_seen": "usage not read",
            }
        ],
        "warnings": ["note"],
    }
    json.dumps(data)


def test_description_trimmed_to_about_100_chars():
    out = render([hit(desc="word " * 60)], "q", 0, Style(), 200)
    assert out[3] == "   " + ("word " * 20).rstrip() + "…"


def test_numbers_align_when_ten_are_shown():
    out = render([hit(f"s{n}", invoke=f"/s{n}") for n in range(10)], "q", 0, Style(), 100, limit=None)
    assert "1.  s0  skill · yours" in out and "10. s9  skill · yours" in out


def test_name_cut_uses_the_exact_remaining_width():
    assert render([hit(name="n" * 20)], "q", 0, Style(), 30)[2] == "1. " + "n" * 11 + "…  skill · yours"


def test_showing_line_is_dim_in_color():
    out = render([hit(), hit("b")], "q", 0, Style(color=True), 100, limit=1)
    assert out[-1] == "\033[2mShowing 1 of 2 (--all shows every match, --limit N sets it).\033[0m"


def test_trim_keeps_trailing_letters_of_the_last_word():
    assert trim("abXX cdef", 6) == "abXX…"
