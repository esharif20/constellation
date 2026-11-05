import json
import os

import pytest
from fakes import FakeEmbedder

from constellation import scan
from constellation.claude_code import read_items, read_secrets
from constellation.cli import main


def _t(*parts: str) -> str:
    return "".join(parts)


SECRET = _t("ghp_", "aB3dE5gH" * 4, "7jK9")
SECRET2 = _t("ghp_", "zY8xW6vU" * 4, "1qP3")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()


def _skill(root, name, description="Does a thing", scope_dir="skills"):
    (root / scope_dir / name).mkdir(parents=True)
    (root / scope_dir / name / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n---\nbody\n")


@pytest.fixture
def repo(tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    _skill(cfg, "gskill")
    repo = tmp_path / "repo-zzclient"
    claude = repo / ".claude"
    _skill(claude, "x", "Project skill")
    (claude / "agents").mkdir()
    (claude / "agents" / "y.md").write_text("---\nname: y\ndescription: Project agent\n---\nbody\n")
    (claude / "commands").mkdir()
    (claude / "commands" / "z.md").write_text("---\ndescription:\n---\n")
    (claude / "settings.json").write_text(
        json.dumps(
            {
                "env": {"TOKEN": SECRET},
                "hooks": {"Stop": [{"hooks": [{"type": "command", "command": f"echo {SECRET2}"}, {"type": "command"}]}]},
            }
        )
    )
    (repo / ".mcp.json").write_text(json.dumps({"mcpServers": {"db": {"command": "npx", "env": {"K": SECRET}}}}))
    _skill(claude, "bad")
    (claude / "skills" / "bad" / "SKILL.md").write_text("no frontmatter here\n")
    outside = tmp_path / "outside"
    _skill(outside, "evil")
    (claude / "skills" / "link").symlink_to(outside / "skills" / "evil")
    return cfg, repo


def test_project_items_have_scope_and_pathless_ids(repo):
    cfg, project = repo
    items, warnings, _, bodies = read_items(cfg, None, project)
    by_id = {i.id: i for i in items}
    assert by_id["claude-code:skill:gskill"].scope == "global"
    for id_ in (
        "claude-code:skill:project/x",
        "claude-code:agent:project/y",
        "claude-code:mcp_server:project/db",
    ):
        assert by_id[id_].scope == "project"
    assert any(i.kind == "hook" and i.scope == "project" for i in items)
    assert "claude-code:skill:project/x" in bodies
    assert not any(str(project) in i.id or "zzclient" in i.id for i in items)


def test_no_project_means_no_project_items(repo):
    cfg, _ = repo
    assert all(i.scope == "global" for i in read_items(cfg)[0])


def test_warnings_use_placeholder_never_a_path(repo, tmp_path):
    cfg, project = repo
    warnings = read_items(cfg, None, project)[1]
    text = "\n".join(warnings)
    assert "<project>/.claude/skills/bad/SKILL.md" in text
    assert "<project>/.claude/commands/z.md" in text
    assert "symlink pointing outside" in text
    assert "it has no command" in text
    assert str(tmp_path) not in text and "zzclient" not in text


def test_warning_under_home_uses_placeholder_too(tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    project = tmp_path / "home" / "proj-home"
    _skill(project / ".claude", "bad")
    (project / ".claude" / "skills" / "bad" / "SKILL.md").write_text("nothing\n")
    text = "\n".join(read_items(cfg, None, project)[1])
    assert "<project>/.claude/skills/bad/SKILL.md" in text
    assert "proj-home" not in text


def test_secrets_from_project_files_are_redacted_everywhere(repo, tmp_path):
    cfg, project = repo
    assert {SECRET, SECRET2} - read_secrets(cfg, project) == {SECRET2}  # SECRET2 is in a command, not an env value
    assert SECRET not in read_secrets(cfg) and SECRET in read_secrets(cfg, project)
    out = tmp_path / "out.json"
    assert main(["scan", str(cfg), "--project", str(project), "--out", str(out), "--no-usage", "--offline"], embedder=FakeEmbedder({})) == 0
    data = out.read_text()
    assert SECRET not in data and str(tmp_path) not in data and "zzclient" not in data
    assert json.loads(data)["current_project"] is None


def test_scan_threads_project_to_items(repo):
    cfg, project = repo
    result = scan(cfg, embedder=FakeEmbedder({}), offline=True, usage=False, origins=False, project=project)
    assert {i.id for i in result.items if i.scope == "project"} >= {"claude-code:skill:project/x"}


def test_project_must_be_a_directory(repo, tmp_path, capsys):
    cfg, _ = repo
    file = tmp_path / "afile"
    file.write_text("x")
    assert main(["scan", str(cfg), "--project", str(file), "--offline"]) == 2
    assert capsys.readouterr().err == "--project must be a directory.\n"


def test_local_servers_are_project_scope(tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / ".claude.json").write_text(json.dumps({"projects": {"/a": {"mcpServers": {"s": {"command": "c"}}}}}))
    by_id = {i.id: i for i in read_items(cfg)[0]}
    assert by_id["claude-code:mcp_server:local/1/s"].scope == "project"
    assert by_id["claude-code:mcp_server:local/1/s"].project is None


def test_hook_without_command_is_skipped_with_fixed_warning(tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "settings.json").write_text(
        json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command"}, {"type": "command", "command": 5}]}]}})
    )
    items, warnings, _, _ = read_items(cfg)
    assert [i for i in items if i.kind == "hook"] == []
    assert warnings == ["skipped a hook in config/settings.json: it has no command"] * 2


def test_bad_hooks_json_is_a_warning_not_a_crash(tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "hooks").mkdir()
    (cfg / "hooks" / "hooks.json").write_text("{nope")
    assert "could not read config/hooks.json: unreadable or not valid JSON" in read_items(cfg)[1]


def test_malformed_project_settings_do_not_break_secrets(tmp_path):
    cfg = tmp_path / "cfg"
    project = tmp_path / "p"
    (project / ".claude").mkdir(parents=True)
    cfg.mkdir()
    (project / ".claude" / "settings.json").write_text("{nope")
    assert read_secrets(cfg, project) == set()


def test_symlinked_claude_dir_or_mcp_file_out_of_the_repo_is_refused(tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    outside = tmp_path / "outside"
    _skill(outside, "evil")
    (outside / ".mcp.json").write_text(json.dumps({"mcpServers": {"evil": {"command": "c"}}}))
    project = tmp_path / "proj"
    project.mkdir()
    os.symlink(outside, project / ".claude")
    os.symlink(outside / ".mcp.json", project / ".mcp.json")
    items, warnings, _, _ = read_items(cfg, None, project)
    assert items == []
    assert warnings == [
        "skipped .claude in project: it is a symlink pointing outside it",
        "skipped .mcp.json in project: it is a symlink pointing outside it",
    ]


def test_symlinked_settings_out_of_the_repo_is_refused(tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    project = tmp_path / "proj"
    (project / ".claude").mkdir(parents=True)
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "x"}]}]}}))
    (project / ".claude" / "settings.json").symlink_to(other)
    items, warnings, _, _ = read_items(cfg, None, project)
    assert items == [] and warnings == ["skipped settings.json in project: it is a symlink pointing outside it"]


def test_bad_project_mcp_json_warns_without_path(tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    project = tmp_path / "proj"
    project.mkdir()
    (project / ".mcp.json").write_text("{nope")
    assert read_items(cfg, None, project)[1] == ["could not read project/.mcp.json: unreadable or not valid JSON"]
