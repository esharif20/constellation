"""#79: invented secrets must not escape the setup through any public output."""

import json

import pytest
from fakes import FakeEmbedder, write_skill
from fastapi.testclient import TestClient

from constellation import habits, public_export, scan, scan_graph, server
from constellation.cli import main
from constellation.report import render_report

TOKENS = {
    name: "sk-ant-CANARY-" + name + "-0123456789abcdef0123456789"
    for name in ("body", "hook", "env", "header", "url", "project", "transcript", "folder", "plugin", "agent", "command", "credential")
}
TOKENS["env"] = "ZZQ-INVENTED-ENV-SECRET-79"  # exercises known-value redaction, independently of token patterns
BODY_MARKER = "ZZQ-INVENTED-BODY-ONLY-79"
TRANSCRIPT_MARKER = "ZZQ-INVENTED-TRANSCRIPT-ONLY-79"
BASE_URL = "http://127.0.0.1:8765"


def assert_clean(value):
    raw = value if isinstance(value, bytes) else str(value).encode()
    for token in (*TOKENS.values(), BODY_MARKER, TRANSCRIPT_MARKER):
        assert token.encode() not in raw, f"invented canary escaped: {token}"


def put_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


@pytest.fixture
def canary_setup(tmp_path, monkeypatch):
    """Every file and symlink target is invented and lives under pytest's temp root."""
    config = tmp_path / TOKENS["folder"]
    config.mkdir()
    project = tmp_path / ("project-" + TOKENS["project"])
    project.mkdir()
    write_skill(config, "invented", TOKENS["body"] + BODY_MARKER, description="Invented helper " + TOKENS["env"])
    write_skill(config, "invented-copy", TOKENS["body"] + BODY_MARKER)
    write_skill(config, "unused", "Invented distinct unused instructions")
    # Folder names need not equal the skill's public name.
    (config / "skills" / "invented").rename(config / "skills" / TOKENS["folder"])
    (config / "agents").mkdir()
    (config / "agents" / "invented.md").write_text(
        f"---\nname: invented-agent\ndescription: Invented helper\n---\n{TOKENS['agent']}{BODY_MARKER}"
    )
    (config / "commands").mkdir()
    (config / "commands" / "invented.md").write_text("Invented command\n" + TOKENS["command"] + BODY_MARKER)
    (config / "CLAUDE.md").write_text(TOKENS["body"] + BODY_MARKER)
    put_json(config / ".credentials.json", {"invented-auth": TOKENS["credential"]})
    put_json(
        config / "settings.json",
        {
            "env": {"INVENTED_TOKEN": TOKENS["env"]},
            "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo " + TOKENS["hook"] + " " + TOKENS["env"]}]}]},
        },
    )
    remote = {
        "type": "http",
        "url": f"https://demo.invalid/{TOKENS['url']}?token={TOKENS['url']}",
        "headers": {"Authorization": "Bearer " + TOKENS["header"]},
        "env": {"TOKEN": TOKENS["env"]},
    }
    put_json(
        config / ".mcp.json",
        {
            "mcpServers": {
                "invented-remote": remote,
                "invented-stdio": {"command": "invented-never-executed", "args": [TOKENS["env"]], "env": {"TOKEN": TOKENS["env"]}},
            }
        },
    )
    put_json(
        config / ".claude.json",
        {
            "oauth": TOKENS["credential"],
            "mcpServers": {"invented-user": remote},
            "projects": {str(project): {"mcpServers": {"invented-local": remote}}},
        },
    )
    put_json(project / ".mcp.json", {"mcpServers": {"invented-project": remote}})
    write_skill(project / ".claude", "invented-project-skill", TOKENS["project"] + BODY_MARKER)
    plugin = config / "plugins/cache/invented-market/invented-plugin/1"
    put_json(
        plugin / ".claude-plugin/plugin.json",
        {
            "name": "invented-plugin",
            "description": "Invented plugin",
            "private": TOKENS["plugin"],
            "mcpServers": {"invented-plugin-server": remote},
        },
    )
    write_skill(plugin, "invented-plugin-skill", TOKENS["plugin"] + BODY_MARKER)
    put_json(config / "plugins/installed_plugins.json", {"plugins": {"invented-plugin@invented-market": [{"installPath": str(plugin)}]}})
    record = {
        "type": "assistant",
        "timestamp": "2026-11-05T12:00:00Z" + TOKENS["transcript"],
        "cwd": str(project),
        "uuid": TOKENS["transcript"],
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": TOKENS["transcript"],
                    "name": "Skill",
                    "input": {"skill": "invented", "private": TOKENS["transcript"] + TRANSCRIPT_MARKER},
                },
                {"type": "text", "text": TOKENS["transcript"] + TRANSCRIPT_MARKER},
                {"type": "tool_use", "id": "unmatched", "name": "mcp__" + TOKENS["transcript"], "input": {}},
            ]
        },
    }
    transcript = config / "projects" / TOKENS["folder"] / (TOKENS["transcript"] + ".jsonl")
    transcript.parent.mkdir(parents=True)
    transcript.write_text(
        json.dumps(record)
        + "\n"
        + json.dumps(
            {
                "type": "user",
                "uuid": TOKENS["transcript"],
                "timestamp": "2026-11-05T13:00:00Z",
                "message": {"content": TOKENS["transcript"] + TRANSCRIPT_MARKER},
            }
        )
        + "\n"
    )
    static = tmp_path / "invented-build"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text('<html><head><script type="module" src="./assets/app.js"></script></head></html>')
    (static / "assets/app.js").write_text('fetch("api/constellation")')
    monkeypatch.setattr(public_export, "STATIC", static)
    monkeypatch.setattr(server, "STATIC", static)
    # The CLI would otherwise search for a real working-directory .env file.
    monkeypatch.setattr("constellation.cli.load_env", lambda: None)
    return config, project


@pytest.fixture
def canary_scan(canary_setup, tmp_path, capsys):
    config, project = canary_setup
    saved = tmp_path / "scan.json"
    embedder = FakeEmbedder({})  # recording local fake; no model download or network
    assert main(["scan", str(config), "--project", str(project), "--offline", "--no-origins", "--out", str(saved)], embedder=embedder) == 0
    captured = capsys.readouterr()
    return saved, config, captured.out + captured.err, embedder.texts


@pytest.mark.parametrize("surface", ["saved-scan", "report", "checklist", "export", "habits", "checkpoint", "logs", "embedder"])
def test_canary_is_absent_from_each_pipeline_output(canary_scan, tmp_path, capsys, caplog, surface):
    saved, _, scan_logs, embedded = canary_scan
    data = json.loads(saved.read_text())
    # Prove the planted transcript and installed/project Items were actually read.
    assert data["usage"]["claude-code:skill:invented"]["count"] == 1
    assert {"skill", "agent", "command", "plugin", "mcp_server", "hook"} <= {i["kind"] for i in data["items"]}
    assert any(i["scope"] == "project" for i in data["items"])
    if surface == "saved-scan":
        assert_clean(saved.read_bytes())
    elif surface == "report":
        assert_clean(render_report(data, top=50, color=False, width=100, show_all=True))
    elif surface == "checklist":
        out = tmp_path / "checklist.md"
        assert main(["report", str(saved), "--cleanup", str(out)]) == 0
        assert out.is_file()
        assert_clean(out.read_bytes())
    elif surface == "export":
        out = tmp_path / "public"
        assert main(["export", "--public", str(saved), "--out", str(out)]) == 0
        assert (out / "api/constellation").is_file()
        for path in out.rglob("*"):
            if path.is_file():
                assert_clean(path.read_bytes())
    elif surface == "habits":
        assert habits.DEFAULT_CACHE.is_file()
        ledger = json.loads(habits.DEFAULT_CACHE.read_text())
        assert any(record["days"] and record["items"] for record in ledger["setups"].values())
        assert_clean(habits.DEFAULT_CACHE.read_bytes())
    elif surface == "checkpoint":
        # Pause a review so the checkpoint contains live persisted state, not just an empty database.
        assert main(["review", str(saved), "--out", str(tmp_path / "review.md")], decide=lambda _: "q") == 0
        import constellation.review as review

        for db in (scan_graph.DEFAULT_CHECKPOINT, review.DEFAULT_CHECKPOINT):
            assert db.is_file() and db.stat().st_size > 0
            for path in db.parent.glob(db.name + "*"):
                assert_clean(path.read_bytes())
    elif surface == "logs":
        assert_clean(scan_logs)
    else:
        assert embedded
        assert_clean(repr(embedded))
    captured = capsys.readouterr()
    assert_clean(captured.out + captured.err + caplog.text)


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("GET", "/api/constellation", None),
        ("GET", "/api/brief", None),
        ("GET", "/api/lenses", None),
        ("GET", "/api/history", None),
        ("GET", "/api/explain", None),
        ("GET", "/api/explain?public=true", None),
        ("GET", "/api/preview", None),
        ("GET", "/api/search?q=invented", None),
        ("POST", "/api/search", {"q": "invented"}),
        ("POST", "/api/chat", {"question": "What should I remove?"}),
        ("POST", "/api/expand", {"id": "claude-code:mcp_server:invented-stdio"}),
        ("POST", "/api/checklist", "current-row"),
    ],
)
def test_canary_is_absent_from_each_api_reply(canary_scan, tmp_path, caplog, method, path, payload):
    saved, config, _, _ = canary_scan

    async def invented_tools(registration):
        return [("invented-tool", "Invented tool " + TOKENS["env"])]

    with TestClient(
        server.create_app(
            saved, checklist=tmp_path / "api-checklist.md", config_dir=config, embedder=FakeEmbedder({}), expansion_query=invented_tools
        ),
        base_url=BASE_URL,
    ) as client:
        if payload == "current-row":
            summary = client.get("/api/brief").json()
            assert summary["pairs"]["rows"], "the fixture must exercise a successful checklist write"
            payload = {"id": summary["pairs"]["rows"][0]["id"]}
        response = client.request(method, path, json=payload) if method == "POST" else client.get(path)
        assert response.status_code == (404 if path == "/api/preview" else 200)
        assert_clean(response.content)
        assert_clean(caplog.text)
        checklist = tmp_path / "api-checklist.md"
        if checklist.exists():
            assert_clean(checklist.read_bytes())


@pytest.mark.parametrize("surface", ["saved-scan", "api"])
@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="claude_code.py:222 puts raw secret folder paths in warnings; cli.py:416 scrubs only Item descriptions",
)
def test_a_bad_skill_warning_does_not_publish_its_secret_folder(canary_setup, tmp_path, surface):
    config, project = canary_setup
    # A malformed but readable file exercises the warning path, independently of valid setup outputs.
    path = config / "skills" / TOKENS["folder"] / "SKILL.md"
    path.write_text("---\nname: invented\n---\nInvented body")
    saved = tmp_path / "scan.json"
    assert (
        main(["scan", str(config), "--project", str(project), "--offline", "--no-origins", "--out", str(saved)], embedder=FakeEmbedder({}))
        == 0
    )
    if surface == "saved-scan":
        assert_clean(saved.read_bytes())
    else:
        with TestClient(server.create_app(saved, embedder=FakeEmbedder({})), base_url=BASE_URL) as client:
            response = client.get("/api/constellation")
            assert response.status_code == 200
            assert_clean(response.content)


def test_an_interrupted_scan_checkpoint_has_no_body_or_secret(canary_setup, tmp_path):
    config, project = canary_setup
    checkpoint = tmp_path / "interrupted.sqlite"

    def interrupt_after_a_label(line):
        raise KeyboardInterrupt

    # Canned local callable only; no SDK, key, network, model, server or MCP process is used.
    with pytest.raises(KeyboardInterrupt):
        scan(
            config,
            llm=lambda _: "invented-purpose",
            origins=False,
            project=project,
            checkpoint=checkpoint,
            on_progress=interrupt_after_a_label,
        )
    assert checkpoint.is_file() and checkpoint.stat().st_size > 0
    for path in checkpoint.parent.glob(checkpoint.name + "*"):
        assert_clean(path.read_bytes())


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="cli.py:416 redacts Item descriptions but writes raw secret names and ids")
def test_a_secret_in_a_skill_name_does_not_reach_the_saved_scan(canary_setup, tmp_path):
    config, _ = canary_setup
    path = config / "skills" / TOKENS["folder"] / "SKILL.md"
    path.write_text(f"---\nname: {TOKENS['credential']}\ndescription: Invented helper\n---\nInvented body")
    saved = tmp_path / "scan.json"
    assert main(["scan", str(config), "--offline", "--no-origins", "--out", str(saved)], embedder=FakeEmbedder({})) == 0
    assert_clean(saved.read_bytes())
