import pytest

from constellation.keys import Action, edit, key_stream, parse_key, split_keys


@pytest.mark.parametrize(
    "data,key",
    [
        (b"\x1b[A", "up"),
        (b"\x1b[B", "down"),
        (b"\x1b[C", "right"),
        (b"\x1b", "esc"),
        (b"\r", "enter"),
        (b"\n", "enter"),
        (b"\x03", "ctrl-c"),
        (b"\x04", "q"),
        (b"", "q"),
        (b"Q", "q"),
        (b"3", "3"),
        (b" ", " "),
        (b"\x1b[D", "left"),
        (b"\x80", ""),
        (b"\xff", ""),
        (b"ab", ""),
        (b"\x7f", "backspace"),
        (b"\x08", "backspace"),
    ],
)
def test_parse_key(data, key):
    assert parse_key(data) == key


def test_action_defaults_to_choice_zero():
    assert Action("quit") == Action("quit", 0)
    assert Action("run", 3).choice == 3


def test_split_keys_cuts_one_read_into_single_keys():
    assert split_keys(b"\x1b[B\x1b[Bq\x1b\r") == [b"\x1b[B", b"\x1b[B", b"q", b"\x1b", b"\r"]
    assert split_keys(b"\x1b[1;5C\xc3\xa9a") == [b"\x1b[1;5C", b"\xc3\xa9", b"a"]
    assert split_keys(b"") == []


def test_key_stream_yields_each_key_and_quits_at_end_of_input():
    reads = iter([b"\x1b[B\x1b[A", b"x", b""])
    assert list(key_stream(lambda: next(reads))) == ["down", "up", "x", "q"]
    assert list(key_stream(lambda: b"")) == ["q"]


def test_parse_key_without_folding_keeps_case_and_names_end_of_input():
    assert parse_key(b"Q", fold=False) == "Q" and parse_key(b"q", fold=False) == "q"
    assert parse_key(b"", fold=False) == "eof" and parse_key(b"\x04", fold=False) == "eof"
    assert parse_key(b"\x1b", fold=False) == "esc" and parse_key(b"\xc3\xa9", fold=False) == ""
    assert parse_key(b"\x04") == "q"


def test_key_stream_without_folding_ends_with_eof():
    reads = iter([b"Ab", b""])
    assert list(key_stream(lambda: next(reads), fold=False)) == ["A", "b", "eof"]


def test_edit_types_deletes_and_ends_the_prompt():
    assert edit("ab", "C") == ("abC", None)
    assert edit("ab", " ") == ("ab ", None)
    assert edit("ab", "backspace") == ("a", None)
    assert edit("", "backspace") == ("", None)
    assert edit("ab", "enter") == ("ab", "done")
    for key in ("esc", "ctrl-c", "eof"):
        assert edit("ab", key) == ("ab", "cancel")
    for key in ("up", "down", "left", "", "\x00"):
        assert edit("ab", key) == ("ab", None)
