"""pins.py exact behaviour: limits, file layout, modes, temp-file hygiene."""

import json
import os
from datetime import date
from pathlib import Path

import pytest

from constellation import pins


def test_limits():
    assert (pins.MAX_PINS, pins.MAX_ID) == (5000, 400)


def write(path, pins_obj, version=1):
    path.write_text(json.dumps({"version": version, "pins": pins_obj}))


def test_load_keeps_the_boundaries(tmp_path):
    f = tmp_path / "p.json"
    write(f, {str(n): "d" for n in range(5000)})
    assert len(pins.load(f)) == 5000
    write(f, {str(n): "d" for n in range(5001)})
    assert pins.load(f) == {}
    write(f, {"k" * 400: "d", "k" * 401: "d"})
    assert list(pins.load(f)) == ["k" * 400]
    write(f, {"a": "d"}, version=2)
    assert pins.load(f) == {}
    write(f, {"a": "d"}, version=0)
    assert pins.load(f) == {}
    f.write_text(json.dumps({"pins": {"a": "d"}}))
    assert pins.load(f) == {}
    f.write_text(json.dumps({"version": 1}))
    assert pins.load(f) == {}


def test_load_survives_a_directory_and_absurd_nesting(tmp_path):
    assert pins.load(tmp_path) == {}
    f = tmp_path / "deep.json"
    f.write_text("[" * 200000)
    assert pins.load(f) == {}


def test_add_writes_the_exact_private_file(tmp_path):
    f = tmp_path / "a" / "b" / "pins.json"
    assert pins.add(f, "z", "2026-01-02") is True
    assert pins.add(f, "a", "2026-01-03") is True
    assert f.read_text() == '{"pins": {"a": "2026-01-03", "z": "2026-01-02"}, "version": 1}'
    assert f.stat().st_mode & 0o777 == 0o600 and f.parent.stat().st_mode & 0o777 == 0o700
    assert pins.add(f, "z", "2030-01-01") is False and pins.load(f)["z"] == "2026-01-02"
    assert [p.name for p in f.parent.iterdir()] == ["pins.json"]


def test_add_tightens_an_existing_directory_and_defaults_to_today(tmp_path):
    d = tmp_path / "open"
    d.mkdir(mode=0o755)
    d.chmod(0o755)
    pins.add(d / "pins.json", "x")
    assert d.stat().st_mode & 0o777 == 0o700
    assert pins.load(d / "pins.json") == {"x": date.today().isoformat()}
    pins.add(d / "pins.json", "y", "")
    assert pins.load(d / "pins.json")["y"] == date.today().isoformat()


def test_add_refuses_past_the_cap_without_touching_the_file(tmp_path):
    f = tmp_path / "p.json"
    write(f, {str(n): "d" for n in range(4999)})
    assert pins.add(f, "last") is True
    before = f.read_bytes()
    with pytest.raises(ValueError, match=r"^too many pins$"):
        pins.add(f, "one-more")
    assert f.read_bytes() == before


def test_add_syncs_and_cleans_up_even_on_an_interrupt(tmp_path, monkeypatch):
    synced = []
    real = os.fsync
    monkeypatch.setattr(os, "fsync", lambda fd: (synced.append(fd), real(fd))[1])
    pins.add(tmp_path / "p.json", "a", "d")
    assert len(synced) == 1
    seen = []

    def boom(src, dst):
        seen.append((Path(src), Path(dst)))
        raise KeyboardInterrupt

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(KeyboardInterrupt):
        pins.add(tmp_path / "p.json", "b", "d")
    tmp, dst = seen[0]
    assert tmp.parent == tmp_path and tmp.name.startswith(".pins-") and dst == tmp_path / "p.json"
    assert not tmp.exists() and pins.load(tmp_path / "p.json") == {"a": "d"}
