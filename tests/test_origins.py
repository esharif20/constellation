import json

import pytest
from fakes import FakeEmbedder, FakeLLM

from constellation import scan
from constellation.cli import main
from constellation.snapshot import snapshot

PLANT = "sk-ant-PLANTED"


@pytest.fixture(autouse=True)
def quiet(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))  # Path.home() is the invented home the tests build under
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("constellation.cli._local_embedder", lambda: None)


def _skill(root, folder, name=None, extra=""):
    (root / folder).mkdir(parents=True, exist_ok=True)
    (root / folder / "SKILL.md").write_text(f"---\nname: {name or folder}\ndescription: Does {folder} things\n{extra}---\nbody\n")


def _lock(path, skills, **top):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 3, "skills": skills, **top}))
    return path


def _origins(result):
    return {i.name: i.origin for i in result.items}


def _setup(tmp_path):
    """config/skills/pat-one -> agents/skills/pat-one (a symlink, as the skills CLI installs); pat-two likewise; plain is a real folder."""
    config, agents = tmp_path / "home" / ".claude", tmp_path / "home" / ".agents"
    for name in ("pat-one", "pat-two"):
        _skill(agents / "skills", name)
        (config / "skills").mkdir(parents=True, exist_ok=True)
        (config / "skills" / name).symlink_to(agents / "skills" / name)
    _skill(config / "skills", "plain")
    return config, agents / ".skill-lock.json"


def test_origin_is_the_lockfile_source_and_nothing_else_from_the_lockfile(tmp_path):
    config, lock = _setup(tmp_path)
    _lock(lock, {"pat-one": {"source": "pat/skills", "sourceUrl": f"https://x.invalid/{PLANT}", "hash": "h"}}, secret=PLANT)

    result = scan(config, offline=True, lockfile=lock)

    assert _origins(result)["pat-one"] == "pat/skills"
    assert _origins(result)["plain"] is None
    dump = json.dumps(result, default=lambda o: o.__dict__)
    assert PLANT not in dump and "x.invalid" not in dump


def test_lockfile_is_found_by_the_name_of_the_folder_the_link_points_at(tmp_path):
    config, lock = _setup(tmp_path)
    (config / "skills" / "renamed").symlink_to(config.parent / ".agents" / "skills" / "pat-two")
    _lock(lock, {"pat-two": {"source": "pat/two"}})

    assert _origins(scan(config, offline=True, lockfile=lock))["pat-two"] == "pat/two"


@pytest.mark.parametrize(
    "source", ["../../etc", "/abs/path", "a//b", "has space", "a/./b", "pat/ghp_" + "aB3dE5gH" * 4 + "7jK9", 5, None, ["a"]]
)
def test_an_unsafe_or_wrong_typed_source_is_dropped(tmp_path, source):
    config, lock = _setup(tmp_path)
    _lock(lock, {"pat-one": {"source": source}})

    assert _origins(scan(config, offline=True, lockfile=lock))["pat-one"] == "agents"  # no lock origin; falls to the installer name


def test_a_source_of_60_characters_is_kept_and_61_is_dropped_whole_never_truncated(tmp_path):
    config, lock = _setup(tmp_path)
    _lock(lock, {"pat-one": {"source": "a" * 60}, "pat-two": {"source": "a" * 61}})

    got = _origins(scan(config, offline=True, lockfile=lock))

    assert got["pat-one"] == "a" * 60
    assert got["pat-two"] == "agents"


def _crossing_secrets():
    return ["ghp_" + "aB3dE5gH" * 4 + "7jK9", "sk-ant-" + "A1b2C3d4" * 4, "plainsecretvalue"]


@pytest.mark.parametrize("secret", _crossing_secrets())
@pytest.mark.parametrize("lead", [20, 40, 57])
def test_a_secret_crossing_the_cap_leaves_no_fragment(tmp_path, secret, lead):
    config, lock = _setup(tmp_path)
    (config / "settings.json").write_text(json.dumps({"env": {"K": "plainsecretvalue"}}))
    _lock(lock, {"pat-one": {"source": "a" * lead + secret}})

    result = scan(config, offline=True, lockfile=lock)

    assert _origins(result)["pat-one"] == "agents"
    assert secret[:8] not in json.dumps(result, default=lambda o: o.__dict__)


@pytest.mark.parametrize(
    "text", ["not json", "[1]", '{"skills": 3}', '{"skills": {"pat-one": "x"}}', '{"skills": {"pat-one": {"source": {}}}}']
)
def test_an_unknown_lockfile_shape_gives_no_origin_and_no_crash(tmp_path, text):
    config, lock = _setup(tmp_path)
    lock.write_text(text)

    result = scan(config, offline=True, lockfile=lock)

    assert _origins(result)["pat-one"] == "agents"
    assert text.startswith("not json") == any(w == "could not read skill lock: unreadable or not valid JSON" for w in result.warnings)


def test_a_missing_lockfile_is_silent(tmp_path):
    config, lock = _setup(tmp_path)

    result = scan(config, offline=True, lockfile=lock)

    assert not any("skill lock" in w for w in result.warnings)


def test_no_origins_skips_every_origin_and_never_reads_the_lockfile(tmp_path, monkeypatch):
    config, lock = _setup(tmp_path)
    _lock(lock, {"pat-one": {"source": "pat/skills"}})

    def boom(*args):
        raise AssertionError("the lockfile was read")

    monkeypatch.setattr("constellation.claude_code.read_lock", boom)
    result = scan(config, offline=True, lockfile=lock, origins=False)

    assert {i.origin for i in result.items} == {None}


def test_the_conftest_guard_refuses_the_real_agents_folder():
    import os
    import pwd
    from pathlib import Path

    import constellation.origins as origins

    with pytest.raises(AssertionError, match="forbidden"):
        origins.read_lock(Path(pwd.getpwuid(os.getuid()).pw_dir).resolve() / ".agents" / ".skill-lock.json", set())


def test_a_symlinked_skill_with_no_lockfile_falls_back_to_the_installer_folder_name(tmp_path):
    config, lock = _setup(tmp_path)

    assert _origins(scan(config, offline=True, lockfile=lock))["pat-one"] == "agents"


def test_a_symlink_back_into_the_config_dir_has_no_origin(tmp_path):
    config, lock = _setup(tmp_path)
    (config / "skills" / "zalias").symlink_to(config / "skills" / "plain")  # sorts last, so its Item is the one read

    assert _origins(scan(config, offline=True, lockfile=lock)).get("plain") is None


def test_frontmatter_repository_is_the_last_fallback_and_urls_reduce_to_owner_repo(tmp_path):
    config, lock = _setup(tmp_path)
    _skill(lock.parent / "skills", "a", extra="repository: https://github.com/owner/repo.git\n")
    (config / "skills" / "a").symlink_to(lock.parent / "skills" / "a")
    _skill(config / "skills", "b", extra="repo: owner/other\n")
    _skill(config / "skills", "c", extra="repository: 7\n")
    _lock(lock, {"a": {"source": "from/lock"}})

    got = _origins(scan(config, offline=True, lockfile=lock))

    assert got["a"] == "from/lock"  # the lockfile outranks the frontmatter
    assert got["b"] == "owner/other"
    assert got["c"] is None
    lock.unlink()
    assert _origins(scan(config, offline=True, lockfile=lock))["a"] == "agents"  # the installer folder outranks the frontmatter
    _skill(config / "skills", "d", extra="repository: https://github.com/owner/repo.git\n")
    assert _origins(scan(config, offline=True, lockfile=lock))["d"] == "owner/repo"


def test_plugin_contents_and_the_plugin_itself_carry_the_plugin_name_and_synced_skills_say_claude_ai(tmp_path):
    config = tmp_path / "cfg"
    plugin = config / "plugins" / "cache" / "mkt" / "demoplug" / "1.0"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "demoplug", "description": "d"}))
    _skill(plugin / "skills", "inner")
    (plugin / "commands").mkdir()
    (plugin / "commands" / "go.md").write_text("Run it\n")
    _skill(config / "skills" / "synced" / "acct-123-secretid", "cloud")
    _skill(config / "skills", "mine")

    got = _origins(scan(config, offline=True, lockfile=tmp_path / "none.json"))

    assert got == {"demoplug": "demoplug", "inner": "demoplug", "go": "demoplug", "cloud": "claude.ai", "mine": None}
    assert "acct-123" not in json.dumps(got)


def test_agents_use_only_frontmatter(tmp_path):
    config = tmp_path / "cfg"
    (config / "agents").mkdir(parents=True)
    (config / "agents" / "rev.md").write_text("---\nname: rev\ndescription: reviews\nrepo: owner/agents\n---\n")

    assert _origins(scan(config, offline=True, lockfile=tmp_path / "none.json"))["rev"] == "owner/agents"


def test_origin_is_never_sent_to_a_provider(tmp_path):
    config, lock = _setup(tmp_path)
    _lock(lock, {"pat-one": {"source": "marker/ZZORIGIN"}})
    llm, embedder = FakeLLM({}), FakeEmbedder({})

    result = scan(config, llm=llm, embedder=embedder, lockfile=lock, label_cache=tmp_path / "labels.json", verifier=llm)

    assert _origins(result)["pat-one"] == "marker/ZZORIGIN"
    assert llm.prompts and embedder.texts and "ZZORIGIN" not in "\n".join(llm.prompts + embedder.texts)


def test_dry_run_output_contains_no_origin_and_the_summary_line_names_the_file(tmp_path, capsys):
    config, lock = _setup(tmp_path)
    _lock(lock, {"pat-one": {"source": "marker/ZZORIGIN"}})

    code = main(["scan", str(config), "--dry-run", "--skill-lock", str(lock), "--out", str(tmp_path / "o.json")])

    out, err = capsys.readouterr()
    assert code == 0
    assert "ZZORIGIN" not in out + err
    assert f"read origin from {lock} (source field only)" in err


def test_cli_scan_writes_origin_and_no_origins_turns_it_off_and_says_nothing(tmp_path, capsys):
    config, lock = _setup(tmp_path)
    _lock(lock, {"pat-one": {"source": "pat/skills"}})
    out = tmp_path / "o.json"

    assert main(["scan", str(config), "--offline", "--skill-lock", str(lock), "--out", str(out)]) == 0
    assert {i["name"]: i["origin"] for i in json.loads(out.read_text())["items"]}["pat-one"] == "pat/skills"
    assert f"read origin from {lock} (source field only)" in capsys.readouterr().err

    assert main(["scan", str(config), "--offline", "--skill-lock", str(lock), "--no-origins", "--out", str(out)]) == 0
    assert {i["origin"] for i in json.loads(out.read_text())["items"]} == {None}
    assert "read origin" not in capsys.readouterr().err


def test_a_missing_lockfile_prints_no_summary_line(tmp_path, capsys):
    config, _ = _setup(tmp_path)

    main(["scan", str(config), "--offline", "--skill-lock", str(tmp_path / "gone.json"), "--out", str(tmp_path / "o.json")])

    assert "read origin" not in capsys.readouterr().err


def test_the_public_snapshot_drops_origin():
    data = {"items": [{"id": "a", "kind": "skill", "name": "n", "description": "d", "source": "s", "origin": "owner/ZZORIGIN"}]}

    assert "ZZORIGIN" not in json.dumps(snapshot(data)) and "origin" not in snapshot(data)["items"][0]


def test_a_source_equal_to_a_configured_secret_is_dropped(tmp_path):
    config, lock = _setup(tmp_path)
    (config / "settings.json").write_text(json.dumps({"env": {"K": "plainsecretvalue"}}))
    _lock(lock, {"pat-one": {"source": "plainsecretvalue"}})

    assert _origins(scan(config, offline=True, lockfile=lock))["pat-one"] == "agents"


def test_the_lockfile_is_for_skills_not_agents(tmp_path):
    config, lock = _setup(tmp_path)
    (config / "agents").mkdir()
    (config / "agents" / "rev.md").write_text("---\nname: rev\ndescription: reviews\n---\n")
    _lock(lock, {"agents": {"source": "not/for-agents"}, "rev": {"source": "not/for-agents"}})

    assert _origins(scan(config, offline=True, lockfile=lock))["rev"] is None


def test_the_lockfile_is_also_tried_by_the_name_of_the_link(tmp_path):
    config, lock = _setup(tmp_path)
    _skill(lock.parent / "skills", "real")
    (config / "skills" / "alias").symlink_to(lock.parent / "skills" / "real")
    _lock(lock, {"alias": {"source": "by/link"}})

    assert _origins(scan(config, offline=True, lockfile=lock))["real"] == "by/link"


def test_a_link_must_point_at_an_installer_skills_folder_outside_the_config_dir(tmp_path):
    config, lock = _setup(tmp_path)
    for where in (config / "stash", tmp_path / "random"):  # inside the config but not under skills/, and outside but not under skills/
        _skill(where, "odd")
        (config / "skills" / f"link-{where.name}").symlink_to(where / "odd")
    (config / "skills" / "link-stash" / "SKILL.md").write_text("---\nname: l1\ndescription: d\n---\n")
    (config / "skills" / "link-random" / "SKILL.md").write_text("---\nname: l2\ndescription: d\n---\n")

    got = _origins(scan(config, offline=True, lockfile=lock))

    assert got["l1"] is None and got["l2"] is None


def test_the_installer_name_loses_only_its_leading_dots(tmp_path):
    config, lock = _setup(tmp_path)
    _skill(tmp_path / "home" / ".Xpack" / "skills", "thing")
    (config / "skills" / "thing").symlink_to(tmp_path / "home" / ".Xpack" / "skills" / "thing")

    assert _origins(scan(config, offline=True, lockfile=lock))["thing"] == "Xpack"


def test_a_repository_url_loses_only_slashes_and_the_git_suffix(tmp_path):
    config, lock = _setup(tmp_path)
    _skill(config / "skills", "u", extra="repository: https://host.example/Xowner/repoX/\n")

    assert _origins(scan(config, offline=True, lockfile=lock))["u"] == "Xowner/repoX"


def test_a_plain_folder_sharing_a_name_with_a_lock_entry_gets_nothing_from_the_lockfile(tmp_path):
    config, lock = _setup(tmp_path)
    _lock(lock, {"plain": {"source": "not/mine"}})

    assert _origins(scan(config, offline=True, lockfile=lock))["plain"] is None


@pytest.mark.parametrize(
    "source",
    [
        "\u0440at/skills",
        "\uff50at/skills",
        "x-access-token@github.com/o/r",
        ".ssh/id_rsa",
        "Users/eshan/dev/private",
        "a/b/c/d",
        "a@b",
        "@",
    ],
)
def test_lookalike_credential_and_path_shaped_sources_are_dropped(tmp_path, source):
    config, lock = _setup(tmp_path)
    _lock(lock, {"pat-one": {"source": source}})

    assert _origins(scan(config, offline=True, lockfile=lock))["pat-one"] == "agents"


def test_an_npm_scope_prefix_is_allowed(tmp_path):
    config, lock = _setup(tmp_path)
    _lock(lock, {"pat-one": {"source": "@scope/pkg"}})

    assert _origins(scan(config, offline=True, lockfile=lock))["pat-one"] == "@scope/pkg"


def test_the_symlink_fallback_names_only_a_dot_folder_directly_under_home(tmp_path):
    config, lock = _setup(tmp_path)
    home = tmp_path / "home"
    for where in (home / "work" / "acme-internal", home / ".deep" / "er", home):
        _skill(where / "skills", f"s-{where.name}")
        (config / "skills" / f"s-{where.name}").symlink_to(where / "skills" / f"s-{where.name}")

    got = _origins(scan(config, offline=True, lockfile=lock))

    assert [got[n] for n in ("s-acme-internal", "s-er", "s-home")] == [None, None, None]
    assert set(got.values()) <= {None, "agents"}


def test_a_lockfile_nested_past_the_recursion_limit_warns_and_does_not_crash(tmp_path):
    config, lock = _setup(tmp_path)
    lock.write_text("[" * 200000)

    result = scan(config, offline=True, lockfile=lock)

    assert "could not read skill lock: unreadable or not valid JSON" in result.warnings
    assert _origins(result)["pat-one"] == "agents"


def test_a_lockfile_that_cannot_be_read_warns_and_does_not_crash(tmp_path):
    config, lock = _setup(tmp_path)
    lock.mkdir()  # a directory is not a regular file: no warning, no crash
    assert not any("skill lock" in w for w in scan(config, offline=True, lockfile=lock).warnings)
    lock.rmdir()
    lock.write_text("{}")
    lock.chmod(0)
    try:
        result = scan(config, offline=True, lockfile=lock)
    finally:
        lock.chmod(0o600)

    assert "could not read skill lock: unreadable or not valid JSON" in result.warnings


def test_installer_folders_that_are_not_dot_folders_under_home_give_nothing(tmp_path):
    config, lock = _setup(tmp_path)
    for where in (tmp_path / ".Xother", tmp_path / "home" / "plainpack"):  # a dot-folder elsewhere, and a plain folder directly under home
        _skill(where / "skills", f"t-{where.name.strip('.')}")
        (config / "skills" / f"t-{where.name.strip('.')}").symlink_to(where / "skills" / f"t-{where.name.strip('.')}")

    got = _origins(scan(config, offline=True, lockfile=lock))

    assert got["t-Xother"] is None and got["t-plainpack"] is None


def test_a_skills_folder_that_is_itself_a_link_is_not_a_linked_skill(tmp_path):
    config, lock = _setup(tmp_path)
    _skill(lock.parent / "skills", "viafolder")
    (config / "skills").rename(config / "skills-old")
    (config / "skills").symlink_to(lock.parent / "skills")  # the skills dir is the link; each skill folder inside is a real folder
    _lock(lock, {"viafolder": {"source": "no/lock"}})

    assert _origins(scan(config, offline=True, lockfile=lock))["viafolder"] is None
