import pytest

from constellation.keys import Action, key_stream, parse_key, split_keys


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
        (b"\x1b[D", ""),
        (b"\x80", ""),
        (b"\xff", ""),
        (b"ab", ""),
        (b"\x7f", "\x7f"),
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
