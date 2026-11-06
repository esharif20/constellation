"""Privacy-review fixes: redacted brief reasons, a small pin body, a tightened pins directory, NaN token costs."""

import json
import stat
from dataclasses import replace

from fastapi.testclient import TestClient
from test_assessment import BASE, scan
from test_brief_groups import _setup

from constellation import assessment, pins, server
from constellation.brief import build_brief
from constellation.redact import redact
from constellation.verdict_types import Reason

SECRET = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789"


def test_brief_reasons_are_redacted_like_the_assessments():
    data, assessments, evidence, _ = _setup()
    first = next(iter(assessments))
    assessments[first] = replace(assessments[first], group="safe", action="remove", reasons=(Reason("never_seen", f"uses {SECRET}"),))
    got = build_brief(data, assessments, evidence)
    row = next(r for r in got["safe"]["rows"] if first in r["item_ids"])
    assert SECRET not in json.dumps(got)
    assert row["reasons"] == [{"code": "never_seen", "text": redact(f"uses {SECRET}")}]
    assert row["reason"].endswith(redact(f"uses {SECRET}"))


def test_a_hostile_name_is_cleaned_in_the_brief_reason():
    data, assessments, evidence, _ = _setup()
    first = next(iter(assessments))
    for i in data["items"]:
        if i["id"] == first:
            i["name"] = "bad\nname"
    assessments[first] = replace(assessments[first], group="safe", action="remove")
    row = next(r for r in build_brief(data, assessments, evidence)["safe"]["rows"] if first in r["item_ids"])
    assert row["reason"].startswith("bad name (")


def test_nan_and_infinite_token_costs_are_unknown():
    data = scan()
    data["costs"] = {
        "s:a": {"always_on": float("nan")},
        "s:b": {"always_on": float("inf")},
        "claude-code:mcp_server:user/search": {"always_on": True},
        "claude-code:mcp_server:local/1/search": {"always_on": "9"},
        "h:1": {"always_on": 12.5},
    }
    keys = assessment._keys(data["items"])
    got = {i["id"]: i["always_on"] for i in assessment.adapt(data, keys)["items"]}
    assert got == {
        "s:a": None,
        "s:b": None,
        "claude-code:mcp_server:user/search": None,
        "claude-code:mcp_server:local/1/search": None,
        "h:1": 12.5,
    }
    assert assessment._tokens(7) == 7


def test_pin_body_is_capped_and_the_pins_directory_is_tightened(tmp_path, monkeypatch):
    path = tmp_path / "scan.json"
    path.write_text(json.dumps(scan()))
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html></html>")
    monkeypatch.setattr(server, "STATIC", static)
    private = tmp_path / "private"
    private.mkdir(mode=0o755)
    private.chmod(0o755)
    client = TestClient(server.create_app(path, checklist=tmp_path / "c.md", pins=private / "pins.json"), base_url=BASE)
    big = client.post("/api/pin", content=b'{"id":"' + b"x" * 3000 + b'"}', headers={"content-type": "application/json"})
    assert big.status_code == 413 and big.json() == {"detail": "Pin request exceeds 2048 bytes"}
    chunked = client.post("/api/pin", content=iter([b'{"id":"s:a"}']), headers={"content-type": "application/json"})
    assert chunked.status_code == 411 and "chunked pin requests" in chunked.json()["detail"]
    bad = client.post("/api/pin", content=b"{}", headers={"content-type": "application/json", "content-length": "x"})
    assert bad.status_code == 400
    assert client.post("/api/pin", json={"id": "s:a"}).json() == {"pinned": True, "added": True}
    assert stat.S_IMODE(private.stat().st_mode) == 0o700
    assert list(pins.load(private / "pins.json")) == ["s:a"]
