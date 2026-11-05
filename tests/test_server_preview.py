import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constellation import server
from constellation.cli import main
from constellation.server import create_app

SCAN = {
    "items": [{"id": "a", "kind": "skill", "name": "a", "description": "d", "source": "s"}],
    "relations": [],
    "labels": {},
    "clusters": [],
    "warnings": [],
}
PREVIEW = {
    "version": 1,
    "pack": {"name": "pdf-kit", "layout": "plugin"},
    "items": [{"id": "new:s", "kind": "skill", "name": "trace-canvas", "description": "Draws traces.", "always_on": 12, "estimated": True}],
    "counts": {"skill": 1},
    "always_on": {"counted": 0, "estimated": 12, "unknown": 0},
    "overlaps": [{"new_id": "new:s", "existing_id": "a", "existing_name": "a", "why": "same name"}],
    "already_installed": False,
    "compared": True,
    "note": None,
    "warnings": [],
}
URL = "http://127.0.0.1:8765/api/preview"


@pytest.fixture(autouse=True)
def built_app(tmp_path, monkeypatch):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><html></html>")
    monkeypatch.setattr(server, "STATIC", static)


def client(tmp_path: Path, body: object | None = PREVIEW, raw: bytes | None = None, flag: bool = True) -> TestClient:
    scan = tmp_path / "constellation.json"
    scan.write_text(json.dumps(SCAN))
    file = tmp_path / "preview.json"
    file.write_bytes(raw if raw is not None else json.dumps(body).encode())
    return TestClient(create_app(scan, checklist=tmp_path / "list.md", preview=file if flag else None))


def test_preview_route_serves_file(tmp_path):
    response = client(tmp_path).get(URL)
    shown = {k: v for k, v in PREVIEW.items() if k not in ("counts", "note", "warnings")}
    shown["items"] = [{"id": "new:s", "kind": "skill", "name": "trace-canvas"}]
    assert (response.status_code, response.json()) == (200, shown)


def test_preview_route_404_without_flag_or_bad_file(tmp_path):
    assert client(tmp_path, flag=False).get(URL).status_code == 404
    assert client(tmp_path, raw=b"not json").get(URL).status_code == 404
    assert client(tmp_path, raw=b"\xff\xfe").get(URL).status_code == 404
    c = client(tmp_path)
    (tmp_path / "preview.json").unlink()
    assert c.get(URL).status_code == 404


def test_preview_route_refuses_deep_nesting_and_fifo(tmp_path):
    assert client(tmp_path, raw=b"[" * 200000).get(URL).status_code == 404
    deep = json.dumps(PREVIEW).replace('"counts": {"skill": 1}', '"counts": {"skill": ' + "[" * 200000 + "]" * 200000 + "}")
    assert client(tmp_path, raw=deep.encode()).get(URL).status_code == 404
    c = client(tmp_path)
    (tmp_path / "preview.json").unlink()
    os.mkfifo(tmp_path / "preview.json")
    assert c.get(URL).status_code == 404


def test_preview_route_does_not_serve_descriptions_or_notes(tmp_path):
    body = client(tmp_path).get(URL).text
    assert "Draws traces" not in body and "counts" not in body and "warnings" not in body


def test_preview_route_is_local_only(tmp_path):
    assert client(tmp_path).get(URL, headers={"host": "evil.example:8765"}).status_code == 403


def _with(**change):
    return {**PREVIEW, **change}


def _item(**change):
    return {**PREVIEW["items"][0], **change}


@pytest.mark.parametrize(
    "bad",
    [
        _with(extra=1),
        _with(version=2),
        _with(pack={"name": "x", "layout": "other"}),
        _with(pack={"name": "x" * 81, "layout": "pack"}),
        _with(items=[_item(description="a\x1b[31m")]),
        _with(items=[_item(name="a‮b")]),
        _with(items=[_item(description="d" * 201)]),
        _with(items=[_item(always_on=True)]),
        _with(items=[_item(always_on=-1)]),
        _with(items=[_item(estimated=1)]),
        _with(items=[{**_item(), "body": "x"}]),
        _with(items="nope"),
        _with(overlaps=[{"new_id": "n", "existing_id": "a", "existing_name": "a"}]),
        _with(counts={"skill": "1"}),
        _with(counts={str(n): 1 for n in range(21)}),
        _with(always_on={"counted": 0, "estimated": 0}),
        _with(already_installed="no"),
        _with(note=3),
        _with(warnings=["w"] * 201),
        _with(note="n" * 401),
        [],
    ],
)
def test_preview_route_refuses_bad_shapes(tmp_path, bad):
    assert client(tmp_path, bad).get(URL).status_code == 404


def test_preview_route_edges_are_accepted(tmp_path):
    edge = _with(
        pack={"name": "x" * 80, "layout": "skill"},
        note="n" * 400,
        warnings=["w" * 200] * 200,
        items=[_item(id="i" * 400, description="d" * 200, always_on=None)],
        overlaps=[{"new_id": "n" * 400, "existing_id": "e" * 400, "existing_name": "e" * 80, "why": "w" * 40}],
        counts={str(n): 0 for n in range(20)},
    )
    assert client(tmp_path, edge).get(URL).status_code == 200
    short = {"id": "i", "kind": "k", "name": "n", "description": "", "always_on": 0, "estimated": False}
    assert client(tmp_path, _with(items=[short] * 2000)).get(URL).status_code == 200
    assert client(tmp_path, _with(items=[short] * 2001)).get(URL).status_code == 404
    link = {"new_id": "n", "existing_id": "e", "existing_name": "e", "why": "w"}
    assert client(tmp_path, _with(overlaps=[link] * 2000)).get(URL).status_code == 200
    assert client(tmp_path, _with(overlaps=[link] * 2001)).get(URL).status_code == 404


def test_preview_route_refuses_big_file(tmp_path):
    assert client(tmp_path, raw=b" " * 1_000_001).get(URL).status_code == 404
    assert client(tmp_path, raw=json.dumps(PREVIEW).encode() + b" " * 100).get(URL).status_code == 200


def test_open_passes_preview(tmp_path):
    scan = tmp_path / "constellation.json"
    scan.write_text(json.dumps(SCAN))
    file = tmp_path / "preview.json"
    file.write_text(json.dumps(PREVIEW))
    calls = []
    assert main(["open", str(scan), "--preview", str(file), "--no-browser"], serve=lambda app, port, browser: calls.append(app)) == 0
    assert TestClient(calls[0]).get(URL).json()["pack"] == PREVIEW["pack"]
    assert main(["open", str(scan), "--preview", str(tmp_path / "gone.json")], serve=lambda *a: pytest.fail("must not serve")) == 2
