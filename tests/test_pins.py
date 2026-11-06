"""pins.py exact behaviour: the length boundary, the too-many error, directory mode, temp-file naming and sorted JSON."""

import json
import stat
import tempfile

import pytest

from constellation import pins


def test_load_keeps_an_id_of_exactly_the_maximum_length(tmp_path):
    f = tmp_path / "pins.json"
    f.write_text(json.dumps({"version": 1, "pins": {"x" * pins.MAX_ID: "d"}}))
    assert pins.load(f) == {"x" * pins.MAX_ID: "d"}


def test_add_at_the_cap_raises_with_the_exact_message(tmp_path):
    f = tmp_path / "pins.json"
    f.write_text(json.dumps({"version": 1, "pins": {str(n): "d" for n in range(pins.MAX_PINS)}}))
    with pytest.raises(ValueError) as err:
        pins.add(f, "one-more")
    assert str(err.value) == "too many pins"


def test_add_creates_missing_parents_privately(tmp_path):
    f = tmp_path / "a" / "b" / "pins.json"
    assert pins.add(f, "s:x", "2026-01-01") is True
    assert stat.S_IMODE(f.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(f.stat().st_mode) == 0o600


def test_add_writes_sorted_keys(tmp_path):
    f = tmp_path / "pins.json"
    pins.add(f, "s:b", "2026-01-01")
    pins.add(f, "s:a", "2026-01-02")
    assert f.read_text() == '{"pins": {"s:a": "2026-01-02", "s:b": "2026-01-01"}, "version": 1}'


def test_add_makes_its_temp_file_beside_the_pins_file_with_the_pins_prefix(tmp_path, monkeypatch):
    seen = {}
    real = tempfile.mkstemp

    def spy(*args, **kwargs):
        seen["args"], seen["kwargs"] = args, kwargs
        return real(*args, **kwargs)

    monkeypatch.setattr(pins.tempfile, "mkstemp", spy)
    pins.add(tmp_path / "pins.json", "s:a", "2026-01-01")
    assert seen == {"args": (), "kwargs": {"dir": tmp_path, "prefix": ".pins-"}}
