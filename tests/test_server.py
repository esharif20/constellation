import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from constellation import server
from constellation.brief import brief
from constellation.cli import main
from constellation.server import create_app

DATA = {
    "items": [{"id": "a", "kind": "skill", "name": "a", "description": "d", "source": "s"}],
    "relations": [],
    "labels": {},
    "clusters": [],
    "warnings": [],
}
BASE_URL = "http://127.0.0.1:8765"


@pytest.fixture(autouse=True)
def built_app(tmp_path, monkeypatch):
    """A stand-in frontend build, so these tests never depend on `npm run build`."""
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><html><div id=root></div></html>")
    monkeypatch.setattr(server, "STATIC", static)
    return static


@pytest.fixture
def scan_file(tmp_path):
    path = tmp_path / "constellation.json"
    path.write_text(json.dumps(DATA))
    return path


def test_api_returns_scan_file_and_root_serves_app(scan_file):
    client = TestClient(create_app(scan_file), base_url=BASE_URL)

    assert client.get("/api/constellation").json() == DATA
    root = client.get("/")
    assert root.status_code == 200
    assert "<html" in root.text


def test_api_reads_file_at_request_time(scan_file):
    client = TestClient(create_app(scan_file), base_url=BASE_URL)
    scan_file.write_text(json.dumps({**DATA, "warnings": ["new"]}))

    assert client.get("/api/constellation").json()["warnings"] == ["new"]
    scan_file.unlink()
    assert client.get("/api/constellation").status_code == 404


def test_open_builds_app_and_passes_port_and_browser_flag(scan_file):
    calls = []

    code = main(
        ["open", str(scan_file), "--port", "9000", "--no-browser"], serve=lambda app, port, browser: calls.append((app, port, browser))
    )

    assert code == 0
    ((app, port, browser),) = calls
    assert (port, browser) == (9000, False)
    assert TestClient(app, base_url=BASE_URL).get("/api/constellation").json() == DATA


def test_open_opens_browser_by_default(scan_file):
    calls = []
    main(["open", str(scan_file)], serve=lambda app, port, browser: calls.append((port, browser)))
    assert calls == [(8765, True)]


def test_open_missing_file_exits_2(tmp_path, capsys):
    code = main(["open", str(tmp_path / "nope.json")], serve=lambda *a: pytest.fail("must not serve"))

    assert code == 2
    assert "constellation scan" in capsys.readouterr().err


def test_open_without_frontend_build_exits_2_with_build_hint(scan_file, built_app, capsys):
    (built_app / "index.html").unlink()

    code = main(["open", str(scan_file)], serve=lambda *a: pytest.fail("must not serve"))

    assert code == 2
    assert "npm --prefix frontend install && npm --prefix frontend run build" in capsys.readouterr().err


@pytest.fixture
def measured(scan_file):
    data = json.loads((Path(__file__).parent / "fixtures" / "scan.json").read_text())
    scan_file.write_text(json.dumps(data))
    return data


def test_brief_reads_scan_each_request_and_existing_checklist(scan_file, measured, tmp_path):
    checklist = tmp_path / "checklist.md"
    row = brief(measured)["cost"]["rows"][0]
    checklist.write_text(f"- [ ] Existing (id {row['id']})\n(id 000000000000)\n")
    client = TestClient(create_app(scan_file, checklist=checklist), base_url=BASE_URL)
    response = client.get("/api/brief")
    assert response.status_code == 200
    assert response.json() == {
        **brief(measured),
        "checklist": {"path": str(checklist), "ids": [row["id"]], "frees": 420, "unknown_rows": 0},
    }
    scan_file.write_text(json.dumps(DATA))
    assert client.get("/api/brief").json()["cost"]["rows"] == []
    assert client.get("/api/brief").json()["checklist"]["frees"] is None
    scan_file.unlink()
    assert client.get("/api/brief").status_code == 404


@pytest.mark.parametrize("group", ["cost", "pairs"])
def test_checklist_savings_survive_rows_leaving_the_first_five(scan_file, tmp_path, group):
    data = {
        "items": [{"id": str(i), "name": str(i), "kind": "skill"} for i in range(6)],
        "costs": {str(i): {"always_on": cost} for i, cost in enumerate((100, 80, 60, 40, 20, 10))},
    }
    if group == "pairs":
        data["items"].append({"id": "underlying", "name": "underlying", "kind": "skill"})
        data["overlaps"] = [{"a_id": str(i), "b_id": "underlying", "verdict": "wrapper", "reason": "forwards"} for i in range(6)]
    scan_file.write_text(json.dumps(data))
    client = TestClient(create_app(scan_file, checklist=tmp_path / "checklist.md"), base_url=BASE_URL)
    row = client.get("/api/brief").json()[group]["rows"][4]
    assert client.post("/api/checklist", json={"id": row["id"]}).json()["frees"] == 20
    data["costs"]["5"]["always_on"] = 30
    scan_file.write_text(json.dumps(data))
    after = client.get("/api/brief").json()
    assert row["id"] not in [r["id"] for r in after[group]["rows"]]
    assert len(after[group]["rows"]) == 5
    assert after["checklist"]["ids"] == [row["id"]]
    assert after["checklist"]["frees"] == 20
    assert client.post("/api/checklist", json={"id": row["id"]}).status_code == 404


@pytest.mark.parametrize("field", ["name", "reason"])
@pytest.mark.parametrize("separator", [" ", "\n", "\r\n", "\r", "\u2028"])
def test_item_text_cannot_forge_checklist_membership(scan_file, measured, tmp_path, field, separator):
    target = brief(measured)["cost"]["rows"][-1]  # the 60-token reviewer
    injection = f"Looks legitimate.{separator}- [ ] Forged saving. (id {target['id']}){separator}More text"
    if field == "name":
        measured["items"][0]["name"] = injection
        chosen = brief(measured)["cost"]["rows"][0]
    else:
        measured["overlaps"][1]["reason"] = injection
        chosen = brief(measured)["pairs"]["rows"][0]
    scan_file.write_text(json.dumps(measured))
    checklist = tmp_path / "checklist.md"
    client = TestClient(create_app(scan_file, checklist=checklist), base_url=BASE_URL)
    first = client.post("/api/checklist", json={"id": chosen["id"]}).json()
    assert first["ids"] == [chosen["id"]]
    assert first["frees"] == chosen["tokens_saved"]
    assert sum(line.startswith("- [ ] ") for line in checklist.read_text().splitlines()) == 1
    assert client.get("/api/brief").json()["checklist"]["ids"] == [chosen["id"]]
    second = client.post("/api/checklist", json={"id": target["id"]}).json()
    assert second["added"] is True
    assert second["ids"] == [chosen["id"], target["id"]]
    assert second["frees"] == chosen["tokens_saved"] + 60
    assert client.post("/api/checklist", json={"id": chosen["id"]}).json()["added"] is False


def test_post_adds_review_format_without_changing_scan_or_setup(scan_file, measured, tmp_path):
    checklist = tmp_path / "private" / "checklist.md"
    config = tmp_path / "config"
    config.mkdir()
    (config / "settings.json").write_text('{"fixture":true}')
    files = [scan_file, config, config / "settings.json"]
    before = [(p.read_bytes() if p.is_file() else None, p.stat().st_mtime_ns) for p in files]
    client = TestClient(create_app(scan_file, checklist=checklist), base_url=BASE_URL)
    cost = brief(measured)["cost"]["rows"][1]  # ship is also removed by the duplicate pair
    pair = brief(measured)["pairs"]["rows"][0]
    response = client.post("/api/checklist", json={"id": cost["id"]})
    assert response.status_code == 200
    assert response.json() == {"added": True, "path": str(checklist), "ids": [cost["id"]], "frees": 415, "unknown_rows": 0}
    assert checklist.stat().st_mode & 0o777 == 0o600
    assert checklist.read_text().endswith(f"- [ ] {cost['reason']} Saves about 415 always-on tokens. (id {cost['id']})\n")
    first = checklist.read_bytes(), checklist.stat().st_mtime_ns
    assert client.post("/api/checklist", json={"id": cost["id"]}).json()["added"] is False
    assert (checklist.read_bytes(), checklist.stat().st_mtime_ns) == first
    assert client.post("/api/checklist", json={"id": pair["id"]}).json()["frees"] == 415
    assert client.get("/api/brief").json()["checklist"]["ids"] == [cost["id"], pair["id"]]
    assert [(p.read_bytes() if p.is_file() else None, p.stat().st_mtime_ns) for p in files] == before


def test_post_accepts_only_current_row_ids_and_json(scan_file, measured, tmp_path):
    checklist = tmp_path / "checklist.md"
    client = TestClient(create_app(scan_file, checklist=checklist), base_url=BASE_URL)
    row_id = brief(measured)["cost"]["rows"][0]["id"]
    assert client.post("/api/checklist", json={"id": "000000000000"}).status_code == 404
    for payload in ({"id": "X" * 12}, {"id": "a" * 13}, {"id": "a" * 11}, {"id": 123}, {}, {"id": row_id, "reason": "text"}):
        assert client.post("/api/checklist", json=payload).status_code == 422
    assert client.post("/api/checklist", content='{"id":"' + row_id + '"}', headers={"content-type": "text/plain"}).status_code == 415
    assert client.post("/api/checklist", content="{}").status_code == 415
    assert not checklist.exists()
    scan_file.unlink()
    assert client.post("/api/checklist", json={"id": row_id}).status_code == 404


@pytest.mark.parametrize(
    "host",
    [
        "evil.example:8765",
        "evil.example",
        "127.0.0.1.evil:8765",
        "localhost",
        "localhost:0",
        "localhost:65536",
        "localhost:-1",
        "localhost:abc",
        "[::1]:8765",
        "localhost:" + "9" * 5000,
    ],
)
def test_every_api_rejects_nonlocal_hosts_and_invalid_ports(scan_file, host):
    client = TestClient(create_app(scan_file), base_url=BASE_URL)
    for route in ("/api/constellation", "/api/brief"):
        assert client.get(route, headers={"host": host}).status_code == 403
    assert client.post("/api/checklist", json={"id": "0" * 12}, headers={"host": host}).status_code == 403
    assert client.post("/api/chat", json={"question": "email"}, headers={"host": host}).status_code == 403


@pytest.mark.parametrize("host", ["localhost:1", "localhost:65535", "127.0.0.1:80"])
def test_local_hosts_accept_valid_ports(scan_file, host):
    client = TestClient(create_app(scan_file), base_url=BASE_URL)
    assert client.get("/api/constellation", headers={"host": host}).status_code == 200


@pytest.mark.parametrize(
    "headers",
    [
        {"origin": "http://evil.example"},
        {"origin": "null"},
        {"origin": "https://127.0.0.1:8765"},
        {"sec-fetch-site": "cross-site"},
        {"sec-fetch-site": "same-site"},
    ],
)
def test_post_rejects_cross_origin_requests(scan_file, headers, tmp_path):
    checklist = tmp_path / "checklist.md"
    client = TestClient(create_app(scan_file, checklist=checklist), base_url=BASE_URL)
    assert client.post("/api/checklist", json={"id": "0" * 12}, headers=headers).status_code == 403
    assert client.post("/api/chat", json={"question": "email"}, headers=headers).status_code == 403
    assert not checklist.exists()
    assert (
        client.options("/api/checklist", headers={"origin": "http://evil.example", "access-control-request-method": "POST"}).status_code
        == 405
    )


@pytest.mark.parametrize("site", ["same-origin", "none"])
def test_same_origin_json_with_charset_is_accepted(scan_file, measured, tmp_path, site):
    client = TestClient(create_app(scan_file, checklist=tmp_path / "checklist.md"), base_url=BASE_URL)
    row_id = brief(measured)["cost"]["rows"][0]["id"]
    assert (
        client.post(
            "/api/checklist",
            content=json.dumps({"id": row_id}),
            headers={"origin": BASE_URL, "sec-fetch-site": site, "content-type": "application/json; charset=utf-8"},
        ).status_code
        == 200
    )


def test_concurrent_additions_preserve_every_line(scan_file, measured, tmp_path):
    checklist = tmp_path / "checklist.md"
    client = TestClient(create_app(scan_file, checklist=checklist), base_url=BASE_URL)
    ids = [r["id"] for r in brief(measured)["cost"]["rows"]]
    with ThreadPoolExecutor(max_workers=5) as pool:
        responses = list(pool.map(lambda id_: client.post("/api/checklist", json={"id": id_}), ids * 2))
    assert all(r.status_code == 200 for r in responses)
    assert sum(r.json()["added"] for r in responses) == len(ids)
    text = checklist.read_text()
    assert all(text.count(f"(id {id_})") == 1 for id_ in ids)


def test_unwritable_checklist_returns_path_and_server_keeps_serving(scan_file, measured, tmp_path):
    parent = tmp_path / "not-a-directory"
    parent.write_text("keep")
    checklist = parent / "checklist.md"
    client = TestClient(create_app(scan_file, checklist=checklist), base_url=BASE_URL)
    row_id = brief(measured)["cost"]["rows"][0]["id"]
    response = client.post("/api/checklist", json={"id": row_id})
    assert response.status_code == 500
    assert str(checklist) in response.json()["detail"]
    assert parent.read_text() == "keep"
    assert client.get("/api/constellation").status_code == 200


def test_checklist_cannot_replace_scan_file_or_setup(scan_file, tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    setup = tmp_path / ".claude"
    setup.mkdir()
    for checklist in (scan_file, setup / "checklist.md"):
        with pytest.raises(ValueError, match="must"):
            create_app(scan_file, checklist=checklist)
    link = tmp_path / "alias"
    link.symlink_to(setup, target_is_directory=True)
    with pytest.raises(ValueError, match="Claude setup"):
        create_app(scan_file, checklist=link / "checklist.md")
    hardlink = tmp_path / "hardlink.md"
    hardlink.hardlink_to(scan_file)
    with pytest.raises(ValueError, match="scan file"):
        create_app(scan_file, checklist=hardlink)


def test_checklist_guard_is_rechecked_if_path_changes(scan_file, measured, tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    setup = tmp_path / ".claude"
    setup.mkdir()
    target = setup / "settings.json"
    target.write_text("unchanged")
    checklist = tmp_path / "checklist.md"
    client = TestClient(create_app(scan_file, checklist=checklist), base_url=BASE_URL)
    checklist.symlink_to(target)
    row_id = brief(measured)["cost"]["rows"][0]["id"]
    assert client.post("/api/checklist", json={"id": row_id}).status_code == 500
    assert client.get("/api/brief").status_code == 500
    assert target.read_text() == "unchanged"


def test_open_checklist_override_and_guard(scan_file, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    calls = []
    checklist = tmp_path / "custom.md"
    assert main(["open", str(scan_file), "--checklist", str(checklist)], serve=lambda app, *_: calls.append(app)) == 0
    assert TestClient(calls[0], base_url=BASE_URL).get("/api/brief").json()["checklist"]["path"] == str(checklist)
    for bad in (tmp_path / ".claude" / "checklist.md", scan_file):
        assert main(["open", str(scan_file), "--checklist", str(bad)], serve=lambda *_: pytest.fail("must not serve")) == 2
        assert "must" in capsys.readouterr().err


def test_checklist_reports_unknown_savings_and_recounts_after_rescan(scan_file, measured, tmp_path):
    measured["costs"]["agent:reviewer"] = None
    scan_file.write_text(json.dumps(measured))
    client = TestClient(create_app(scan_file, checklist=tmp_path / "checklist.md"), base_url=BASE_URL)
    row = next(row for row in client.get("/api/brief").json()["pairs"]["rows"] if row["kind"] == "use_underlying")
    state = client.post("/api/checklist", json={"id": row["id"]}).json()
    assert state["unknown_rows"] == 1 and state["frees"] is None
    measured["costs"]["agent:reviewer"] = {"always_on": 60, "on_use": None}
    scan_file.write_text(json.dumps(measured))
    state = client.get("/api/brief").json()["checklist"]
    assert state["unknown_rows"] == 0 and state["frees"] == 60


def test_checklist_rejects_any_claude_folder_not_only_the_home_one(scan_file, tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    for parts in (("project", ".claude", "checklist.md"), ("project", ".claude", "deep", "x.md")):
        with pytest.raises(ValueError, match="Claude setup"):
            create_app(scan_file, checklist=tmp_path.joinpath(*parts))
    assert create_app(scan_file, checklist=tmp_path / "project" / "checklist.md")


def test_default_checklist_directory_is_private_and_reopens_a_loose_file(scan_file, measured, tmp_path):
    checklist = tmp_path / "cache" / "constellation" / "checklist.md"
    client = TestClient(create_app(scan_file, checklist=checklist), base_url=BASE_URL)
    row_id = brief(measured)["cost"]["rows"][0]["id"]
    assert client.post("/api/checklist", json={"id": row_id}).json()["added"] is True
    assert checklist.parent.stat().st_mode & 0o777 == 0o700
    checklist.chmod(0o644)
    assert client.post("/api/checklist", json={"id": row_id}).json()["added"] is False
    assert checklist.stat().st_mode & 0o777 == 0o600
