"""Exact secret collection: every source in, nothing else in (invented values only)."""

import json
from pathlib import Path

from constellation.claude_code import (
    _env_values,
    _mcp_env,
    _quiet_json,
    _strings,
    pack_secrets,
    read_secrets,
)


def put(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data))
    return path


def test_strings_yields_every_string_at_any_depth_and_nothing_else():
    node = {"a": "s1", "b": ["s2", {"c": "s3", "n": 5, "t": True, "z": None}, [["s4"]]], "d": 1.5}
    assert sorted(_strings(node)) == ["s1", "s2", "s3", "s4"]
    assert list(_strings("top")) == ["top"]
    assert list(_strings(7)) == []
    assert list(_strings({})) == [] and list(_strings([])) == []


def test_strings_survives_hostile_nesting():
    deep: object = "bottom"
    for _ in range(5000):
        deep = [deep]
    assert list(_strings(deep)) == ["bottom"]


def test_quiet_json(tmp_path):
    assert _quiet_json(tmp_path / "missing.json") == {}
    assert _quiet_json(put(tmp_path / "ok.json", {"k": 1})) == {"k": 1}
    assert _quiet_json(put(tmp_path / "bad.json", "{nope")) == {}
    assert _quiet_json(put(tmp_path / "list.json", ["x"])) == {}
    assert _quiet_json(put(tmp_path / "list2.json", ["x"]), only_object=False) == ["x"]
    assert _quiet_json(put(tmp_path / "deep.json", "[" * 100000 + "]" * 100000)) == {}
    assert _quiet_json(tmp_path) == {}  # a directory is unreadable, not an error


def test_mcp_env_collects_only_env_strings(tmp_path):
    mcp = put(
        tmp_path / ".mcp.json",
        {
            "mcpServers": {
                "a": {"env": {"K": "env-secret-a"}, "command": "cmd-not-secret"},
                "b": {"args": ["arg-not-secret"]},
                "c": {"env": {"N": {"deep": "env-secret-c"}}},
            }
        },
    )
    assert sorted(_mcp_env(mcp)) == ["env-secret-a", "env-secret-c"]
    assert _mcp_env(tmp_path / "none.json") == []
    assert _mcp_env(put(tmp_path / "bad.json", "{x")) == []
    assert _mcp_env(put(tmp_path / "nolist.json", {"mcpServers": {"a": "not-a-dict"}})) == []
    assert _mcp_env(put(tmp_path / "other.json", {"servers": {"a": {"env": {"K": "x"}}}})) == []


def test_env_values_joins_settings_env_then_mcp_env(tmp_path):
    settings = put(tmp_path / "settings.json", {"env": {"A": "settings-env"}, "other": "not-env"})
    mcp = put(tmp_path / ".mcp.json", {"mcpServers": {"s": {"env": {"B": "mcp-env"}}}})
    assert _env_values(settings, mcp) == ["settings-env", "mcp-env"]
    assert _env_values(tmp_path / "x.json", tmp_path / "y.json") == []


def test_read_secrets_collects_each_source_and_ignores_the_rest(tmp_path, monkeypatch):
    monkeypatch.setenv("PROCESS_ENV_VAR", "process-env-value")
    cfg = tmp_path / "cfg"
    put(cfg / ".credentials.json", {"oauth": {"access": "credential-one", "list": ["credential-two"]}})
    put(cfg / "settings.json", {"env": {"K": "settings-secret"}, "model": "not-a-secret-value"})
    put(cfg / ".mcp.json", {"mcpServers": {"s": {"env": {"K": "root-mcp-secret"}, "args": ["arg-not-secret"]}}})
    (cfg / ".env").write_text(
        'DOTENV_ONE="dotenv-quoted"\n# COMMENTED=dotenv-comment\n  # INDENTED=dotenv-indented\nno equals here\n'
        "SPACED = dotenv-spaced \nEQ=a=b=dotenv-eq\nSHORT=tiny\n"
    )
    plug = cfg / "plugins" / "cache" / "m" / "p" / "1.0"
    put(plug / ".claude-plugin" / "plugin.json", {"name": "p"})
    put(plug / "settings.json", {"env": {"K": "plugin-settings-secret"}})
    put(plug / ".mcp.json", {"mcpServers": {"s": {"env": {"K": "plugin-mcp-secret"}}}})
    proj_dir = tmp_path / "listed"
    put(proj_dir / ".mcp.json", {"mcpServers": {"s": {"env": {"K": "listed-project-secret"}}}})
    put(cfg / ".claude.json", {"projects": {str(proj_dir): {}, "relative/path": {}, str(tmp_path / "gone"): {}}})
    repo = tmp_path / "repo"
    put(repo / ".claude" / "settings.json", {"env": {"K": "repo-settings-secret"}})
    put(repo / ".mcp.json", {"mcpServers": {"s": {"env": {"K": "repo-mcp-secret"}}}})

    base = read_secrets(cfg)
    assert base == {
        "credential-one",
        "credential-two",
        "settings-secret",
        "root-mcp-secret",
        "dotenv-quoted",
        "dotenv-spaced",
        "a=b=dotenv-eq",
        "plugin-settings-secret",
        "plugin-mcp-secret",
        "listed-project-secret",
    }
    assert read_secrets(str(cfg), repo) == base | {"repo-settings-secret", "repo-mcp-secret"}


def test_read_secrets_short_values_are_dropped_at_exactly_eight(tmp_path):
    cfg = tmp_path / "cfg"
    put(cfg / "settings.json", {"env": {"A": "1234567", "B": "12345678", "C": "123456789"}})
    assert read_secrets(cfg) == {"12345678", "123456789"}


def test_read_secrets_tolerates_bad_files_and_a_malformed_repo(tmp_path):
    cfg = tmp_path / "cfg"
    put(cfg / "settings.json", "{broken")
    put(cfg / ".credentials.json", "[broken")
    repo = tmp_path / "repo"
    put(repo / ".claude" / "settings.json", {"env": "string-not-dict-secret"})
    put(repo / ".mcp.json", {"mcpServers": {"s": {"env": {"K": "repo-mcp-secret"}}}})
    assert read_secrets(cfg, repo) == {"string-not-dict-secret", "repo-mcp-secret"}
    put(repo / ".claude" / "settings.json", ["list-not-object"])
    assert read_secrets(cfg, repo) == {"repo-mcp-secret"}
    (cfg / ".credentials.json").write_text('["listed-credential"]')  # an auth file may be any JSON shape
    assert read_secrets(cfg) == {"listed-credential"}


def test_read_secrets_dotenv_tolerates_bad_bytes(tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / ".env").write_bytes(b"KEY=secret-\xff-value\n")
    assert read_secrets(cfg) == {"secret-�-value"}


def test_pack_secrets_reads_only_env_in_the_three_manifests(tmp_path):
    root = tmp_path / "pack"
    put(root / ".mcp.json", {"mcpServers": {"s": {"env": {"K": "mcp-env-secret"}, "command": "cmd-not-secret"}}})
    put(root / "settings.json", {"hooks": [{"env": {"K": "settings-env-secret"}}], "env": ["list-env-secret"]})
    put(root / ".claude-plugin" / "plugin.json", {"x": {"y": [{"env": {"K": {"d": "plugin-env-secret"}}}]}, "name": "not-env-name"})
    (root / ".env").write_text("K=dotenv-never-read\n")
    put(root / "other.json", {"env": {"K": "other-file-secret"}})
    assert pack_secrets(root) == {"mcp-env-secret", "settings-env-secret", "list-env-secret", "plugin-env-secret"}


def test_pack_secrets_skips_bad_and_short(tmp_path):
    root = tmp_path / "pack"
    put(root / ".mcp.json", "{bad")
    put(root / "settings.json", {"env": {"A": "1234567", "B": "12345678"}})
    assert pack_secrets(root) == {"12345678"}
    assert pack_secrets(tmp_path / "missing") == set()
    put(root / ".claude-plugin" / "plugin.json", "[" * 100000)
    assert pack_secrets(root) == {"12345678"}


def test_depth_counts_nesting_levels():
    from constellation.claude_code import _depth

    assert _depth("x") == 0 and _depth([]) == 0 and _depth({}) == 0
    assert _depth([[]]) == 1 and _depth({"a": 1}) == 1
    assert _depth({"a": [1]}) == 2
    assert _depth({"a": {"b": {}}, "c": [[[]]]}) == 3
    assert _depth([{"k": [[]]}]) == 3


def test_secret_collection_opens_exactly_these_files_by_exact_name(tmp_path, monkeypatch):
    """The filesystem here may be case-insensitive, so spy on the names rather than relying on a missing file."""
    cfg = tmp_path / "cfg"
    repo = tmp_path / "repo"
    listed = tmp_path / "listed"
    cfg.mkdir(), repo.mkdir(), listed.mkdir()
    (cfg / ".claude.json").write_text(json.dumps({"projects": {str(listed): {}}}))
    (cfg / ".env").write_text("A=value-not-used\n")
    seen: set[str] = set()
    real_exists, real_read = Path.exists, Path.read_text

    def exists(self, *a, **k):
        seen.add(str(self))
        return real_exists(self, *a, **k)

    def read_text(self, *a, **k):
        seen.add(str(self))
        return real_read(self, *a, **k)

    monkeypatch.setattr(Path, "exists", exists)
    monkeypatch.setattr(Path, "read_text", read_text)
    read_secrets(cfg, repo)
    pack = tmp_path / "pack"
    pack.mkdir()
    pack_secrets(pack)
    wanted = {
        cfg / ".credentials.json",
        cfg / "settings.json",
        cfg / ".mcp.json",
        cfg / ".env",
        listed.resolve() / ".mcp.json",
        repo / ".claude" / "settings.json",
        repo / ".mcp.json",
        pack / ".mcp.json",
        pack / "settings.json",
        pack / ".claude-plugin" / "plugin.json",
    }
    assert {str(p) for p in wanted} <= seen


def test_listed_project_file_failure_is_silent_and_no_other_json_leaks(tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / ".claude.json").write_text("{bad")
    assert read_secrets(cfg) == set()


def test_dotenv_values_are_stripped_of_quotes_and_space_only():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        cfg = Path(d)
        (cfg / ".env").write_text("A='XXsingle-quotedXX'\nB=\"XXdouble-quotedXX\"\nC=  XXplain-valueXX  \n")
        assert read_secrets(cfg) == {"XXsingle-quotedXX", "XXdouble-quotedXX", "XXplain-valueXX"}


def test_changed_on_is_the_utc_day_whatever_the_local_zone(tmp_path, monkeypatch):
    import os
    import time

    from constellation.claude_code import _changed_on

    f = put(tmp_path / "f", "x")
    os.utime(f, (1577921400, 1577921400))  # 2020-01-01 23:30 UTC
    monkeypatch.setenv("TZ", "UTC-14")  # UTC+14: the local day is the 2nd
    time.tzset()
    try:
        assert _changed_on(f) == "2020-01-01"
    finally:
        monkeypatch.undo()
        time.tzset()
    assert _changed_on(tmp_path / "missing") is None


def test_frontmatter_takes_only_the_first_block(tmp_path):
    from constellation.claude_code import _frontmatter

    f = put(tmp_path / "a.md", "---\nname: one\n---\nbody --- rule ---\nmore\n---\nlast")
    assert _frontmatter(f) == ({"name": "one"}, None)
    assert _frontmatter(put(tmp_path / "b.md", "---\nname: x"))[0] == {}


def test_names_redacts_known_secrets():
    from constellation.claude_code import _names

    got = _names({"k": ["invented-secret-name", "plain", 5]}, "k", {"invented-secret-name"})
    assert "invented-secret-name" not in got and "plain" in got and len(got) == 2


def test_command_frontmatter_rules(tmp_path):
    from constellation.claude_code import _command

    w: list[str] = []
    assert _command(put(tmp_path / "a.md", "intro\n---\ndescription: no\n---\nbody"), w) == ("intro", "a")
    assert _command(put(tmp_path / "b.md", "---\nname: x\n---\n\n--- rule\nafter"), w) == ("--- rule", "b")
    assert _command(put(tmp_path / "c.md", "---\ndescription: from meta\n---\nbody"), w) == ("from meta", "c")
    assert w == []
    assert _command(put(tmp_path / "d.md", "---\ndescription: a: b\n---\nbody"), w) == ("a: b", "d") and len(w) == 1
    assert "not valid YAML" in w[0]
    (tmp_path / "e.md").write_bytes(b"\xff\xfe")
    assert _command(tmp_path / "e.md", w) is None and w[-1] == "skipped a command file: unreadable or not valid UTF-8"


def test_installed_reports_cleanliness_exactly(tmp_path):
    from constellation.claude_code import _installed

    cfg = tmp_path / "cfg"
    assert _installed(cfg) == ({}, True)
    f = cfg / "plugins" / "installed_plugins.json"
    good = {"installPath": "/p/one"}
    put(f, {"plugins": {"k": [good]}})
    assert _installed(cfg) == ({Path("/p/one"): "k"}, True)
    put(f, "{bad")
    assert _installed(cfg) == ({}, False)
    put(f, ["x"])
    assert _installed(cfg) == ({}, False)
    put(f, {"plugins": ["x"]})
    assert _installed(cfg) == ({}, False)
    put(f, {"plugins": {"k": [good, "str", {"installPath": 5}, {}]}})
    assert _installed(cfg) == ({Path("/p/one"): "k"}, False)
    put(f, {"plugins": {"k": 5}})
    assert _installed(cfg) == ({}, False)
    put(f, {"plugins": {"bad": 5, "k": [good]}})  # one bad key stays bad even when a later one is clean
    assert _installed(cfg) == ({Path("/p/one"): "k"}, False)
    put(f, {"plugins": {"k": [good], "bad": 5}})
    assert _installed(cfg) == ({Path("/p/one"): "k"}, False)


def test_plugin_roots_cache_named_and_outside(tmp_path):
    from constellation.claude_code import _plugin_roots

    cfg = tmp_path / "cfg"
    cached = cfg / "plugins" / "cache" / "m" / "p" / "1"
    put(cached / ".claude-plugin" / "plugin.json", {"name": "p"})
    bare = cfg / "plugins" / "cache" / "m" / "q" / "1"
    bare.mkdir(parents=True)
    outside = tmp_path / "local" / "plug"
    put(outside / ".claude-plugin" / "plugin.json", {"name": "local"})
    nomanifest = tmp_path / "local" / "bare"
    nomanifest.mkdir(parents=True)
    assert _plugin_roots(cfg) == [cached]
    put(
        cfg / "plugins" / "installed_plugins.json",
        {
            "plugins": {
                "p@m": [{"installPath": str(cached)}],
                "l": [{"installPath": str(outside)}],
                "b": [{"installPath": str(nomanifest)}, {"installPath": str(bare)}],
            }
        },
    )
    assert sorted(_plugin_roots(cfg)) == sorted([cached, outside])


def test_manifest_cases(tmp_path):
    from constellation.claude_code import _manifest

    root = tmp_path / "plugins" / "m" / "plug" / "1"
    w: list[str] = []
    assert _manifest(root, w) == {"name": root.parent.name}
    put(root / ".claude-plugin" / "plugin.json", {"name": "ok"})
    assert _manifest(root, w) == {"name": "ok"} and w == []
    for bad in ("{x", ["a"], {"name": 5}, {"name": ""}, {}):
        put(root / ".claude-plugin" / "plugin.json", bad)
        assert _manifest(root, w) is None
    assert w == ["skipped a plugin: its plugin.json is unreadable, not valid JSON or has no name"] * 5
    outside = put(tmp_path / "elsewhere.json", {"name": "evil"})
    (root / ".claude-plugin" / "plugin.json").unlink()
    (root / ".claude-plugin" / "plugin.json").symlink_to(outside)
    w.clear()
    assert _manifest(root, w) is None and w == ["skipped plugin.json in plugin: it is a symlink pointing outside it"]


def _opened(monkeypatch, call) -> set[str]:
    """The exact path strings a call probes or reads (the filesystem here may be case-insensitive)."""
    seen: set[str] = set()
    real_exists, real_read = Path.exists, Path.read_text

    def exists(self, *a, **k):
        seen.add(str(self))
        return real_exists(self, *a, **k)

    def read_text(self, *a, **k):
        seen.add(str(self))
        return real_read(self, *a, **k)

    with monkeypatch.context() as m:
        m.setattr(Path, "exists", exists)
        m.setattr(Path, "read_text", read_text)
        call()
    return seen


def test_plugin_paths_use_exact_names(tmp_path, monkeypatch):
    from constellation.claude_code import _installed, _manifest, _plugin_roots

    cfg = tmp_path / "cfg"
    outside = tmp_path / "local" / "plug"
    put(outside / ".claude-plugin" / "plugin.json", {"name": "local"})
    put(cfg / "plugins" / "installed_plugins.json", {"plugins": {"l": [{"installPath": str(outside)}]}})
    cached = cfg / "plugins" / "cache" / "m" / "p" / "1"
    cached.mkdir(parents=True)
    manifest = str(outside / ".claude-plugin" / "plugin.json")
    assert str(cfg / "plugins" / "installed_plugins.json") in _opened(monkeypatch, lambda: _installed(cfg))
    assert manifest in _opened(monkeypatch, lambda: _manifest(outside, []))
    # outside the cache, only the named-root branch can probe this path
    cached.rmdir()
    assert manifest in _opened(monkeypatch, lambda: _plugin_roots(cfg))
    put(cached / ".claude-plugin" / "plugin.json", {"name": "p"})
    assert str(cached / ".claude-plugin" / "plugin.json") in _opened(monkeypatch, lambda: _plugin_roots(cfg))
